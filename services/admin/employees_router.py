import os
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from common.database import get_db
from common.enums import UserRole
from common.auth_dependencies import get_current_user, require_permissions, require_role
from common.auth import get_password_hash
from models.users import User
from models.employees import EmployeeInvite, EmployeeAuditLog
from services.notifications.tasks import send_email_task
from services.notifications.email_templates import get_employee_invite_template
from models.communication_logs import CommunicationLog
from common.permissions import EMPLOYEE_PERMISSIONS
from services.auth.schemas import format_phone
from services.admin import employee_profile_service
from services.admin.employee_profile_schemas import (
    ActivityPageOut, ActivityView, EmployeeProfileOut, EmployeeUpdateIn, PermissionOut,
)
from services.hr.directory import HR_ADMIN_PERMISSION

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
    phone_number: Optional[str] = None
    role: str
    permissions: List[str] = []

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone_number(cls, value):
        if value is None:
            return None
        normalized = format_phone(value)
        if normalized is not None and not 7 <= len(normalized) <= 20:
            raise ValueError("Phone number must be between 7 and 20 characters.")
        return normalized

    @field_validator("role")
    @classmethod
    def reject_treasurer_role(cls, role):
        if role == UserRole.TREASURER.value:
            raise ValueError("Employee invitations can't use the treasurer role.")
        return role

class EmployeeResponse(BaseModel):
    user_id: UUID
    email: str
    first_name: str
    last_name: str
    phone_number: Optional[str] = None
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
    id: UUID
    email: str
    first_name: str
    last_name: str
    phone_number: Optional[str] = None
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

    if payload.phone_number:
        existing_phone = db.execute(
            select(User.user_id).where(User.phone_number == payload.phone_number)
        ).first()
        if existing_phone:
            raise HTTPException(status_code=409, detail="That phone number belongs to another account.")
        
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
        phone_number=payload.phone_number,
        role=payload.role,
        permissions=payload.permissions,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        created_by=current_user["sub"]
    )
    db.add(new_invite)
    db.commit()
    db.refresh(new_invite)
    
    # Audit log
    record_audit_log(db, current_user["sub"], "INVITED_EMPLOYEE", {"email": payload.email, "role": payload.role})
    
    # Send Email
    setup_url = f"{os.environ.get('FRONTEND_URL', 'http://localhost:3000')}/employee-setup?token={token}"
    html_body = get_employee_invite_template(payload.first_name, payload.role, setup_url)
    
    log = CommunicationLog(
        user_id=current_user["sub"],  # Associate with super admin sending it for now
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
    # HR admins need the directory to pick meeting attendees and set per-employee schedules.
    current_user: dict = Depends(require_permissions([HR_ADMIN_PERMISSION]))
):
    """List all active employees"""
    employees = db.execute(select(User).where(
        User.role != UserRole.TREASURER.value
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

@router.post("/invites/{invite_id}/resend")
def resend_invite(
    invite_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Resend a pending invite, refreshing the token and extending the expiry."""
    invite = db.query(EmployeeInvite).filter(EmployeeInvite.id == invite_id, EmployeeInvite.is_used == False).first()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Active invite not found")
        
    # Refresh token and expiry
    new_token = secrets.token_urlsafe(32)
    invite.token = new_token
    invite.expires_at = datetime.utcnow() + timedelta(hours=24)
    db.commit()
    db.refresh(invite)
    
    # Audit log
    record_audit_log(db, current_user["sub"], "RESENT_EMPLOYEE_INVITE", {"email": invite.email})
    
    # Send Email
    setup_url = f"{os.environ.get('FRONTEND_URL', 'http://localhost:3000')}/employee-setup?token={new_token}"
    html_body = get_employee_invite_template(invite.first_name, invite.role, setup_url)
    
    log = CommunicationLog(
        user_id=current_user["sub"],
        channel="EMAIL",
        destination=invite.email,
        subject="Reminder: You're Invited to KapuLetu!",
        status="QUEUED"
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    
    send_email_task(str(log.log_id), invite.email, "Reminder: You're Invited to KapuLetu!", html_body)
    
    return {"message": "Invitation resent successfully"}

@router.delete("/{user_id}")
def revoke_employee_access(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Revoke an employee's access: suspends the account and ends their sessions (reversible via /restore)."""
    employee_profile_service.set_suspended(db, user_id, True, current_user["user_id"])
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



class ActivityTrendItem(BaseModel):
    date: str
    actions: int

class EmployeeMetricsResponse(BaseModel):
    total_hours_logged: float
    total_actions_performed: int
    activity_trend: List[ActivityTrendItem]

@router.get('/{user_id}/metrics', response_model=EmployeeMetricsResponse)
def get_employee_metrics(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN]))
):
    from models.hr import EmployeeReport
    from models.audit_log import AuditLog
    from sqlalchemy import func
    import datetime

    # 1. Total Hours Logged
    reports = db.query(EmployeeReport).filter(
        EmployeeReport.user_id == user_id,
        EmployeeReport.status.in_(["confirmed", "approved"])
    ).all()
    
    total_seconds = 0
    for report in reports:
        if report.clock_in_time and report.clock_out_time:
            diff = report.clock_out_time - report.clock_in_time
            total_seconds += diff.total_seconds()
            
    total_hours_logged = round(total_seconds / 3600, 2)
    
    # 2. Total Actions Performed
    total_actions = db.query(func.count(AuditLog.log_id)).filter(
        AuditLog.actor_id == user_id
    ).scalar() or 0
    
    # 3. Activity Trend (Last 7 Days)
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=6)
    
    # Get all logs for the last 7 days
    logs = db.query(func.date(AuditLog.created_at).label("log_date"), func.count(AuditLog.log_id)).filter(
        AuditLog.actor_id == user_id,
        func.date(AuditLog.created_at) >= start_date
    ).group_by(func.date(AuditLog.created_at)).all()
    
    log_map = {str(date): count for date, count in logs}
    
    trend = []
    for i in range(7):
        current_date = start_date + datetime.timedelta(days=i)
        date_str = str(current_date)
        trend.append(ActivityTrendItem(
            date=current_date.strftime("%b %d"),
            actions=log_map.get(date_str, 0)
        ))
        
    return EmployeeMetricsResponse(
        total_hours_logged=total_hours_logged,
        total_actions_performed=total_actions,
        activity_trend=trend
    )


