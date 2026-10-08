"""
Admin view and control of one internal employee: profile, access changes, account status,
sessions and a unified activity feed (what they did, what was done to them, their sign-ins).
"""
import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from common.utils import parse_uuid
from models.audit_log import AuditLog
from models.employees import EmployeeAuditLog
from models.hr import EmployeeReport
from models.users import User
from services.admin.employee_profile_schemas import (
    ActivityItemOut, ActivityPageOut, EmployeeProfileOut, EmployeeUpdateIn,
)
from services.audit.service import AuditService
from services.hr.directory import full_name, get_employee_or_404
from services.notifications.service import create_notification

LOGIN_ACTIONS = ("USER_LOGIN",)
# Upper bound per source when building the merged feed; per-employee volumes stay well below this.
FEED_SCAN_LIMIT = 2000


def _employee(db: Session, user_id) -> User:
    return get_employee_or_404(db, user_id, include_inactive=True)


def _assert_not_self(actor_id, employee: User, action: str) -> None:
    if str(employee.user_id) == str(actor_id):
        raise HTTPException(status_code=400, detail=f"You can't {action} your own account.")


def _audit(db: Session, actor_id, employee: User, action: str, message: str, **details) -> None:
    AuditService(db).log_action(
        actor_id=actor_id, action=action, entity_type="USER", entity_id=str(employee.user_id),
        details={"message": message, **details},
    )


def _notify(db: Session, employee: User, message: str) -> None:
    create_notification(
        db=db, user_id=str(employee.user_id), title="Your account was updated", message=message,
        type="account_updated",
    )


# --- Profile ---

def get_profile(db: Session, user_id) -> EmployeeProfileOut:
    employee = _employee(db, user_id)
    last_login = db.query(func.max(AuditLog.created_at)).filter(
        AuditLog.actor_id == employee.user_id, AuditLog.action.in_(LOGIN_ACTIONS)
    ).scalar()
    report_counts = dict(
        db.query(EmployeeReport.status, func.count()).filter(
            EmployeeReport.user_id == employee.user_id, EmployeeReport.clock_in_time.isnot(None)
        ).group_by(EmployeeReport.status).all()
    )
    return EmployeeProfileOut(
        user_id=employee.user_id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email,
        phone_number=employee.phone_number,
        role=employee.role,
        permissions=employee.permissions or [],
        is_active=employee.is_active is not False and employee.deleted_at is None,
        created_at=employee.created_at,
        last_login_at=last_login,
        last_active_at=employee.last_active_at,
        current_action=employee.current_action,
        two_factor_enabled=bool(employee.two_factor_enabled),
        sessions_revoked_at=employee.sessions_revoked_at,
        reports_pending=report_counts.get("pending_review", 0),
        reports_confirmed=report_counts.get("confirmed", 0),
    )


def update_employee(db: Session, user_id, payload: EmployeeUpdateIn, actor_id) -> EmployeeProfileOut:
    """Edits name, phone, role and permissions; the diff is audited and the employee notified."""
    employee = _employee(db, user_id)
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if ("role" in changes or "permissions" in changes) and str(employee.user_id) == str(actor_id):
        raise HTTPException(status_code=400, detail="You can't change your own role or permissions.")
    if "phone_number" in changes and changes["phone_number"] != employee.phone_number:
        taken = db.query(User.user_id).filter(
            User.phone_number == changes["phone_number"], User.user_id != employee.user_id
        ).first()
        if taken:
            raise HTTPException(status_code=409, detail="That phone number belongs to another account.")

    def differs(field, old, new):
        return set(old or []) != set(new) if field == "permissions" else old != new

    diff = {
        field: [getattr(employee, field), value]
        for field, value in changes.items()
        if differs(field, getattr(employee, field), value)
    }
    if not diff:
        return get_profile(db, employee.user_id)

    for field, (_, value) in diff.items():
        setattr(employee, field, value)
    db.commit()

    labels = {"first_name": "first name", "last_name": "last name", "phone_number": "phone number",
              "role": "role", "permissions": "access permissions"}
    changed = ", ".join(labels[f] for f in diff)
    _audit(db, actor_id, employee, "EMPLOYEE_UPDATED",
           f"Updated {full_name(employee)}'s {changed}", changes=diff)
    _notify(db, employee, f"An administrator updated your {changed}.")
    return get_profile(db, employee.user_id)


# --- Account status & sessions ---

