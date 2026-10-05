import os
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from common.database import get_db
from common.enums import UserRole
from common.auth_dependencies import get_current_user, require_role
from common.auth import get_password_hash
from models.users import User
from models.employees import EmployeeInvite, EmployeeAuditLog
from services.notifications.tasks import send_email_task
from services.notifications.email_templates import get_employee_invite_template
from models.communication_logs import CommunicationLog

router = APIRouter(prefix="/employees", tags=["Admin Employees"])

def record_audit_log(db: Session, employee_id: str, action_type: str, details: dict = None, resource_id: str = None):
    log = EmployeeAuditLog(
        employee_id=employee_id,
        action_type=action_type,
        details=details or {},
        resource_id=resource_id
    )
    db.add(log)
    db.commit()

# --- Schemas (inline for now) ---
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator

class EmployeeInviteCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    role: UserRole
    permissions: List[str] = []

class EmployeeResponse(BaseModel):
    user_id: UUID
    email: str
    first_name: str
    last_name: str
    role: str
    permissions: List[str] = []
    is_active: bool
    last_active_at: Optional[datetime]
    
    @field_validator("permissions", mode="before")
    def default_permissions(cls, v):
        return v or []
    
    class Config:
        from_attributes = True

class InviteResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    permissions: List[str] = []
    expires_at: datetime
    created_at: datetime
    is_used: bool

    class Config:
        from_attributes = True


@router.post("/invite")
def invite_employee(
    payload: EmployeeInviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """
    Generate an invite token, save it to `employee_invites`, and dispatch an email.
    """
    # Check if user already exists
    existing_user = db.execute(select(User).where(User.email == payload.email)).scalars().first()
    if existing_user:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")
        
    # Check if an active invite already exists
    existing_invite = db.execute(select(EmployeeInvite).where(
        EmployeeInvite.email == payload.email,
        EmployeeInvite.is_used == False,
        EmployeeInvite.expires_at > datetime.utcnow()
    )).scalars().first()
    
    if existing_invite:
        raise HTTPException(status_code=400, detail="An active invite has already been sent to this email.")

    # Generate token
    token = secrets.token_urlsafe(32)
    
    new_invite = EmployeeInvite(
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=payload.role.value,
        permissions=payload.permissions,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        created_by=current_user.user_id
    )
    db.add(new_invite)
    db.commit()
    db.refresh(new_invite)
    
    # Audit log
    record_audit_log(db, current_user.user_id, "INVITED_EMPLOYEE", {"email": payload.email, "role": payload.role.value})
    
    # Send Email
    setup_url = f"{os.environ.get('FRONTEND_URL', 'http://localhost:3000')}/employee-setup?token={token}"
    html_body = get_employee_invite_template(payload.first_name, payload.role.value, setup_url)
    
    log = CommunicationLog(
        user_id=current_user.user_id,  # Associate with super admin sending it for now
        channel="EMAIL",
        destination=payload.email,
        subject="You're Invited to KapuLetu!",
        status="QUEUED"
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    
    send_email_task(str(log.log_id), payload.email, "You're Invited to KapuLetu!", html_body)
    
    return {"message": "Invitation sent successfully"}

@router.get("/", response_model=List[EmployeeResponse])
def get_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """List all active employees"""
    employees = db.execute(select(User).where(
        User.role.in_([UserRole.SUPER_ADMIN.value, UserRole.CONTENT_MANAGER.value, UserRole.SUPPORT_AGENT.value, UserRole.FINANCE_MANAGER.value, UserRole.ADMIN.value, UserRole.CEO.value])
    )).scalars().all()
    
    return employees

@router.get("/invites", response_model=List[InviteResponse])
def get_pending_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """List pending invites"""
    invites = db.execute(select(EmployeeInvite).where(
        EmployeeInvite.is_used == False
    )).scalars().all()
    
    return invites

@router.delete("/{user_id}")
def revoke_employee_access(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Revoke an employee's access by suspending their account"""
    if str(current_user.user_id) == user_id:
        raise HTTPException(status_code=400, detail="Cannot revoke your own access.")
        
    employee = db.query(User).get(user_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    employee.is_active = False
    employee.deleted_at = datetime.utcnow()
    db.commit()
    
    record_audit_log(db, current_user.user_id, "REVOKED_EMPLOYEE", {}, resource_id=str(employee.user_id))
    return {"message": "Employee access revoked."}

@router.get("/audit-logs")
def get_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Get global audit logs for super admins."""
    logs = db.execute(
        select(EmployeeAuditLog).order_by(EmployeeAuditLog.timestamp.desc()).limit(limit)
    ).scalars().all()
    
    # Simple mapping without complex Pydantic response models for now
    return [
        {
            "log_id": str(log.log_id),
            "employee_id": str(log.employee_id) if log.employee_id else None,
            "action_type": log.action_type,
            "resource_id": log.resource_id,
            "details": log.details,
            "timestamp": log.timestamp.isoformat() + "Z",
            "ip_address": log.ip_address
        } for log in logs
    ]



class UpdatePermissionsIn(BaseModel):
    permissions: List[str]

@router.put('/{user_id}/permissions')
def update_employee_permissions(
    user_id: str,
    payload: UpdatePermissionsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    employee = db.query(User).filter(User.user_id == user_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail='Employee not found')
    employee.permissions = payload.permissions
    db.commit()
    return {'message': 'Permissions updated'}
