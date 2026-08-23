from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user
from services.admin.analytics_service import AnalyticsService
from services.admin.user_service import UserService
from services.admin.ai_governance_service import AIGovernanceService
from services.admin.finance_service import FinanceService
from services.admin.crm_service import CRMService
from services.admin.audit_service import AuditService as AdminAuditService

router = APIRouter(prefix="/admin", tags=["11. Admin & Governance"])

# --- Module A: Platform Intelligence ---
@router.get("/overview", summary="Global Platform Intelligence")
async def get_overview(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user) # In reality, restrict to admin role
):
    service = AnalyticsService(db)
    return service.get_platform_overview()

# --- Module B: User Lifecycle & Support ---
@router.get("/users/activity", summary="Recent and Active Users")
async def get_user_activity(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = UserService(db)
    return service.get_recent_activity()

@router.get("/users/treasurers", summary="List Treasurers")
async def list_treasurers(
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = UserService(db)
    return service.list_treasurers(page=page, limit=limit, status=status, q=q)

@router.get("/users/treasurers/{identifier}", summary="Get Treasurer Details")
async def get_treasurer_details(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
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
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = UserService(db)
    return service.get_user_groups(identifier)

@router.post("/users/treasurers/{identifier}/status", summary="Update User Status")
async def update_user_status(
    identifier: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = UserService(db)
    new_status = payload.get("status") == "active"
    reason = payload.get("reason")
    success = service.update_user_status(identifier, new_status, reason)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Status updated"}

@router.patch("/users/treasurers/{identifier}", summary="Escalated Profile Update")
async def escalated_update(
    identifier: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = UserService(db)
    success = service.escalated_update(identifier, payload)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Profile updated"}

@router.patch("/users/treasurers/{identifier}/role", summary="Upgrade User Role")
async def upgrade_user_role(
    identifier: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = UserService(db)
    new_role = payload.get("role")
    if not new_role:
        raise HTTPException(status_code=400, detail="Missing role in payload")
        
    try:
        success = service.upgrade_user_role(identifier, new_role)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": f"User upgraded to {new_role}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/users/treasurers/{identifier}/plan", summary="Upgrade User Plan")
async def upgrade_user_plan(
    identifier: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = FinanceService(db)
    plan_id = payload.get("plan_id")
    if not plan_id:
        raise HTTPException(status_code=400, detail="Missing plan_id in payload")
        
    success = service.manual_override_subscription(identifier, plan_id, payload.get("duration", 30))
    if not success:
        raise HTTPException(status_code=400, detail="Override failed")
    return {"message": "User plan upgraded successfully"}

@router.get("/users/treasurers/{identifier}/activity", summary="Get User Activity Log")
async def get_user_activity(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = UserService(db)
    return service.get_user_recent_activity(identifier)

# --- Module C: AI Parser Governance ---
@router.get("/ai/parser/feedback-queue", summary="Get AI Feedback Queue")
async def get_feedback_queue(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = AIGovernanceService(db)
    return service.get_feedback_queue()

@router.post("/ai/parser/feedback-queue/{feedback_id}", summary="Approve AI Feedback")
async def approve_feedback(
    feedback_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
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
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = AIGovernanceService(db)
    return service.get_training_pool()

@router.post("/ai/parser/training-data", summary="Inject Manual Training Sample")
async def add_training_sample(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
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
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = AIGovernanceService(db)
    epochs = payload.get("epochs", 10)
    return service.trigger_training(epochs=epochs)

@router.get("/ai/parser/config", summary="Get AI Config")
async def get_config(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = AIGovernanceService(db)
    return service.get_config()

@router.post("/ai/parser/config", summary="Update AI Config")
async def update_config(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = AIGovernanceService(db)
    service.update_config(payload)
    return {"message": "AI configuration updated"}

# --- Module D: Subscription Revenue & Plans ---
@router.get("/finance/plans", summary="List Subscription Plans")
async def list_plans(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = FinanceService(db)
    return service.list_plans()

@router.post("/finance/plans", summary="Create Subscription Plan")
async def create_plan(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = FinanceService(db)
    plan_id = service.create_plan(payload)
    return {"message": "Plan created", "id": plan_id}

@router.get("/finance/payments", summary="List All Payments")
async def list_payments(
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = FinanceService(db)
    return service.list_all_payments(page=page)

@router.post("/finance/payments/override", summary="Manual Override Subscription")
async def override_subscription(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = FinanceService(db)
    if "user_id" not in payload or "plan_id" not in payload:
        raise HTTPException(status_code=400, detail="Missing user_id or plan_id")
    success = service.manual_override_subscription(
        payload["user_id"], payload["plan_id"], payload.get("duration", 30)
    )
    if not success:
        raise HTTPException(status_code=400, detail="Override failed")
    return {"message": "Override applied"}

# --- Module E: CRM & System Communications ---
@router.post("/crm/broadcast", summary="Send Broadcast Message")
async def send_broadcast(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = CRMService(db)
    if "message" not in payload:
        raise HTTPException(status_code=400, detail="Missing message")
    result = service.send_broadcast(payload["message"], payload.get("channels", ["sms"]))
    return result

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
    current_user: Dict[str, Any] = Depends(get_verified_user)
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
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = CRMService(db)
    return service.list_tickets(status=status)

@router.get("/crm/tickets/{ticket_id}", summary="Get Support Ticket Details")
async def get_ticket_details(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
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
    current_user: Dict[str, Any] = Depends(get_verified_user)
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
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = CRMService(db)
    if "message" not in payload:
        raise HTTPException(status_code=400, detail="Missing message")
    success = service.reply_to_ticket(ticket_id, current_user.get("sub"), payload["message"])
    if not success:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"message": "Reply sent successfully"}