def set_suspended(db: Session, user_id, suspended: bool, actor_id) -> EmployeeProfileOut:
    employee = _employee(db, user_id)
    if suspended:
        _assert_not_self(actor_id, employee, "suspend")
        employee.is_active = False
        # End every active session immediately, not just future sign-ins.
        employee.sessions_revoked_at = datetime.datetime.utcnow()
    else:
        employee.is_active = True
        employee.deleted_at = None  # also restores accounts revoked by the old one-way flow
    db.commit()

    verb = "Suspended" if suspended else "Restored"
    _audit(db, actor_id, employee, "EMPLOYEE_SUSPENDED" if suspended else "EMPLOYEE_RESTORED",
           f"{verb} {full_name(employee)}'s account")
    if not suspended:
        _notify(db, employee, "Your account has been restored. You can sign in again.")
    return get_profile(db, employee.user_id)


def sign_out_everywhere(db: Session, user_id, actor_id) -> EmployeeProfileOut:
    employee = _employee(db, user_id)
    employee.sessions_revoked_at = datetime.datetime.utcnow()
    db.commit()
    _audit(db, actor_id, employee, "EMPLOYEE_SIGNED_OUT", f"Signed {full_name(employee)} out of all sessions")
    return get_profile(db, employee.user_id)


def send_password_reset(db: Session, user_id, actor_id) -> None:
    from services.auth.auth_service import auth_service

    employee = _employee(db, user_id)
    if employee.is_active is False:
        raise HTTPException(status_code=400, detail="Restore this account before sending a password reset.")
    auth_service.forgot_password(db=db, username=employee.email)
    _audit(db, actor_id, employee, "EMPLOYEE_PASSWORD_RESET_SENT",
           f"Sent a password reset code to {full_name(employee)} ({employee.email})")


# --- Activity feed ---

def _humanize(action: str) -> str:
    return action.replace("_", " ").capitalize()


def get_activity(
    db: Session, user_id, view: str, q: Optional[str] = None, page: int = 1, limit: int = 25
) -> ActivityPageOut:
    """
    performed: actions the employee took (excluding sign-ins)
    received:  actions others took on the employee's account or records (both audit tables)
    logins:    the employee's sign-ins
    """
    employee = _employee(db, user_id)
    uid = employee.user_id
    uid_str = str(uid)

    audit_query = db.query(AuditLog)
    if view == "logins":
        audit_query = audit_query.filter(AuditLog.actor_id == uid, AuditLog.action.in_(LOGIN_ACTIONS))
    elif view == "performed":
        audit_query = audit_query.filter(AuditLog.actor_id == uid, AuditLog.action.notin_(LOGIN_ACTIONS))
    else:
        audit_query = audit_query.filter(
            or_(AuditLog.entity_id == uid_str, AuditLog.entity_id.like(f"{uid_str}:%")),
            or_(AuditLog.actor_id.is_(None), AuditLog.actor_id != uid),
        )
    rows = [
        (f"a-{log.log_id}", log.created_at, log.action, (log.details or {}).get("message"), log.actor_id)
        for log in audit_query.order_by(AuditLog.created_at.desc()).limit(FEED_SCAN_LIMIT)
    ]

    # The older employee-admin log records invites/revocations: by the admin (employee_id) on a resource.
    if view != "logins":
        legacy = db.query(EmployeeAuditLog)
        legacy = legacy.filter(
            EmployeeAuditLog.employee_id == uid if view == "performed" else EmployeeAuditLog.resource_id == uid_str
        )
        rows += [
            (f"e-{log.log_id}", log.timestamp, log.action_type, None, log.employee_id)
            for log in legacy.order_by(EmployeeAuditLog.timestamp.desc()).limit(FEED_SCAN_LIMIT)
        ]

    actor_ids = {r[4] for r in rows if r[4]}
    names = (
        {u.user_id: full_name(u) for u in db.query(User).filter(User.user_id.in_(actor_ids))}
        if actor_ids else {}
    )

    items = [
        ActivityItemOut(
            id=row_id, at=at, action=action, message=message or _humanize(action),
            actor_id=actor, actor_name=names.get(actor),
        )
        for row_id, at, action, message, actor in rows
        if at is not None
    ]
    if q:
        needle = q.lower()
        items = [i for i in items if needle in i.message.lower() or needle in i.action.lower()]
    items.sort(key=lambda i: i.at, reverse=True)

    start = (page - 1) * limit
    return ActivityPageOut(items=items[start:start + limit], total=len(items), page=page, limit=limit)
