import json
import logging
from common.database import SessionLocal
from common.decorators import with_auth
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)

@with_auth(role_required="treasurer")
def handler(event, context):
    """
    Forensic Audit Handler: Allows treasurers to view system logs for their own account.
    """
    try:
        user_id = event["user_id"]
        query_params = event.get("queryStringParameters", {}) or {}
        
        db = SessionLocal()
        try:
            # Strictly filter by the treasurer's ID for tenant isolation
            query = db.query(AuditLog).filter(AuditLog.actor_id == user_id)
            
            # Simple pagination
            limit = int(query_params.get("limit", 20))
            logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
            
            return {
                "statusCode": 200,
                "body": json.dumps([{
                    "action": l.action,
                    "entity": l.entity_type,
                    "entity_id": l.entity_id,
                    "timestamp": l.created_at.isoformat(),
                    "details": l.details
                } for l in logs])
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Audit Handler Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
