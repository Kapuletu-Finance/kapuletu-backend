from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from common.auth_dependencies import require_permissions
from common.database import get_db
from common.enums import ApprovalStatus
from services.admin.approval_service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["Admin Approvals"])

approver = require_permissions(["manage_approvals"])
# Sensitive actions today are financial; whoever can do finance work can ask for one.
submitter = require_permissions(["manage_finance"])

# Action types that only their own module may create (a hand-made request would have nothing to execute).
MODULE_OWNED_ACTIONS = {"ISSUE_REFUND"}

# --- Schemas ---

class ApprovalRequestCreate(BaseModel):
    action_type: str
    payload: dict
    justification: Optional[str] = None

class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    requested_by: str
    action_type: str
    payload: dict
    justification: Optional[str]
    status: str
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime

    @classmethod
    def of(cls, req) -> "ApprovalResponse":
        return cls(
            id=str(req.id), requested_by=str(req.requested_by), action_type=req.action_type,
            payload=req.payload or {}, justification=req.justification, status=req.status,
            resolved_by=str(req.resolved_by) if req.resolved_by else None, resolved_at=req.resolved_at,
            created_at=req.created_at,
        )

class ResolveAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")


def _actor(user: Dict[str, Any]) -> str:
    return user.get("user_id") or user.get("sub")


# --- Endpoints ---

@router.post("", response_model=ApprovalResponse)
def submit_approval_request(
    payload: ApprovalRequestCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(submitter)
):
    """Submit a sensitive action to the approval queue."""
    if payload.action_type in MODULE_OWNED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"{payload.action_type} requests are created by their own screen")
    req = ApprovalService(db).create_request(
        requested_by=_actor(current_user),
        action_type=payload.action_type,
        payload=payload.payload,
        justification=payload.justification
    )
    return ApprovalResponse.of(req)

@router.get("", response_model=List[ApprovalResponse])
def get_approvals(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(approver)
):
    """Approval requests, newest first; ?status=pending for the open queue."""
    service = ApprovalService(db)
    requests = service.list_pending_requests() if status == "pending" else service.list_all_requests()
    return [ApprovalResponse.of(r) for r in requests]

@router.post("/{request_id}/resolve", response_model=ApprovalResponse)
def resolve_approval(
    request_id: str,
    payload: ResolveAction,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(approver)
):
    """Approve or reject a pending request; an approved one is carried out in the same transaction."""
    actor = _actor(current_user)
    try:
        req = ApprovalService(db).resolve_request(request_id, actor, payload.action, commit=False)
        dispatch_resolved_action(db, req, actor)
        db.commit()
        db.refresh(req)
        return ApprovalResponse.of(req)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

def dispatch_resolved_action(db: Session, req, actor_id: str):
    """
    Executes (or records the rejection of) the action behind a resolved request.
    Raises ValueError to abort the whole resolution.
    """
    if req.action_type == "ISSUE_REFUND":
        from services.admin.finance import FinanceError, RefundService
        refund_id = (req.payload or {}).get("refund_id")
        if not refund_id:
            raise ValueError("This refund request has no refund attached")
        try:
            RefundService(db).decide(refund_id, req.status == ApprovalStatus.APPROVED.value, actor_id,
                                     approval_already_resolved=True)
        except FinanceError as e:
            raise ValueError(str(e))
