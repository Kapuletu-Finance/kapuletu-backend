from common.utils import parse_uuid
import json
import logging
import uuid
from common.database import SessionLocal
from common.decorators import with_auth
from models.transaction import Transaction
from services.audit.service import AuditService
from services.approval.service import ApprovalService

logger = logging.getLogger(__name__)

@with_auth(role_required=["treasurer", "admin", "super_admin"])
def handler(event, context):
    """
    Manual Transaction Entry Handler.
    Allows Treasurers to manually input transaction data that didn't come via webhook.
    """
    try:
        raw_body = event.get("body", "{}") or "{}"
        body = json.loads(raw_body)
        
        # 1. Validation
        required = ["amount", "sender_name", "group_id", "campaign_id"]
        for field in required:
            if not body.get(field):
                return {"statusCode": 400, "body": json.dumps({"error": f"Missing or empty field: {field}"})}

        # 2. Setup DB & Repo
        db = SessionLocal()
        
        # Security: Verify group ownership (IDOR prevention)
        from models.group import Group
        from repositories.group_repo import get_group
        from repositories.campaign_repo import get_campaign
        import uuid
        
        try:
            user_id_raw = event.get("user_id")
            if not user_id_raw:
                return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized: Missing user identity"})}
            owner_uuid = uuid.UUID(str(user_id_raw))
        except (ValueError, AttributeError):
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid UUID format for user_id"})}
            
        # Resolve identifiers (can be UUIDs or slugs)
        group = get_group(db, body["group_id"])
        if not group or group.owner_id != owner_uuid:
            logger.warning(f"manual_handler 403: User {owner_uuid} does not own group {body.get('group_id')}")
            db.close()
            return {"statusCode": 403, "body": json.dumps({"error": "Forbidden: You do not have permission to add transactions to this group."})}
            
        campaign = get_campaign(db, body["campaign_id"])
        if not campaign:
            db.close()
            return {"statusCode": 404, "body": json.dumps({"error": "Campaign not found"})}
            
        # 3. Create Finalized Transaction record
        # Note: We generate a 'MANUAL-' transaction code for idempotency
        txn_code = body.get("transaction_code") or f"MANUAL-{uuid.uuid4().hex[:12].upper()}"
        
        # Check for duplicates
        from models.pending_transaction import PendingTransaction
        pending_exists = db.query(PendingTransaction).filter(PendingTransaction.transaction_code == txn_code, PendingTransaction.owner_id == parse_uuid(owner_uuid)).first()
        txn_exists = db.query(Transaction).filter(Transaction.transaction_code == txn_code, Transaction.owner_id == parse_uuid(owner_uuid)).first()
        if pending_exists or txn_exists:
            return {"statusCode": 409, "body": json.dumps({"error": "Transaction code already exists"})}

        new_txn = Transaction(
            owner_id=owner_uuid,
            group_id=group.group_id,
            campaign_id=campaign.campaign_id,
            transaction_code=txn_code,
            amount=body["amount"],
            sender_phone=body.get("sender_phone"),
            sender_name=body["sender_name"],
            payment_method=body.get("payment_method", "Cash"),
            source_evidence="Manually entered by treasurer",
            status="approved"
        )
        db.add(new_txn)
        db.flush()
        
        # Write Integrity Seal
        ApprovalService(db)._write_to_ledger(new_txn)
        db.commit()
        
        AuditService(db).log_action(
            actor_id=event["user_id"],
            action="MANUAL_ENTRY",
            entity_type="TRANSACTION",
            entity_id=str(new_txn.transaction_id),
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
                "transaction_id": str(new_txn.transaction_id)
            })
        }

    except Exception as e:
        logger.error(f"Manual Entry Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
