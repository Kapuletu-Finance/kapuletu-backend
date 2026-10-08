from models import User
from typing import Dict, Any, Optional
from common.utils import parse_uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user, get_admin_user, require_role, require_permissions
from common.enums import UserRole
from services.admin.analytics_service import AnalyticsService
from services.admin.user_service import UserService
from services.admin.ai_governance_service import AIGovernanceService
from services.admin.finance import FinanceError, SubscriptionService
from services.admin.finance_schemas import SubscriptionOverrideIn
from services.admin.crm_service import CRMService
from services.admin.audit_service import AuditService as AdminAuditService
from services.admin.performance_service import PerformanceService
from fastapi.responses import StreamingResponse
import io
import datetime

router = APIRouter(prefix="/admin", tags=["11. Admin & Governance"])

# Everything that reads revenue or moves money/entitlements requires the finance permission.
finance_officer = require_permissions(["manage_finance"])


def _finance_http_error(e: FinanceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))

# --- Module A: Platform Intelligence ---
@router.get("/overview", summary="Global Platform Intelligence")
async def get_overview(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user) # In reality, restrict to admin role
):
    service = AnalyticsService(db)
    return service.get_platform_overview()

# --- Module A2: Platform Performance ---
@router.get("/performance/health", summary="Get System Health KPIs")
async def get_system_health(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = PerformanceService(db)
    return service.get_system_health()

@router.get("/performance/activity-trend", summary="Get Activity Trend")
async def get_activity_trend(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = PerformanceService(db)
    return service.get_activity_trend()

@router.get("/performance/active-users", summary="Get Detailed Active Users")
async def get_extended_active_users(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = PerformanceService(db)
    return service.get_extended_active_users()

@router.get("/performance/events", summary="Get System Events Log")
async def get_system_events(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = PerformanceService(db)
    return service.get_system_events()

# --- Module B: User Lifecycle & Support ---
@router.get("/users/activity", summary="Recent and Active Users")
async def get_user_activity(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    return service.get_recent_activity()

@router.get("/users/treasurers", summary="List Users")
async def list_users(
    status: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    viewer_role = current_user.get("role", "admin")
    return service.list_users(viewer_role=viewer_role, page=page, limit=limit, status=status, q=q, role=role)

@router.get("/users/treasurers/{identifier}", summary="Get Treasurer Details")
async def get_treasurer_details(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    data = service.get_treasurer_details(identifier)
    if not data:
        raise HTTPException(status_code=404, detail="User not found")
    return data

@router.get("/users/treasurers/{identifier}/groups", summary="Get User Groups")
async def get_user_groups(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    return service.get_user_groups(identifier)

@router.post("/users/treasurers/{identifier}/status", summary="Update User Status")
async def update_user_status(
    identifier: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    new_status = payload.get("status") == "active"
    reason = payload.get("reason")
    success = service.update_user_status(identifier, new_status, current_user.get("sub"), reason)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Status updated"}

@router.patch("/users/treasurers/{identifier}", summary="Escalated Profile Update")
async def escalated_update(
    identifier: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    success = service.escalated_update(identifier, payload, current_user.get("sub"))
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Profile updated"}

@router.get("/users/whatsapp-blocklist", summary="Get WhatsApp Blocklist")
async def get_whatsapp_blocklist(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    return service.get_whatsapp_blocklist(page, limit, search)

@router.post("/users/whatsapp-blocklist/{phone_number}/unblock", summary="Unblock WhatsApp Number")
async def unblock_whatsapp_number(
    phone_number: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    try:
        return service.unblock_whatsapp_number(phone_number)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.patch("/users/treasurers/{identifier}/role", summary="Upgrade User Role")
async def upgrade_user_role(
    identifier: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    new_role = payload.get("role")
    if not new_role:
        raise HTTPException(status_code=400, detail="Missing role in payload")
        
    try:
        success = service.upgrade_user_role(identifier, new_role, current_user.get("sub"))
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": f"User upgraded to {new_role}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/users/treasurers/{identifier}/reset-password", summary="Trigger Password Reset")
async def trigger_password_reset(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    success = service.trigger_password_reset(identifier, current_user.get("sub"))
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Password reset initiated"}

@router.post("/users/treasurers/{identifier}/resend-code", summary="Resend Verification Code")
async def resend_verification_code(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    success = service.resend_verification_code(identifier, current_user.get("sub"))
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Verification code resent"}

@router.delete("/users/treasurers/{identifier}", summary="Delete User (Soft/Hard)")
async def delete_user(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can delete users")
        
    service = UserService(db)
    result = service.delete_user(identifier, current_user.get("sub"))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("reason", "User not found"))
    
    return {"message": f"User deleted successfully via {result.get('type')}"}

@router.post("/auth/verify-pin", summary="Verify Admin PIN for Secure Wrapper")
async def verify_admin_pin(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    pin = payload.get("pin")
    if not pin:
        raise HTTPException(status_code=401, detail="PIN is required")
        
    from models.system_config import SystemConfig
    config = db.query(SystemConfig).filter(SystemConfig.config_key == "admin_pin").first()
    expected_pin = config.config_value.get("pin") if config else "123456"
    
    if pin != expected_pin:
        raise HTTPException(status_code=401, detail="Invalid PIN")
        
    return {"message": "PIN verified", "token": "temp_secure_token_123"}

@router.post("/auth/set-pin", summary="Set Admin PIN for Secure Wrapper")
async def set_admin_pin(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can set the PIN")
        
    new_pin = payload.get("pin")
    if not new_pin or len(new_pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 characters")
        
    from models.system_config import SystemConfig
    config = db.query(SystemConfig).filter(SystemConfig.config_key == "admin_pin").first()
    
    if config:
        config.config_value = {"pin": new_pin}
    else:
        config = SystemConfig(config_key="admin_pin", config_value={"pin": new_pin})
        db.add(config)
        
    db.commit()
    return {"message": "Admin PIN updated successfully"}

@router.post("/users/treasurers/{identifier}/plan", summary="Upgrade User Plan")
async def upgrade_user_plan(
    identifier: str,
    payload: SubscriptionOverrideIn,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(finance_officer)
):
    try:
        SubscriptionService(db).grant(
            identifier, payload.plan_id, payload.duration, payload.is_trial,
            actor_id=current_user.get("user_id"), reason=payload.reason,
        )
    except FinanceError as e:
        raise _finance_http_error(e)
    return {"message": "User plan upgraded successfully"}

@router.get("/users/treasurers/{identifier}/activity", summary="Get User Activity Log")
async def get_user_activity(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    return service.get_user_recent_activity(identifier)

# --- Module C: AI Parser Governance ---
@router.get("/ai/parser/feedback-queue", summary="Get AI Feedback Queue")
async def get_feedback_queue(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = AIGovernanceService(db)
    return service.get_feedback_queue()

@router.post("/ai/parser/feedback-queue/{feedback_id}", summary="Approve AI Feedback")
async def approve_feedback(
    feedback_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = AIGovernanceService(db)
    approved = payload.get("approve", True)
    success = service.approve_feedback(feedback_id, current_user.get("sub"), approved)
    if not success:
        raise HTTPException(status_code=404, detail="Feedback ID not found")
    return {"message": "Feedback reviewed"}

@router.get("/ai/parser/training-data", summary="Get AI Training Pool")
async def get_training_pool(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = AIGovernanceService(db)
    return service.get_training_pool()

@router.post("/ai/parser/training-data", summary="Inject Manual Training Sample")
async def add_training_sample(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = AIGovernanceService(db)
    if "text" not in payload or "ground_truth" not in payload:
        raise HTTPException(status_code=400, detail="Missing text or ground_truth")
    sample_id = service.add_training_sample(payload["text"], payload["ground_truth"])
    return {"message": "Sample added", "id": sample_id}

@router.post("/ai/parser/train", summary="Trigger AI Retraining")
async def trigger_training(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = AIGovernanceService(db)
    epochs = payload.get("epochs", 10)
    return service.trigger_training(epochs=epochs)

@router.get("/ai/parser/config", summary="Get AI Config")
async def get_config(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = AIGovernanceService(db)
    return service.get_config()

@router.post("/ai/parser/config", summary="Update AI Config")
async def update_config(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = AIGovernanceService(db)
    service.update_config(payload)
    return {"message": "AI configuration updated"}

# --- Module D: Subscription Revenue & Plans ---
# Moved to services/admin/finance/router.py (/admin/finance/*).

# --- Module E: CRM & System Communications ---
# Broadcasts, delivery logs and templates moved to services/communications (/admin/communications/*).

# --- Module F: System & Audit Logs ---
@router.get("/audit/logs", summary="List System & Audit Logs")
async def list_audit_logs(
    actor_id: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = AdminAuditService(db)
    filters = {
        "actor_id": actor_id,
        "entity_type": entity_type,
        "action": action,
        "query": q,
        "page": page,
        "limit": limit
    }
    return service.search_logs(filters)

# --- Module H: System Configurations ---
@router.get("/config/notifications", summary="Get Admin Notification Emails")
async def get_admin_notifications_config(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can access global configuration")
        
    from models.system_config import SystemConfig
    
    keys = ["admin_notification_emails", "admin_notification_emails_hr", "admin_notification_emails_signups", "admin_notification_emails_warnings", "admin_notification_emails_finance"]
    configs = db.query(SystemConfig).filter(SystemConfig.config_key.in_(keys)).all()
    
    response = {
        "emails": [],
        "emails_hr": [],
        "emails_signups": [],
        "emails_warnings": [],
        "emails_finance": []
    }
    
    for config in configs:
        if config.config_key == "admin_notification_emails":
            response["emails"] = config.config_value.get("emails", []) if config.config_value else []
        elif config.config_key == "admin_notification_emails_hr":
            response["emails_hr"] = config.config_value.get("emails", []) if config.config_value else []
        elif config.config_key == "admin_notification_emails_signups":
            response["emails_signups"] = config.config_value.get("emails", []) if config.config_value else []
        elif config.config_key == "admin_notification_emails_warnings":
            response["emails_warnings"] = config.config_value.get("emails", []) if config.config_value else []
        elif config.config_key == "admin_notification_emails_finance":
            response["emails_finance"] = config.config_value.get("emails", []) if config.config_value else []
            
    return response

@router.post("/config/notifications", summary="Set Admin Notification Emails")
async def set_admin_notifications_config(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can modify global configuration")
        
    from models.system_config import SystemConfig
    
    mapping = {
        "emails": "admin_notification_emails",
        "emails_hr": "admin_notification_emails_hr",
        "emails_signups": "admin_notification_emails_signups",
        "emails_warnings": "admin_notification_emails_warnings",
        "emails_finance": "admin_notification_emails_finance",
    }
    
    for key, config_key in mapping.items():
        if key in payload:
            new_emails = payload.get(key, [])
            if not isinstance(new_emails, list):
                raise HTTPException(status_code=400, detail=f"'{key}' must be a list of strings")
                
            config = db.query(SystemConfig).filter(SystemConfig.config_key == config_key).first()
            if config:
                config.config_value = {"emails": new_emails}
            else:
                config = SystemConfig(config_key=config_key, config_value={"emails": new_emails})
                db.add(config)
                
    db.commit()
    return {"message": "Admin notification emails updated"}


@router.get("/crm/tickets", summary="List Support Tickets")
async def list_tickets(
    status: str = Query("open"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = CRMService(db)
    return service.list_tickets(status=status)

@router.get("/crm/tickets/{ticket_id}", summary="Get Support Ticket Details")
async def get_ticket_details(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = CRMService(db)
    details = service.get_ticket_details(ticket_id)
    if not details:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return details

@router.patch("/crm/tickets/{ticket_id}", summary="Update Support Ticket")
async def update_ticket(
    ticket_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = CRMService(db)
    success = service.update_ticket(ticket_id, current_user.get("sub"), payload)
    if not success:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"message": "Ticket updated"}

@router.post("/crm/tickets/{ticket_id}/reply", summary="Admin Reply to Support Ticket")
async def reply_ticket(
    ticket_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = CRMService(db)
    if "message" not in payload:
        raise HTTPException(status_code=400, detail="Missing message")
    success = service.reply_to_ticket(ticket_id, current_user.get("sub"), payload["message"])
    if not success:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"message": "Reply sent successfully"}


from fastapi import APIRouter, Depends, HTTPException, Request

@router.post("/invites", summary="Send Invite(s)")
async def send_invite(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from services.admin.invites_service import InvitesService
    service = InvitesService(db)
    
    emails = payload.get("emails", [])
    email = payload.get("email")
    phone = payload.get("phone_number")
    message = payload.get("message", "Welcome to KapuLetu!")
    
    # Handle bulk
    if emails and isinstance(emails, list):
        count = service.bulk_invite(emails, message=message, sender_id=current_user.get("sub"), background_tasks=background_tasks)
        return {"message": f"{count} invites generated and sent successfully"}
    
    # Handle single
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Provide emails array or a single email/phone number")
    
    token = service.generate_and_send_invite(email=email, phone_number=phone, sender_id=current_user.get("sub"), message=message)
    return {"message": "Invite generated and sent successfully", "token": token}

@router.get("/invites", summary="List Invites")
async def list_invites(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from services.admin.invites_service import InvitesService
    service = InvitesService(db)
    return service.list_invites()

# --- Module G: Waitlist Management ---
@router.get("/users/waitlist", summary="List Waitlisted Users")
async def get_waitlisted_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    return service.list_waitlisted_users(page, limit)

@router.get("/users/waitlist/history", summary="Get Waitlist and Whitelist History")
async def get_waitlist_history(
    limit: int = Query(50),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from models.audit_log import AuditLog
    from models.users import User
    
    # We want actions related to Waitlist and Whitelist
    actions = [
        "Whitelist Added",
        "Whitelist Removed",
        "Whitelist Invite Sent",
        "Waitlist Approved"
    ]
    
    logs = db.query(AuditLog, User).outerjoin(
        User, AuditLog.actor_id == User.user_id
    ).filter(
        AuditLog.action.in_(actions)
    ).order_by(
        AuditLog.created_at.desc()
    ).limit(limit).all()
    
    result = []
    for log, actor in logs:
        result.append({
            "id": str(log.log_id),
            "actor": f"{actor.first_name} {actor.last_name}" if actor else "System",
            "action": log.action,
            "entity_id": log.entity_id,
            "details": log.details,
            "created_at": log.created_at.isoformat() if log.created_at else None
        })
        
    return {"history": result}

@router.post("/users/waitlist/{identifier}/approve", summary="Approve Waitlisted User")
async def approve_waitlisted_user(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    success = service.approve_waitlisted_user(identifier, current_user.get("sub"))
    if not success:
        raise HTTPException(status_code=404, detail="User not found or not on waitlist")
    return {"message": "User approved successfully"}

@router.get("/users/whitelist", summary="List Waitlist Whitelist")
async def get_waitlist_whitelist(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    return service.list_whitelist()

@router.post("/users/whitelist", summary="Add to Whitelist")
async def add_to_whitelist(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    
    phone_number = payload.get("phone_number")
    email = payload.get("email")
    name = payload.get("name")
    description = payload.get("description")
    
    if not phone_number or not email:
        raise HTTPException(status_code=400, detail="Missing phone_number or email (both are required)")
        
    entry_id = service.add_whitelist_entry(phone_number, email, name, description)
    
    from models.audit_log import AuditLog
    from common.utils import parse_uuid
    log = AuditLog(
        actor_id=parse_uuid(current_user["sub"]),
        action="Whitelist Added",
        entity_type="waitlist_whitelist",
        entity_id=entry_id,
        details={"email": email, "phone_number": phone_number, "name": name}
    )
    db.add(log)
    db.commit()
    
    return {"message": "Added to whitelist", "id": entry_id}

@router.post("/users/whitelist/{entry_id}/invite", summary="Send Invite to Whitelisted Person")
async def invite_whitelist_user(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from models.waitlist_whitelist import WaitlistWhitelist
    from services.admin.invites_service import InvitesService
    
    entry = db.query(WaitlistWhitelist).filter(WaitlistWhitelist.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Tester not found")
        
    if not entry.email:
        raise HTTPException(status_code=400, detail="Tester has no email address")
        
    # Send invite
    invite_service = InvitesService(db)
    invite_service.generate_and_send_invite(email=entry.email)
    
    # Update record
    service = UserService(db)
    service.mark_whitelist_invite_sent(entry_id)
    
    # Audit log
    from models.audit_log import AuditLog
    from common.utils import parse_uuid
    log = AuditLog(
        actor_id=parse_uuid(current_user["sub"]),
        action="Whitelist Invite Sent",
        entity_type="waitlist_whitelist",
        entity_id=entry_id,
        details={"email": entry.email, "resend": entry.invite_sent}
    )
    db.add(log)
    db.commit()
    
    return {"message": "Invite sent successfully"}


@router.delete("/users/whitelist/{entry_id}", summary="Remove from Whitelist")
async def remove_from_whitelist(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = UserService(db)
    success = service.remove_whitelist_entry(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
        
    from models.audit_log import AuditLog
    from common.utils import parse_uuid
    log = AuditLog(
        actor_id=parse_uuid(current_user["sub"]),
        action="Whitelist Removed",
        entity_type="waitlist_whitelist",
        entity_id=entry_id,
        details={"removed": True}
    )
    db.add(log)
    db.commit()
    
    return {"message": "Removed from whitelist"}

# --- Contact Messages ---
@router.get("/contact-messages", summary="List Contact Messages")
async def list_contact_messages(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT]))
):
    from models.contact_message import ContactMessage
    messages = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).all()
    
    # Format them for output
    return [{
        "id": str(msg.id),
        "first_name": msg.first_name,
        "last_name": msg.last_name,
        "email": msg.email,
        "topic": msg.topic,
        "message": msg.message,
        "status": msg.status,
        "created_at": msg.created_at.isoformat() + "Z",
        "updated_at": msg.updated_at.isoformat() + "Z"
    } for msg in messages]

@router.patch("/contact-messages/{message_id}/status", summary="Update Contact Message Status")
async def update_contact_message_status(
    message_id: str,
    status: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT]))
):
    from models.contact_message import ContactMessage
    from common.utils import parse_uuid
    
    message = db.query(ContactMessage).filter(ContactMessage.id == parse_uuid(message_id)).first()
    if not message:
        raise HTTPException(status_code=404, detail="Contact message not found")
        
    if status not in ("unread", "read", "resolved"):
        raise HTTPException(status_code=400, detail="status must be unread, read or resolved")
    message.status = status
    db.commit()
    db.refresh(message)
    
    return {"message": "Status updated successfully", "status": message.status}
