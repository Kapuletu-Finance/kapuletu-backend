import json
import logging
from common.database import SessionLocal
from common.decorators import with_auth
from models.pending_transaction import PendingTransaction

logger = logging.getLogger(__name__)

@with_auth(role_required="treasurer")
def handler(event, context):
    """
    Evidence Management Handler: Allows treasurers to link screenshots to pending records.
    """
    try:
        method = event.get("httpMethod")
        path_params = event.get("pathParameters", {}) or {}
        pending_id = path_params.get("pending_id")
        
        if not pending_id:
            return {"statusCode": 400, "body": json.dumps({"error": "pending_id is required"})}

        db = SessionLocal()
        try:
            pending = db.query(PendingTransaction).filter(PendingTransaction.pending_id == pending_id).first()
            if not pending:
                return {"statusCode": 404, "body": json.dumps({"error": "Pending transaction not found"})}

            if method == "POST":
                body = json.loads(event.get("body", "{}"))
                url = body.get("evidence_url")
                if not url:
                    return {"statusCode": 400, "body": json.dumps({"error": "evidence_url is required"})}
                
                pending.evidence_url = url
                db.commit()
                return {"statusCode": 200, "body": json.dumps({"message": "Evidence linked successfully"})}

            # Default: GET
            return {
                "statusCode": 200,
                "body": json.dumps({"pending_id": pending_id, "evidence_url": pending.evidence_url})
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Evidence Handler Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
