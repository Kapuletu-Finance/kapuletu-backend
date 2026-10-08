"""
/admin/communications: broadcasts, the delivery log, suppressions and email templates.
Every route requires the manage_communications permission.

/communications/unsubscribe: the public, token-authenticated unsubscribe endpoint linked from marketing email.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from common.auth_dependencies import require_permissions
from common.database import get_db
from models.users import User as UserModel

from .broadcasts import BroadcastService
from .common import CommError, as_uuid, audit, iso, page_bounds, paged
from .consent import (
    add_suppression,
    list_suppressions,
    mask_email,
    read_unsubscribe_token,
    remove_suppression,
    unsubscribe,
)
from .schemas import (
    BroadcastCreateIn,
    BroadcastEstimateIn,
    DecisionIn,
    SuppressionIn,
    TemplatePreviewIn,
    TemplateSaveIn,
)
from .templates import TemplateService

router = APIRouter(prefix="/admin/communications", tags=["11c. Admin Communications"])
public_router = APIRouter(prefix="/communications", tags=["11. Notifications"])

communicator = require_permissions(["manage_communications"])
User = Dict[str, Any]


def _http(e: CommError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


def _actor(user: User) -> Optional[str]:
    return user.get("user_id") or user.get("sub")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except CommError as e:
        raise _http(e)


# --- overview ---

@router.get("/overview", summary="Messaging KPIs for the last N days")
async def overview(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), _: User = Depends(communicator)):
    return BroadcastService(db).overview(days)


# --- broadcasts ---

@router.get("/broadcasts", summary="List broadcasts")
async def list_broadcasts(
    page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=200),
    status: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(communicator),
):
    return _call(BroadcastService(db).list, page, limit, status, q)


@router.post("/broadcasts/estimate", summary="Who a broadcast would reach, per channel, before sending")
async def estimate_broadcast(payload: BroadcastEstimateIn, db: Session = Depends(get_db), _: User = Depends(communicator)):
    return _call(BroadcastService(db).estimate, payload.model_dump())


@router.post("/broadcasts", status_code=201, summary="Create and queue a broadcast (or send it for approval)")
async def create_broadcast(payload: BroadcastCreateIn, db: Session = Depends(get_db), user: User = Depends(communicator)):
    return _call(BroadcastService(db).create, payload.model_dump(), _actor(user))


@router.get("/broadcasts/{broadcast_id}", summary="Broadcast detail with live delivery counts")
async def get_broadcast(broadcast_id: str, db: Session = Depends(get_db), _: User = Depends(communicator)):
    return _call(BroadcastService(db).get, broadcast_id)


@router.get("/broadcasts/{broadcast_id}/messages", summary="One broadcast's recipients and delivery status")
async def broadcast_messages(
    broadcast_id: str, page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(communicator),
):
    return _call(BroadcastService(db).messages, broadcast_id, page, limit, channel, status, q)


@router.post("/broadcasts/{broadcast_id}/approve", summary="Approve a broadcast (not your own)")
async def approve_broadcast(broadcast_id: str, payload: DecisionIn, db: Session = Depends(get_db),
                            user: User = Depends(communicator)):
    return _call(BroadcastService(db).approve, broadcast_id, _actor(user), payload.note)


@router.post("/broadcasts/{broadcast_id}/reject", summary="Reject a broadcast awaiting approval")
async def reject_broadcast(broadcast_id: str, payload: DecisionIn, db: Session = Depends(get_db),
                           user: User = Depends(communicator)):
    return _call(BroadcastService(db).reject, broadcast_id, _actor(user), payload.note)


@router.post("/broadcasts/{broadcast_id}/cancel", summary="Stop a broadcast that hasn't finished")
async def cancel_broadcast(broadcast_id: str, db: Session = Depends(get_db), user: User = Depends(communicator)):
    return _call(BroadcastService(db).cancel, broadcast_id, _actor(user))


@router.get("/recipients/search", summary="Find users to address a broadcast to")
async def search_recipients(q: str = Query(..., min_length=2), limit: int = Query(20, ge=1, le=50),
                            db: Session = Depends(get_db), _: User = Depends(communicator)):
    like = f"%{q.strip()}%"
    users = (db.query(UserModel).filter(UserModel.deleted_at.is_(None), or_(
        UserModel.first_name.ilike(like), UserModel.last_name.ilike(like), UserModel.email.ilike(like),
        UserModel.phone_number.ilike(like),
    )).order_by(UserModel.first_name).limit(limit).all())
    return [{
        "user_id": str(u.user_id), "name": f"{u.first_name} {u.last_name}".strip(), "email": u.email,
        "phone_number": u.phone_number, "role": u.role, "marketing_consent": bool(u.marketing_consent),
        "is_active": bool(u.is_active),
    } for u in users]


# --- delivery log ---

@router.get("/messages", summary="Delivery log across all broadcasts")
async def list_messages(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(communicator),
):
    return _call(BroadcastService(db).messages, None, page, limit, channel, status, q)


@router.get("/transactional-log", summary="Transactional emails and WhatsApp (OTPs, receipts, invites)")
async def transactional_log(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(communicator),
):
    """Sends that don't go through the outbox yet still write communication_logs; they move over in Phase 4."""
    from models.communication_logs import CommunicationLog
    page, limit, offset = page_bounds(page, limit)
    query = (db.query(CommunicationLog, UserModel).outerjoin(UserModel, CommunicationLog.user_id == UserModel.user_id)
             .filter(CommunicationLog.campaign_id.is_(None)))  # old broadcast rows were copied to comm_messages
    if channel:
        query = query.filter(CommunicationLog.channel == channel.upper())
    if status:
        query = query.filter(CommunicationLog.status == status.upper())
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(CommunicationLog.destination.ilike(like), CommunicationLog.subject.ilike(like)))
    total = query.count()
    rows = query.order_by(CommunicationLog.created_at.desc()).offset(offset).limit(limit).all()
    return paged([{
        "id": str(log.log_id),
        "recipient": f"{u.first_name} {u.last_name}".strip() if u else "Not a user",
        "channel": log.channel.lower(),
        "destination": log.destination,
        "subject": log.subject,
        "status": log.status.lower(),
        # Tracebacks stay in the server logs; the hub shows the first line only
        "error": (log.error_message or "").strip().splitlines()[-1][:300] if log.error_message else None,
        "created_at": iso(log.created_at),
    } for log, u in rows], total, page, limit)


