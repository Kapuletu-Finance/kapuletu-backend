import json
from services.campaigns.service import create_campaign, list_campaigns

def handler(event, context):
    """
    Campaign Management Handler: Oversees fundraising and project goals.
    
    Supports:
    - POST: Initialize a new fundraising campaign.
    - GET (Default): List all active and archived campaigns.
    """
    method = event.get("httpMethod")
    
    if method == "POST":
        # Initialize a new campaign (e.g. 'Social Fund', 'Christmas Party')
        body = json.loads(event.get("body", "{}"))
        return {"statusCode": 201, "body": json.dumps(create_campaign(body))}
        
    # Default to listing available campaigns
    return {"statusCode": 200, "body": json.dumps(list_campaigns())}
