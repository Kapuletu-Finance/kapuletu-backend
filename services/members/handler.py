import json
from services.members.service import create_member, list_members

def handler(event, context):
    """
    Member Management Handler: Handles CRUD operations for community group members.
    
    Supports:
    - POST: Register a new member.
    - GET (Default): List all members in the treasurer's context.
    """
    method = event.get("httpMethod")
    
    if method == "POST":
        # Create a new member profile
        body = json.loads(event.get("body", "{}"))
        return {"statusCode": 201, "body": json.dumps(create_member(body))}
        
    # Default to listing members
    return {"statusCode": 200, "body": json.dumps(list_members())}