# --- suppressions ---

@router.get("/suppressions", summary="Destinations we must not message")
async def get_suppressions(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(communicator),
):
    return list_suppressions(db, page, limit, channel, q)


@router.post("/suppressions", status_code=201, summary="Block a destination by hand")
async def create_suppression(payload: SuppressionIn, db: Session = Depends(get_db), user: User = Depends(communicator)):
    try:
        row = add_suppression(db, payload.channel, payload.destination, "manual", payload.category, payload.note,
                              actor_id=_actor(user))
        audit(db, _actor(user), "SUPPRESSION_ADDED", "SUPPRESSION", row.suppression_id,
              {"channel": row.channel, "destination": row.destination, "category": row.category})
        db.commit()
    except CommError as e:
        raise _http(e)
    return {"id": str(row.suppression_id)}


@router.delete("/suppressions/{suppression_id}", summary="Remove a manual block or bounce")
async def delete_suppression(suppression_id: str, db: Session = Depends(get_db), user: User = Depends(communicator)):
    _call(remove_suppression, db, suppression_id, _actor(user))
    return {"status": "removed"}


# --- email templates ---

@router.get("/templates", summary="Editable email templates")
async def list_templates(db: Session = Depends(get_db), _: User = Depends(communicator)):
    return TemplateService(db).list()


@router.get("/templates/{name}", summary="Template source and version history")
async def get_template(name: str, db: Session = Depends(get_db), _: User = Depends(communicator)):
    return _call(TemplateService(db).get, name)


@router.put("/templates/{name}", summary="Save a new version (validated in the sandbox)")
async def save_template(name: str, payload: TemplateSaveIn, db: Session = Depends(get_db),
                        user: User = Depends(communicator)):
    return _call(TemplateService(db).save, name, payload.content, payload.note, _actor(user))


@router.post("/templates/{name}/restore/{version}", summary="Make an old version current again")
async def restore_template(name: str, version: int, db: Session = Depends(get_db), user: User = Depends(communicator)):
    return _call(TemplateService(db).restore, name, version, _actor(user))


@router.post("/templates/{name}/preview", response_class=HTMLResponse, summary="Render with sample values")
async def preview_template(name: str, payload: TemplatePreviewIn, db: Session = Depends(get_db),
                           _: User = Depends(communicator)):
    return HTMLResponse(_call(TemplateService(db).preview, name, payload.content, payload.message))


# --- public unsubscribe ---

@public_router.get("/unsubscribe", summary="Check an unsubscribe link (used by the unsubscribe page)")
async def check_unsubscribe(token: str, db: Session = Depends(get_db)):
    data = _call(read_unsubscribe_token, token)
    user = db.get(UserModel, _call(as_uuid, data["user_id"]))
    if not user:
        raise HTTPException(status_code=400, detail="This unsubscribe link is invalid")
    return {"email": mask_email(user.email), "subscribed": bool(user.marketing_consent), "category": data["category"]}


@public_router.post("/unsubscribe", summary="Unsubscribe from marketing (RFC 8058 one-click compatible)")
async def do_unsubscribe(token: str = Query(...), db: Session = Depends(get_db)):
    return _call(unsubscribe, db, token)
