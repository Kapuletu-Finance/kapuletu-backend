import json
import logging
from common.database import SessionLocal
from common.decorators import with_auth
from services.campaigns import service

logger = logging.getLogger(__name__)

@with_auth(role_required="treasurer")
def handler(event, context):
    """
    Campaign Management Handler (Production Grade).
    """
    try:
        method = event.get("httpMethod")
        path_params = event.get("pathParameters", {}) or {}
        group_id = path_params.get("group_id")
        
        if not group_id:
            return {"statusCode": 400, "body": json.dumps({"error": "group_id is required"})}

        db = SessionLocal()
        try:
            if method == "POST":
                body = json.loads(event.get("body", "{}"))
                result = service.create_campaign(db, group_id, body)
                return {
                    "statusCode": 201, 
                    "body": json.dumps({
                        "message": "Campaign created successfully",
                        "campaign_id": str(result.campaign_id)
                    })
                }
            
            # Default: List campaigns for this group
            campaigns = service.list_campaigns(db, group_id)
            return {
                "statusCode": 200, 
                "body": json.dumps([{
                    "id": str(c.campaign_id),
                    "title": c.title,
                    "target": float(c.target_amount)
                } for c in campaigns])
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Campaign Handler Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
