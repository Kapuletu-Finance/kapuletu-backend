import json
import logging
from common.database import SessionLocal
from common.decorators import with_auth
from services.members import service

logger = logging.getLogger(__name__)

@with_auth(role_required="treasurer")
def handler(event, context):
    """
    Member Management Handler: Tracks virtual members based on contribution records.
    """
    try:
        method = event.get("httpMethod")
        path_params = event.get("pathParameters", {}) or {}
        query_params = event.get("queryStringParameters", {}) or {}
        
        group_id = query_params.get("group_id") or path_params.get("group_id")
        if not group_id:
            return {"statusCode": 400, "body": json.dumps({"error": "group_id is required"})}

        db = SessionLocal()
        try:
            # 1. Contributor History for a specific person
            phone = query_params.get("phone")
            if phone:
                history = service.get_contributor_history(db, group_id, phone)
                return {"statusCode": 200, "body": json.dumps(history)}

            # 2. List all contributors in the group
            members = service.list_members_by_group(db, group_id)
            return {"statusCode": 200, "body": json.dumps(members)}

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Members Handler Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