# --- Employee profile (HR admins view; super admins change access) ---

hr_admin = require_permissions([HR_ADMIN_PERMISSION])
super_admin = require_role([UserRole.SUPER_ADMIN])


@router.get("/permissions", response_model=List[PermissionOut], summary="Permission catalogue")
def list_permissions(current_user: dict = Depends(hr_admin)):
    return EMPLOYEE_PERMISSIONS


@router.get("/{user_id}", response_model=EmployeeProfileOut, summary="Employee profile")
def get_employee_profile(user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(hr_admin)):
    return employee_profile_service.get_profile(db, user_id)


@router.patch("/{user_id}", response_model=EmployeeProfileOut, summary="Edit profile, role or permissions")
def update_employee(
    user_id: str, payload: EmployeeUpdateIn, db: Session = Depends(get_db), current_user: dict = Depends(super_admin)
):
    return employee_profile_service.update_employee(db, user_id, payload, current_user["user_id"])


@router.post("/{user_id}/suspend", response_model=EmployeeProfileOut, summary="Suspend and sign out")
def suspend_employee(user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(super_admin)):
    return employee_profile_service.set_suspended(db, user_id, True, current_user["user_id"])


@router.post("/{user_id}/restore", response_model=EmployeeProfileOut, summary="Restore a suspended employee")
def restore_employee(user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(super_admin)):
    return employee_profile_service.set_suspended(db, user_id, False, current_user["user_id"])


@router.post("/{user_id}/sign-out", response_model=EmployeeProfileOut, summary="Sign out of all sessions")
def sign_out_employee(user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(super_admin)):
    return employee_profile_service.sign_out_everywhere(db, user_id, current_user["user_id"])


@router.post("/{user_id}/reset-password", summary="Send a password reset code")
def reset_employee_password(user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(super_admin)):
    employee_profile_service.send_password_reset(db, user_id, current_user["user_id"])
    return {"message": "Password reset code sent."}


@router.get("/{user_id}/activity", response_model=ActivityPageOut, summary="Employee activity feed")
def get_employee_activity(
    user_id: str,
    view: ActivityView = "performed",
    q: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(hr_admin),
):
    return employee_profile_service.get_activity(db, user_id, view, q, page, limit)
