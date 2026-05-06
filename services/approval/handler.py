import json
from common.decorators import with_auth, with_subscription_check
from common.database import SessionLocal
from services.approval.service import ApprovalService

@with_auth(role_required="treasurer")
@with_subscription_check(required_feature="approvals")
def handler(event, context):
    """
    Treasurer Approval Handler (AWS Lambda).
    
    This endpoint allows a treasurer to transition a transaction from 'Pending' (unvalidated)
    to the official immutable ledger. It is the core human-in-the-loop validation point.
    
    Security:
    - @with_auth: Ensures only authenticated users with the 'treasurer' role can proceed.
    - @with_subscription_check: Verifies the group has an active subscription for this feature.
    
    Workflow:
    1. Extract the pending transaction ID and context (group/campaign).
    2. Initialize the ApprovalService with a scoped DB session.
    3. Execute business logic to move data from Postgres (pending) to the Ledger (official).
    
    Args:
        event (dict): Lambda event. Must contain 'user_id' injected by @with_auth.
        context (object): Lambda context.
    """
    # Parse incoming request parameters
    body = json.loads(event.get("body", "{}"))
    pending_id = body.get("pending_id")
    group_id = body.get("group_id")
    campaign_id = body.get("campaign_id")
    
    # Validation: Ensure we have enough data to link the transaction
    if not pending_id or not group_id:
        return {
            "statusCode": 400, 
            "body": json.dumps({"error": "Missing required fields: pending_id and group_id are mandatory."})
        }

    # Initialize persistence layer
    db = SessionLocal()
    service = ApprovalService(db)
    
    try:
        # Business Logic Execution:
        # The service layer handles state transitions, validation, and ledger commitment.
        # It also implicitly handles multi-tenancy by verifying that the treasurer 
        # owns the group/pending transaction.
        txn = service.approve_transaction(
            pending_txn_id=pending_id,
            treasurer_id=event["user_id"],
            group_id=group_id,
            campaign_id=campaign_id
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Transaction successfully approved and committed to the immutable ledger.",
                "transaction_id": str(txn.transaction_id)
            })
        }
    except Exception as e:
        # Error handling: Catch business logic violations (e.g. already approved, unauthorized)
        return {
            "statusCode": 500, 
            "body": json.dumps({"error": "Failed to approve transaction", "details": str(e)})
        }
    finally:
        # Resource cleanup: Close DB connections
        db.close()
