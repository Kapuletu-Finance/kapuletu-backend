from models import User
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user, get_admin_user
from services.admin.analytics_service import AnalyticsService
from services.admin.user_service import UserService
from services.admin.ai_governance_service import AIGovernanceService
from services.admin.finance_service import FinanceService
from services.admin.crm_service import CRMService
from services.admin.audit_service import AuditService as AdminAuditService
from services.admin.analytics_engine import FinancialAnalyticsEngine
from services.admin.performance_service import PerformanceService
from fastapi.responses import StreamingResponse
import io
import datetime

router = APIRouter(prefix="/admin", tags=["11. Admin & Governance"])

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
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = FinanceService(db)
    plan_id = payload.get("plan_id")
    if not plan_id:
        raise HTTPException(status_code=400, detail="Missing plan_id in payload")
        
    success = service.manual_override_subscription(identifier, plan_id, payload.get("duration", 30), payload.get("is_trial", False))
    if not success:
        raise HTTPException(status_code=400, detail="Override failed")
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
@router.get("/finance/analytics/health-metrics", summary="Get Financial Health Metrics")
async def get_health_metrics(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    engine = FinancialAnalyticsEngine(db)
    return engine.get_health_metrics()

@router.get("/finance/analytics/revenue-flow", summary="Get Revenue Flow Time-Series")
async def get_revenue_flow(
    interval: str = Query("month", description="week or month"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    engine = FinancialAnalyticsEngine(db)
    return engine.get_revenue_flow(interval=interval)

@router.get("/finance/analytics/cohorts", summary="Get Cohort Retention")
async def get_cohort_retention(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    engine = FinancialAnalyticsEngine(db)
    return engine.get_cohort_retention()

@router.get("/finance/analytics/export", summary="Export Financial Data")
async def export_financial_data(
    format: str = Query("csv", description="Export format (csv, excel, pdf)"),
    start_date: str = Query(None, description="Start date in ISO format"),
    end_date: str = Query(None, description="End date in ISO format"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    engine = FinancialAnalyticsEngine(db)
    
    parsed_start = datetime.datetime.fromisoformat(start_date) if start_date else None
    parsed_end = datetime.datetime.fromisoformat(end_date) if end_date else None
    
    file_data, mime_type = engine.generate_export(
        start_date=parsed_start, 
        end_date=parsed_end, 
        format=format
    )
    
    extension = "csv"
    if format == "excel":
        extension = "xlsx"
    elif format == "pdf":
        extension = "pdf"
        
    filename = f"financial_export_{datetime.datetime.utcnow().strftime('%Y%m%d')}.{extension}"
    
    # Return as downloadable file
    response = StreamingResponse(iter([file_data]), media_type=mime_type)
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

@router.get("/finance/plans", summary="List Subscription Plans")
async def list_plans(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = FinanceService(db)
    return service.list_plans()

@router.get("/finance/plans/{plan_id}", summary="Get Subscription Plan Details")
async def get_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = FinanceService(db)
    plan = service.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan

@router.patch("/finance/plans/{plan_id}", summary="Update Subscription Plan")
async def update_plan(
    plan_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = FinanceService(db)
    success = service.update_plan(plan_id, payload)
    if not success:
        raise HTTPException(status_code=404, detail="Plan not found or update failed")
    return {"message": "Plan updated successfully"}

@router.post("/finance/plans", summary="Create Subscription Plan")
async def create_plan(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = FinanceService(db)
    plan_id = service.create_plan(payload)
    return {"message": "Plan created", "id": plan_id}

@router.post("/finance/payments/{payment_id}/refund", summary="Process Refund")
async def process_refund(
    payment_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = FinanceService(db)
    reason = payload.get("reason", "")
    success = service.process_refund(payment_id, reason)
    if not success:
        raise HTTPException(status_code=400, detail="Could not process refund (invalid payment or already refunded)")
    return {"message": "Refund processed"}

@router.get("/finance/payments", summary="List All Payments")
async def list_payments(
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = FinanceService(db)
    return service.list_all_payments(page=page)

@router.post("/finance/payments/override", summary="Manual Override Subscription")
async def override_subscription(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = FinanceService(db)
    if "user_id" not in payload or "plan_id" not in payload:
        raise HTTPException(status_code=400, detail="Missing user_id or plan_id")
    success = service.manual_override_subscription(
        payload["user_id"], payload["plan_id"], payload.get("duration", 30), payload.get("is_trial", False)
    )
    if not success:
        raise HTTPException(status_code=400, detail="Override failed")
    return {"message": "Override applied"}

# --- Module E: CRM & System Communications ---
@router.post("/crm/broadcast", summary="Send Broadcast Message")
async def send_broadcast(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    service = CRMService(db)
    if "message" not in payload:
        raise HTTPException(status_code=400, detail="Missing message")
    if "title" not in payload:
        raise HTTPException(status_code=400, detail="Missing title")
        
    result = service.send_broadcast(
        title=payload["title"],
        message=payload["message"],
        target_audience=payload.get("target_type", "all_members"),
        channels=payload.get("channels", ["in_app"]),
        target_emails=payload.get("target_emails"),
        background_tasks=background_tasks
    )
    return result

@router.get("/crm/broadcasts", summary="List Broadcast Campaigns")
async def list_broadcasts(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from models.broadcast import BroadcastCampaign
    campaigns = db.query(BroadcastCampaign).order_by(BroadcastCampaign.created_at.desc()).all()
    
    return [
        {
            "id": str(c.campaign_id),
            "title": c.title,
            "target_audience": c.target_audience,
            "channels": c.channels,
            "status": c.status,
            "recipients_count": c.recipients_count,
            "created_at": c.created_at.isoformat()
        } for c in campaigns
    ]

@router.get("/crm/broadcasts/{campaign_id}/recipients", summary="List Recipients for a Broadcast")
async def get_broadcast_recipients(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from models.communication_logs import CommunicationLog
    from models.users import User
    
    logs = db.query(CommunicationLog, User).outerjoin(
        User, CommunicationLog.user_id == User.user_id
    ).filter(
        CommunicationLog.campaign_id == campaign_id
    ).order_by(CommunicationLog.created_at.desc()).all()
    
    return [
        {
            "log_id": str(log.CommunicationLog.log_id),
            "user_name": f"{log.User.first_name} {log.User.last_name}" if log.User else "Unknown",
            "channel": log.CommunicationLog.channel,
            "destination": log.CommunicationLog.destination,
            "status": log.CommunicationLog.status,
            "error_message": log.CommunicationLog.error_message,
            "created_at": log.CommunicationLog.created_at.isoformat()
        } for log in logs
    ]

@router.get("/crm/communication-logs", summary="List All Communication Logs")
async def list_communication_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from models.communication_logs import CommunicationLog
    
    total = db.query(CommunicationLog).count()
    logs = db.query(CommunicationLog, User).outerjoin(
        User, CommunicationLog.user_id == User.user_id
    ).order_by(CommunicationLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "logs": [
            {
                "log_id": str(log.CommunicationLog.log_id),
                "user_name": f"{log.User.first_name} {log.User.last_name}" if log.User else "System / Non-User",
                "channel": log.CommunicationLog.channel,
                "destination": log.CommunicationLog.destination,
                "subject": log.CommunicationLog.subject,
                "status": log.CommunicationLog.status,
                "error_message": log.CommunicationLog.error_message,
                "created_at": log.CommunicationLog.created_at.isoformat()
            } for log in logs
        ]
    }

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

# --- Module: Email Templates Preview ---
from fastapi.responses import HTMLResponse

@router.get("/templates/preview/{name}", summary="Preview Email Template")
async def preview_template(
    name: str,
    message: str = "This is a live preview of the message you just typed. It shows how it will appear within the KapuLetu email branding.",
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from services.notifications.templates.render import render_email_template
    
    # Inject safe dummy variables
    invite_url = "https://kapuletu.co.ke/sign-up?invite_token=preview-token-12345"
    
    try:
        html_body = render_email_template(
            name,
            message=message.replace('\n', '<br>'),
            invite_url=invite_url
        )
        return HTMLResponse(content=html_body)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Template error: {str(e)}")

import os

@router.get("/templates", summary="List Email Templates")
async def list_templates(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from services.notifications.templates.render import TEMPLATE_DIR
    try:
        files = [f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".html")]
        return {"templates": [{"id": f, "name": f.replace(".html", "").replace("_", " ").title()} for f in files]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read templates: {str(e)}")

@router.get("/templates/raw/{name}", summary="Get Raw Email Template")
async def get_raw_template(
    name: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from services.notifications.templates.render import TEMPLATE_DIR
    path = os.path.join(TEMPLATE_DIR, name)
    if not os.path.exists(path) or not name.endswith(".html"):
        raise HTTPException(status_code=404, detail="Template not found")
        
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"name": name, "content": content}

@router.put("/templates/raw/{name}", summary="Save Raw Email Template")
async def save_raw_template(
    name: str,
    payload: Dict[str, str],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    from services.notifications.templates.render import TEMPLATE_DIR
    path = os.path.join(TEMPLATE_DIR, name)
    if not os.path.exists(path) or not name.endswith(".html"):
        raise HTTPException(status_code=404, detail="Template not found")
        
    content = payload.get("content")
    if content is None:
        raise HTTPException(status_code=400, detail="Missing content")
        
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"message": "Template saved successfully"}

