import json
import logging
from common.database import SessionLocal
from common.decorators import with_auth, with_subscription_check
from services.approval.service import ApprovalService

logger = logging.getLogger(__name__)

@with_auth(role_required="treasurer")
@with_subscription_check(required_feature="approvals")
def handler(event, context):
    """
    Unified Transaction Approval & Review Handler.
    Routes requests based on the specific action (Approve, Split, Reject).
    """
    try:
        body = json.loads(event.get("body", "{}"))
        path = event.get("path", "")
        
        # 1. Context Extraction
        # pending_id can come from body or path parameter depending on route
        pending_id = body.get("pending_id") or event.get("pathParameters", {}).get("pending_id")
        group_id = body.get("group_id")
        user_id = event["user_id"]

        if not pending_id:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing pending_id"})}

        # 2. Service Initialization
        db = SessionLocal()
        service = ApprovalService(db)
        
        # 3. Action Routing
        try:
            if "/approve" in path:
                txn = service.approve_transaction(pending_id, user_id, group_id, body.get("campaign_id"))
                msg = "Transaction approved and committed to ledger."
            
            elif "/split" in path:
                allocations = body.get("allocations", [])
                if not allocations:
                    return {"statusCode": 400, "body": json.dumps({"error": "Missing allocations for split"})}
                txn = service.split_transaction(pending_id, user_id, group_id, allocations, body.get("campaign_id"))
                msg = "Transaction split and committed to ledger."
            
            elif "/reject" in path:
                # Add rejection logic if needed, or just mark as rejected
                msg = "Transaction rejected."
                txn = None # Need to implement reject in service
            
            else:
                return {"statusCode": 404, "body": json.dumps({"error": "Unknown approval action"})}

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": msg,
                    "transaction_id": str(txn.transaction_id) if txn else None
                })
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Approval Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
