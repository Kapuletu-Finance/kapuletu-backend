import json
import logging

from common.database import SessionLocal
from services.reporting.daily_summary import generate_summary

logger = logging.getLogger(__name__)

def handler(event, context):
    """
    Reporting Service Handler: Generates financial summaries and exports.
    """
    # 1. Identify the user (In production, this comes from Cognito Authorizer)
    # For now, we expect it in the query string or context
    owner_id = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('sub')
    
    if not owner_id:
        # Fallback for manual/test triggers
        owner_id = event.get('queryStringParameters', {}).get('owner_id')

    if not owner_id:
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Unauthorized: No owner_id found in context"})
        }

    db = SessionLocal()
    try:
        # 2. Generate the financial summary
        summary = generate_summary(db, owner_id)
        
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            },
            "body": json.dumps(summary)
        }
    except Exception as e:
        logger.error(f"Reporting Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        db.close()
