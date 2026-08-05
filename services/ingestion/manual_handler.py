import json
import logging
import uuid
from common.database import SessionLocal
from common.decorators import with_auth
from models.pending_transaction import PendingTransaction
from repositories.transaction_repo import TransactionRepository
from services.audit.service import AuditService

logger = logging.getLogger(__name__)

@with_auth(role_required=["treasurer", "admin", "super_admin"])
def handler(event, context):
    """
    Manual Transaction Entry Handler.
    Allows Treasurers to manually input transaction data that didn't come via webhook.
    """
    try:
        body = json.loads(event.get("body", "{}"))
        
        # 1. Validation
        required = ["amount", "sender_name", "group_id", "campaign_id"]
        for field in required:
            if not body.get(field):
                return {"statusCode": 400, "body": json.dumps({"error": f"Missing or empty field: {field}"})}

        # 2. Setup DB & Repo
        db = SessionLocal()
        
        # Security: Verify group ownership (IDOR prevention)
        from models.group import Group
        import uuid
        try:
            group_uuid = uuid.UUID(body["group_id"])
            owner_uuid = uuid.UUID(event["user_id"])
        except ValueError:
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid UUID format for group_id or user_id"})}
            
        group = db.query(Group).filter(Group.group_id == group_uuid, Group.owner_id == owner_uuid).first()
        if not group:
            logger.warning(f"manual_handler 403: User {owner_uuid} does not own group {group_uuid}")
            db.close()
            return {"statusCode": 403, "body": json.dumps({"error": "Forbidden: You do not have permission to add transactions to this group."})}
            
        repo = TransactionRepository(db)
        
        # 3. Create Pending Transaction record
        # Note: We generate a 'MANUAL-' transaction code for idempotency
        txn_code = body.get("transaction_code") or f"MANUAL-{uuid.uuid4().hex[:12].upper()}"
        
        # Check for duplicates even in manual entry
        if repo.check_duplicate_transaction_code(txn_code, event["user_id"]):
            return {"statusCode": 409, "body": json.dumps({"error": "Transaction code already exists"})}

        pending_txn = PendingTransaction(
            owner_id=event["user_id"],
            group_id=body["group_id"],
            campaign_id=body["campaign_id"],
            raw_message="MANUAL_ENTRY",
            sender_name=body["sender_name"],
            amount=body["amount"],
            currency=body.get("currency", "KES"),
            transaction_code=txn_code,
            sender_phone=body.get("sender_phone"),
            purpose=body.get("purpose", "Manual Entry"),
            confidence_score=1.0, # Manual entry is 100% confident
            workflow_status="pending",
            payment_method="Cash",
            source_evidence="Manually entered by treasurer"
        )
        
        saved_txn = repo.insert_pending_transaction(pending_txn)
        
        AuditService(db).log_action(
            actor_id=event["user_id"],
            action="MANUAL_ENTRY",
            entity_type="PENDING_TRANSACTION",
            entity_id=str(saved_txn.pending_id),
            details={
                "amount": float(body["amount"]),
                "message": f"Manual contribution of Ksh. {float(body['amount'])} added",
                "campaign_id": body.get("campaign_id") # Assuming body might pass it, otherwise None
            }
        )
        
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
