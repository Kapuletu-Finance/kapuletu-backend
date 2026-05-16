import json
import logging
from typing import Dict, Any
from common.database import SessionLocal
from services.finance.providers.mpesa import MpesaProvider
from services.finance.providers.flutterwave import FlutterwaveProvider
from services.finance.fulfillment import FulfillmentService
from models.subscription import Plan

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def response(status_code: int, body: Any):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Unified Finance API Handler.
    Routes: /checkout, /webhooks/{provider}, /available-plans, /status/{id}
    """
    db = SessionLocal()
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "GET")
        
        # 1. Available Plans (Public)
        if path.endswith("/available-plans") and method == "GET":
            plans = db.query(Plan).all()
            return response(200, [{"id": str(p.plan_id), "name": p.name, "price": p.price} for p in plans])

        # 2. Checkout (Authenticated - Requires Treasurer)
        if path.endswith("/checkout") and method == "POST":
            body = json.loads(event.get("body", "{}"))
            provider_name = body.get("provider")
            plan_id = body.get("plan_id")
            user_id = event.get("requestContext", {}).get("authorizer", {}).get("claims", {}).get("sub")
            
            # Fetch plan for amount
            plan = db.query(Plan).filter(Plan.plan_id == plan_id).first()
            if not plan: return response(404, {"error": "Plan not found"})

            # Factory Dispatch
            if provider_name == "mpesa":
                provider = MpesaProvider()
                metadata = {"phone_number": body.get("phone_number")}
            elif provider_name in ["stripe", "flutterwave"]:
                provider = FlutterwaveProvider()
                metadata = {
                    "user_id": user_id, 
                    "plan_id": plan_id,
                    "email": body.get("email"),
                    "name": body.get("name"),
                    "phone_number": body.get("phone_number")
                }
            else:
                return response(400, {"error": "Unsupported provider"})

            result = provider.initiate_checkout(user_id, plan_id, plan.price, metadata)
            return response(200, result)

        # 4. Payment Status (Authenticated - Polling)
        if "/status/" in path and method == "GET":
            checkout_id = path.split("/")[-1]
            from models.subscription import SubscriptionPayment
            payment = db.query(SubscriptionPayment).filter(
                (SubscriptionPayment.provider_reference == checkout_id) | 
                (SubscriptionPayment.payment_id == checkout_id)
            ).first()
            
            if not payment:
                return response(200, {"status": "pending"})
            return response(200, {"status": payment.status, "confirmed_at": payment.created_at.isoformat()})

        # 5. My Subscription (Authenticated - Dashboard)
        if path.endswith("/my-subscription") and method == "GET":
            user_id = event.get("requestContext", {}).get("authorizer", {}).get("claims", {}).get("sub")
            from models.subscription import Subscription
            sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            if not sub: return response(200, {"active_plan": "Free", "usage": {}})
            
            plan = db.query(Plan).filter(Plan.plan_id == sub.plan_id).first()
            # Calculate Usage (Groups and Campaigns)
            from models import Group, Campaign
            groups_count = db.query(Group).filter(Group.owner_id == user_id).count()
            campaigns_count = db.query(Campaign).filter(Campaign.owner_id == user_id).count()

            return response(200, {
                "active_plan": plan.name,
                "status": sub.status,
                "expiry_date": sub.end_date.isoformat() if sub.end_date else None,
                "usage": {
                    "groups": f"{groups_count}/{plan.max_groups}",
                    "campaigns": f"{campaigns_count}/{plan.max_campaigns}"
                }
            })

        # 6. Webhooks (Public - Signature Verified Internally)
        if "/webhooks/" in path and method == "POST":
            provider_name = path.split("/")[-1]
            raw_body = event.get("body", "")
            payload = json.loads(raw_body)
            headers = event.get("headers", {})

            if provider_name == "mpesa": provider = MpesaProvider()
            elif provider_name in ["stripe", "flutterwave"]: provider = FlutterwaveProvider()
            else: return response(400, {"error": "Invalid webhook provider"})

            if not provider.verify_webhook(raw_body, headers):
                return response(401, {"error": "Invalid signature"})

            event_data = provider.parse_webhook_payload(payload)
            if event_data["success"]:
                fulfillment = FulfillmentService(db)
                # Note: In a real system, we'd lookup metadata via event_data['correlation_id']
                fulfillment.process_success(
                    event_data["correlation_id"], 
                    event_data["provider_ref"], 
                    event_data["amount"]
                )
            
            return response(200, {"received": True})

        return response(404, {"error": "Not Found"})

    except Exception as e:
        logger.error(f"Finance Error: {str(e)}", exc_info=True)
        return response(500, {"error": "internal_server_error"})
    finally:
        db.close()
