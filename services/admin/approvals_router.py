from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime

from common.database import get_db
from common.enums import UserRole
from common.auth_dependencies import require_role
from models.users import User
from services.admin.approval_service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["Admin Approvals"])

# --- Schemas ---

class ApprovalRequestCreate(BaseModel):
    action_type: str
    payload: dict
    justification: Optional[str] = None

class ApprovalResponse(BaseModel):
    id: str
    requested_by: str
    action_type: str
    payload: dict
    justification: Optional[str]
    status: str
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True

class ResolveAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")


# --- Endpoints ---

@router.post("/", response_model=ApprovalResponse)
def submit_approval_request(
    payload: ApprovalRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.FINANCE_MANAGER, UserRole.SUPER_ADMIN, UserRole.ADMIN]))
):
    """Submit a sensitive action to the approval queue."""
    service = ApprovalService(db)
    req = service.create_request(
        requested_by=current_user.user_id,
        action_type=payload.action_type,
        payload=payload.payload,
        justification=payload.justification
    )
    return req

@router.get("/", response_model=List[ApprovalResponse])
def get_approvals(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN]))
):
    """Get all approval requests. Super Admin only."""
    service = ApprovalService(db)
    if status == "pending":
        return service.list_pending_requests()
    return service.list_all_requests()

@router.post("/{request_id}/resolve", response_model=ApprovalResponse)
def resolve_approval(
    request_id: str,
    payload: ResolveAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN]))
):
    """Approve or Reject a pending request."""
    service = ApprovalService(db)
    try:
        req = service.resolve_request(
            request_id=request_id,
            resolved_by=current_user.user_id,
            action=payload.action
        )
        
        # If approved, dispatch the actual logic based on action_type
        if req.status == "APPROVED":
            dispatch_approved_action(db, req)
            
        return req
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

def dispatch_approved_action(db: Session, req):
    """
    Executes the payload logic for an approved action.
    """
    if req.action_type == "ISSUE_REFUND":
        # Handle refund logic here
        pass
    elif req.action_type == "SUSPEND_USER":
        # Handle user suspension logic here
        pass
    # ... add more handlers as needed
