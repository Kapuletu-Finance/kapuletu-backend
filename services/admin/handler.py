import json
import logging
from typing import Dict, Any
from common.database import SessionLocal
from common.decorators import with_auth
from services.admin.analytics_service import AnalyticsService
from services.admin.user_service import UserService
from services.admin.ai_governance_service import AIGovernanceService
from services.admin.finance_service import FinanceService
from services.admin.crm_service import CRMService
from services.admin.audit_service import AuditService

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

@with_auth(role_required=["admin", "super_admin"])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Entry Point for the KapuLetu Admin Governance API.
    Dispatches requests to specialized services for platform oversight.
    """
    db = SessionLocal()
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "GET")
        path_params = event.get("pathParameters", {})
        query_params = event.get("queryStringParameters", {}) or {}
        
        logger.info(f"Admin API Request: {method} {path}")
        
        # --- Route Dispatching ---
        
        # Module A: Platform Intelligence
        if path.endswith("/overview") and method == "GET":
            service = AnalyticsService(db)
            return response(200, service.get_platform_overview())

        # Module B: User Lifecycle & Support
        user_service = UserService(db)
        
        if path.endswith("/users/treasurers") and method == "GET":
            status = query_params.get("status")
            page = int(query_params.get("page", 1))
            return response(200, user_service.list_treasurers(page=page, status=status))

        # Endpoints with {user_id} proxy
        if "/users/treasurers/" in path:
            # Simple extraction for local bridge
            parts = path.split("/")
            user_id = parts[parts.index("treasurers") + 1] if "treasurers" in parts else None
            
            if not user_id: return response(400, {"error": "Missing User ID"})

            if path.endswith(user_id) and method == "GET":
                data = user_service.get_treasurer_details(user_id)
                return response(200, data) if data else response(404, {"error": "User not found"})
            
            if path.endswith("/groups") and method == "GET":
                return response(200, user_service.get_user_groups(user_id))

            if path.endswith("/status") and method == "POST":
                body = json.loads(event.get("body", "{}"))
                new_status = body.get("status") == "active"
                reason = body.get("reason")
                success = user_service.update_user_status(user_id, new_status, reason)
                return response(200, {"message": "Status updated"}) if success else response(404, {"error": "User not found"})

            if path.endswith(user_id) and method == "PATCH":
                body = json.loads(event.get("body", "{}"))
                success = user_service.escalated_update(user_id, body)
                return response(200, {"message": "Profile updated"}) if success else response(404, {"error": "User not found"})

        # Module C: AI Parser Governance
        ai_service = AIGovernanceService(db)

        if path.endswith("/ai/parser/feedback-queue") and method == "GET":
            return response(200, ai_service.get_feedback_queue())

        if "/ai/parser/feedback-queue/" in path and method == "POST":
            parts = path.split("/")
            feedback_id = parts[parts.index("feedback-queue") + 1]
            body = json.loads(event.get("body", "{}"))
            approved = body.get("approve", True)
            success = ai_service.approve_feedback(feedback_id, event["user_id"], approved)
            return response(200, {"message": "Feedback reviewed"}) if success else response(404, {"error": "Feedback ID not found"})

        if path.endswith("/ai/parser/training-data") and method == "GET":
            return response(200, ai_service.get_training_pool())

        if path.endswith("/ai/parser/training-data") and method == "POST":
            body = json.loads(event.get("body", "{}"))
            sample_id = ai_service.add_training_sample(body["text"], body["ground_truth"])
            return response(201, {"message": "Sample added", "id": sample_id})

        if path.endswith("/ai/parser/train") and method == "POST":
            body = json.loads(event.get("body", "{}"))
            epochs = body.get("epochs", 10)
            return response(202, ai_service.trigger_training(epochs=epochs))

        if path.endswith("/ai/parser/config") and method == "GET":
            return response(200, ai_service.get_config())

        if path.endswith("/ai/parser/config") and method == "POST":
            body = json.loads(event.get("body", "{}"))
            ai_service.update_config(body)
            return response(200, {"message": "AI configuration updated"})

        # Module D: Subscription Revenue & Plans
        finance_service = FinanceService(db)

        if path.endswith("/finance/plans") and method == "GET":
            return response(200, finance_service.list_plans())

        if path.endswith("/finance/plans") and method == "POST":
            body = json.loads(event.get("body", "{}"))
            plan_id = finance_service.create_plan(body)
            return response(201, {"message": "Plan created", "id": plan_id})

        if path.endswith("/finance/payments") and method == "GET":
            page = int(query_params.get("page", 1))
            return response(200, finance_service.list_all_payments(page=page))

        if path.endswith("/finance/payments/override") and method == "POST":
            body = json.loads(event.get("body", "{}"))
            success = finance_service.manual_override_subscription(
                body["user_id"], body["plan_id"], body.get("duration", 30)
            )
            return response(200, {"message": "Override applied"}) if success else response(400, {"error": "Override failed"})

        # Module E: CRM & System Communications
        crm_service = CRMService(db)

        if path.endswith("/crm/broadcast") and method == "POST":
            body = json.loads(event.get("body", "{}"))
            result = crm_service.send_broadcast(body["message"], body.get("channels", ["sms"]))
            return response(200, result)

        if path.endswith("/crm/tickets") and method == "GET":
            status = query_params.get("status", "open")
            return response(200, crm_service.list_tickets(status=status))

        if "/crm/tickets/" in path and method == "PATCH":
            parts = path.split("/")
            ticket_id = parts[parts.index("tickets") + 1]
            body = json.loads(event.get("body", "{}"))
            success = crm_service.update_ticket(ticket_id, event["user_id"], body)
            return response(200, {"message": "Ticket updated"}) if success else response(404, {"error": "Ticket not found"})

        # Module F: Forensic Audit & Forensics
        audit_service = AuditService(db)

        if path.endswith("/audit/logs") and method == "GET":
            filters = {
                "actor_id": query_params.get("actor_id"),
                "entity_type": query_params.get("entity_type"),
                "action": query_params.get("action"),
                "query": query_params.get("q"),
                "page": query_params.get("page", 1),
                "limit": query_params.get("limit", 50)
            }
            return response(200, audit_service.search_logs(filters))

        # Default Catch-All
        return response(404, {
            "error": "NOT_FOUND",
            "message": f"The admin endpoint {method} {path} does not exist."
        })

    except Exception as e:
        logger.error(f"ADMIN_HANDLER_ERROR: {str(e)}")
        return response(500, {"error": "INTERNAL_SERVER_ERROR", "message": str(e)})
    finally:
        db.close()

def response(status_code: int, body: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": True,
        },
        "body": json.dumps(body)
    }
