import json
import logging
from common.database import SessionLocal
from common.decorators import with_auth
from repositories import group_repo

logger = logging.getLogger(__name__)

@with_auth(role_required="treasurer")
def handler(event, context):
    """
    Group Management Handler (Production Grade).
    Handles lifecycle of community organizations (Chamas).
    """
    try:
        method = event.get("httpMethod")
        user_id = event["user_id"]
        
        db = SessionLocal()
        try:
            if method == "POST":
                body = json.loads(event.get("body", "{}"))
                if "name" not in body:
                    return {"statusCode": 400, "body": json.dumps({"error": "Group name is required"})}
                
                result = group_repo.create_group(db, user_id, body["name"], body.get("description"))
                return {
                    "statusCode": 201, 
                    "body": json.dumps({
                        "message": "Group created successfully",
                        "group_id": str(result.group_id)
                    })
                }
            
            # Default: List groups owned by this treasurer
            groups = group_repo.get_owner_groups(db, user_id)
            return {
                "statusCode": 200, 
                "body": json.dumps([{
                    "id": str(g.group_id),
                    "name": g.name,
                    "description": g.description
                } for g in groups])
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Group Handler Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
