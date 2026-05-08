import json
import logging

from common.database import SessionLocal
from services.reporting.daily_summary import generate_summary, generate_campaign_whatsapp_report

logger = logging.getLogger(__name__)

def handler(event, context):
    """
    Reporting Service Handler: Generates financial summaries and WhatsApp group lists.
    """
    try:
        # 1. Identify the user/context
        owner_id = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('sub')
        query_params = event.get('queryStringParameters', {}) or {}
        path_params = event.get('pathParameters', {}) or {}
        
        if not owner_id:
            owner_id = query_params.get('owner_id')

        # 2. Check for Campaign-Specific Request
        campaign_id = path_params.get('campaign_id') or query_params.get('campaign_id')
        
        db = SessionLocal()
        try:
            if campaign_id:
                # Generate the 'Official Group List' for WhatsApp
                instructions = query_params.get('instructions', "Pay via M-Pesa to our Treasury number.")
                report_text = generate_campaign_whatsapp_report(db, campaign_id, instructions)
                
                return {
                    "statusCode": 200,
                    "body": json.dumps({
                        "campaign_id": campaign_id,
                        "whatsapp_format": report_text
                    })
                }
            
            # Default: General Daily Summary
            summary = generate_summary(db, owner_id)
            return {
                "statusCode": 200,
                "body": json.dumps(summary)
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Reporting Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
