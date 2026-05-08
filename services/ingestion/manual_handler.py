import json
import logging
import uuid
from common.database import SessionLocal
from common.decorators import with_auth
from models.pending_transaction import PendingTransaction
from repositories.transaction_repo import TransactionRepository

logger = logging.getLogger(__name__)

@with_auth(role_required="treasurer")
def handler(event, context):
    """
    Manual Transaction Entry Handler.
    Allows Treasurers to manually input transaction data that didn't come via webhook.
    """
    try:
        body = json.loads(event.get("body", "{}"))
        
        # 1. Validation
        required = ["amount", "sender_name", "sender_phone"]
        for field in required:
            if field not in body:
                return {"statusCode": 400, "body": json.dumps({"error": f"Missing field: {field}"})}

        # 2. Setup DB & Repo
        db = SessionLocal()
        repo = TransactionRepository(db)
        
        # 3. Create Pending Transaction record
        # Note: We generate a 'MANUAL-' transaction code for idempotency
        txn_code = body.get("transaction_code") or f"MANUAL-{uuid.uuid4().hex[:12].upper()}"
        
        # Check for duplicates even in manual entry
        if repo.check_duplicate_transaction_code(txn_code):
            return {"statusCode": 409, "body": json.dumps({"error": "Transaction code already exists"})}

        pending_txn = PendingTransaction(
            owner_id=event["user_id"],
            raw_message="MANUAL_ENTRY",
            sender_name=body["sender_name"],
            amount=body["amount"],
            currency=body.get("currency", "KES"),
            transaction_code=txn_code,
            sender_phone=body["sender_phone"],
            purpose=body.get("purpose", "Manual Entry"),
            confidence_score=1.0, # Manual entry is 100% confident
            workflow_status="pending"
        )
        
        saved_txn = repo.insert_pending_transaction(pending_txn)
        db.close()

        return {
            "statusCode": 201,
            "body": json.dumps({
                "message": "Manual transaction recorded successfully",
                "pending_id": str(saved_txn.pending_id)
            })
        }

    except Exception as e:
        logger.error(f"Manual Entry Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
