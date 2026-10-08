"""
/admin/communications: broadcasts, the delivery log, suppressions and email templates.
Every route requires the manage_communications permission.

/communications/unsubscribe: the public, token-authenticated unsubscribe endpoint linked from marketing email.
"""
import csv
import datetime
import io
import itertools
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from common.auth_dependencies import get_verified_user, missing_permissions, require_permissions
from common.database import get_db
from models.users import User as UserModel

from .broadcasts import BroadcastService
from .common import CommError, as_uuid, audit
from .consent import (
    add_suppression,
    list_suppressions,
    mask_email,
    read_unsubscribe_token,
    remove_suppression,
    unsubscribe,
)
from .events import apply_events, resend_event, verify_resend_signature
from .inquiries import InquiryService
from .preferences import get_preferences, update_preferences
from .providers.whatsapp import approved_templates
from .schemas import (
    BroadcastCreateIn,
    BroadcastEstimateIn,
    DecisionIn,
    DraftIn,
    InquiryReplyIn,
    InquiryStatusIn,
    PreferencesIn,
    SuppressionIn,
    TemplatePreviewIn,
    TemplateSaveIn,
    TestSendIn,
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


@router.post("/broadcasts/drafts", status_code=201, summary="Save a new draft")
async def create_draft(payload: DraftIn, db: Session = Depends(get_db), user: User = Depends(communicator)):
    return _call(BroadcastService(db).save_draft, payload.model_dump(exclude_none=True), _actor(user))


@router.post("/broadcasts/test", summary="Send the content to yourself on the chosen channels")
async def test_broadcast(payload: TestSendIn, db: Session = Depends(get_db), user: User = Depends(communicator)):
    return _call(BroadcastService(db).test_send, payload.model_dump(exclude_none=True), _actor(user))


@router.put("/broadcasts/{broadcast_id}", summary="Update a draft")
async def update_draft(broadcast_id: str, payload: DraftIn, db: Session = Depends(get_db),
                       user: User = Depends(communicator)):
    return _call(BroadcastService(db).save_draft, payload.model_dump(exclude_none=True), _actor(user), broadcast_id)


@router.delete("/broadcasts/{broadcast_id}", summary="Delete a draft")
async def delete_draft(broadcast_id: str, db: Session = Depends(get_db), user: User = Depends(communicator)):
    _call(BroadcastService(db).delete_draft, broadcast_id, _actor(user))
    return {"status": "deleted"}


@router.post("/broadcasts/{broadcast_id}/submit", summary="Validate a draft and queue it (or send it for approval)")
async def submit_draft(broadcast_id: str, db: Session = Depends(get_db), user: User = Depends(communicator)):
    return _call(BroadcastService(db).submit, broadcast_id, _actor(user))


@router.post("/broadcasts/{broadcast_id}/duplicate", status_code=201, summary="Copy a broadcast into a new draft")
async def duplicate_broadcast(broadcast_id: str, db: Session = Depends(get_db), user: User = Depends(communicator)):
    return _call(BroadcastService(db).duplicate, broadcast_id, _actor(user))


@router.post("/broadcasts/{broadcast_id}/return-to-draft", summary="Pull back a broadcast that hasn't started")
async def return_to_draft(broadcast_id: str, db: Session = Depends(get_db), user: User = Depends(communicator)):
    return _call(BroadcastService(db).return_to_draft, broadcast_id, _actor(user))


@router.get("/whatsapp/templates", summary="Approved WhatsApp templates from Meta Business Manager")
async def whatsapp_templates(refresh: bool = False, _: User = Depends(communicator)):
    try:
        templates = approved_templates(force=refresh)
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't load templates from Meta. Try again in a minute.")
    return {"configured": templates is not None, "templates": templates or []}


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

@router.get("/messages", summary="Delivery log: broadcasts and transactional messages")
async def list_messages(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None,
    kind: Optional[str] = Query(None, description="broadcast or transactional"),
    db: Session = Depends(get_db), _: User = Depends(communicator),
):
    return _call(BroadcastService(db).messages, None, page, limit, channel, status, q, kind)


EXPORT_COLUMNS = ["created_at", "recipient", "destination", "channel", "category", "broadcast_title", "subject",
                  "status", "error", "sent_at", "delivered_at", "opened_at", "clicked_at", "attempts"]


def _csv_cell(value) -> str:
    """Spreadsheets run cells starting with = + - @ as formulas; names and subjects come from users."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/messages/export", summary="Download the delivery log as CSV (same filters, up to 100,000 rows)")
async def export_messages(
    channel: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None,
    broadcast_id: Optional[str] = None, kind: Optional[str] = None,
    date_from: Optional[datetime.datetime] = Query(None, alias="from"),
    date_to: Optional[datetime.datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db), user: User = Depends(communicator),
):
    service = BroadcastService(db)
    rows = _call(lambda: service.export_messages(broadcast_id, channel, status, q, date_from, date_to, kind))
    first = _call(next, rows, None)  # surfaces filter errors as 400 before the download starts
    audit(db, _actor(user), "DELIVERY_LOG_EXPORTED", "COMM_MESSAGES", broadcast_id,
          {"channel": channel, "status": status, "q": q, "kind": kind})
    db.commit()

    def stream():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(EXPORT_COLUMNS)
        for row in itertools.chain([first] if first else [], rows):
            writer.writerow([_csv_cell(row.get(c)) for c in EXPORT_COLUMNS])
            if buffer.tell() > 64_000:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
        yield buffer.getvalue()

    filename = f"delivery-log-{datetime.date.today().isoformat()}.csv"
    return StreamingResponse(stream(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/messages/{message_id}/events", summary="Everything providers reported about one message")
async def message_events(message_id: str, db: Session = Depends(get_db), _: User = Depends(communicator)):
    return _call(BroadcastService(db).message_events, message_id)


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


@public_router.post("/webhooks/resend", include_in_schema=False)
async def resend_webhook(request: Request, db: Session = Depends(get_db)):
    """Delivery, bounce, complaint, open and click events from Resend, signed with RESEND_WEBHOOK_SECRET."""
    body = await request.body()
    _call(verify_resend_signature, body, dict(request.headers))
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    event = resend_event(payload, request.headers["svix-id"])
    if event:
        _call(apply_events, db, [event])
    return {"status": "ok"}


# --- website inquiries (communications or support staff) ---

def inquiry_handler(user: User = Depends(get_verified_user)) -> User:
    if missing_permissions(user, ["manage_communications"]) and missing_permissions(user, ["manage_support"]) \
            and user.get("role") != "support_agent":
        raise HTTPException(status_code=403, detail="Needs the Manage Communications or Manage Support permission")
    return user


@router.get("/inquiries", summary="Website contact-form messages")
async def list_inquiries(
    page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=200),
    status: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(inquiry_handler),
):
    return _call(InquiryService(db).list, page, limit, status, q)


@router.get("/inquiries/{inquiry_id}", summary="An inquiry and its reply thread")
async def get_inquiry(inquiry_id: str, db: Session = Depends(get_db), _: User = Depends(inquiry_handler)):
    return _call(InquiryService(db).get, inquiry_id)


@router.patch("/inquiries/{inquiry_id}", summary="Change an inquiry's status")
async def update_inquiry(inquiry_id: str, payload: InquiryStatusIn, db: Session = Depends(get_db),
                         user: User = Depends(inquiry_handler)):
    return _call(InquiryService(db).set_status, inquiry_id, payload.status, _actor(user))


@router.post("/inquiries/{inquiry_id}/reply", summary="Email a reply to the person who wrote in")
async def reply_inquiry(inquiry_id: str, payload: InquiryReplyIn, db: Session = Depends(get_db),
                        user: User = Depends(inquiry_handler)):
    return _call(InquiryService(db).reply, inquiry_id, payload.body, _actor(user), payload.resolve)


# --- the signed-in person's own preferences ---

@public_router.get("/preferences", summary="My marketing preferences")
async def my_preferences(db: Session = Depends(get_db), user: User = Depends(get_verified_user)):
    return get_preferences(db, _me(db, user))


@public_router.put("/preferences", summary="Change my marketing preferences")
async def change_my_preferences(payload: PreferencesIn, db: Session = Depends(get_db),
                                user: User = Depends(get_verified_user)):
    return _call(update_preferences, db, _me(db, user), payload.marketing_email, payload.marketing_whatsapp)


def _me(db: Session, user: User) -> UserModel:
    me = db.get(UserModel, as_uuid(_actor(user)))
    if not me:
        raise HTTPException(status_code=404, detail="Account not found")
    return me
