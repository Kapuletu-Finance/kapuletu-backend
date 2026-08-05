import functools
import json

from common.auth import decode_access_token
from common.database import SessionLocal
from models.subscription import Subscription


def with_auth(role_required: str = None):
    """
    Decorator for AWS Lambda handlers to enforce JWT Authentication.
    
    Responsibilities:
    1. Extracts the Bearer token from the 'Authorization' header.
    2. Decodes and validates the token via JWT utilities.
    3. Enforces Role-Based Access Control (RBAC).
    4. Injects 'user_id' and 'role' into the Lambda 'event' object for use by the handler.
    
    Args:
        role_required (str): Optional role name (e.g., 'treasurer', 'admin') to restrict access.
    """
    def decorator(handler):
        @functools.wraps(handler)
        def wrapper(event, context):
            headers = event.get("headers", {})
            auth_header = headers.get("Authorization") or headers.get("authorization") or ""
            if not auth_header.startswith("Bearer "):
                return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized: Missing or malformed token"})}
            
            token = auth_header.split(" ")[1]
            payload = decode_access_token(token)
            
            if not payload:
                return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized: Invalid or expired token"})}
            
            # Role-Based Access Control check
            if role_required:
                allowed_roles = [role_required] if isinstance(role_required, str) else role_required
                if payload.get("role") not in allowed_roles:
                    return {"statusCode": 403, "body": json.dumps({"error": "Forbidden: Insufficient permissions for this operation"})}
            
            # Context Injection: Allows the handler to know who is making the request
            event["user_id"] = payload.get("sub")
            event["role"] = payload.get("role")
            
            return handler(event, context)
        return wrapper
    return decorator

def with_subscription_check(required_feature: str = None):
    """
    Decorator for AWS Lambda handlers to enforce active service subscriptions.
    
    Responsibilities:
    1. Verifies that the authenticated user has an 'active' subscription.
    2. (Optional) Can be extended to check if the user's specific plan covers a feature.
    
    Note: Requires @with_auth to be applied first to provide the 'user_id' context.
    """
    def decorator(handler):
        @functools.wraps(handler)
        def wrapper(event, context):
            user_id = event.get("user_id")
            if not user_id:
                 # This error occurs if the developer forgets to use @with_auth
                 return {"statusCode": 500, "body": json.dumps({"error": "System Error: User context missing"})}
            
            db = SessionLocal()
            try:
                # Lookup active subscription for the current user
                subscription = db.query(Subscription).filter(
                    Subscription.user_id == user_id, 
                    Subscription.status == "active"
                ).first()
                
                if not subscription:
                    return {
                        "statusCode": 402, 
                        "body": json.dumps({"error": "Payment Required: No active subscription found"})
                    }
                
                # Feature Gating & Quota Logic
                if required_feature:
                    from models.subscription import Plan, UsageTracking
                    plan = db.query(Plan).filter(Plan.plan_id == subscription.plan_id).first()
                    
                    if required_feature == "max_groups":
                        # Check count of existing groups
                        from models import Group
                        count = db.query(Group).filter(Group.owner_id == user_id).count()
                        if count >= plan.max_groups:
                            return {"statusCode": 403, "body": json.dumps({"error": f"Limit Reached: Your {plan.name} plan allows only {plan.max_groups} group(s)."})}
                    
                    if required_feature == "max_campaigns":
                        from models import Campaign
                        count = db.query(Campaign).filter(Campaign.owner_id == user_id).count()
                        if count >= plan.max_campaigns:
                            return {"statusCode": 403, "body": json.dumps({"error": f"Limit Reached: Your {plan.name} plan allows only {plan.max_campaigns} campaign(s)."})}

                return handler(event, context)
            finally:
                db.close()
        return wrapper
    return decorator
