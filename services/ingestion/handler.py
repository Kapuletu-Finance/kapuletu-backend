from common.utils import parse_uuid
import json
import logging
import os
import requests

from common.database import SessionLocal
from services.ingestion.service import IngestionService
from common.config import get_config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handler(event, context):
    """
    Primary entry point for the Meta WhatsApp Cloud API Webhook.
    """
    logger.info("Received Ingestion Webhook request")
    
    http_method = event.get("httpMethod", "POST")
    query_params = event.get("queryStringParameters") or {}
    
    config = get_config()

    # 1. Meta Webhook Verification Challenge (GET)
    if http_method == "GET":
        mode = query_params.get("hub.mode")
        token = query_params.get("hub.verify_token")
        challenge = query_params.get("hub.challenge")
        
        if mode == "subscribe" and token == config.META_VERIFY_TOKEN:
            logger.info("Meta Webhook Verification successful.")
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "text/plain"},
                "body": str(challenge)
            }
        else:
            logger.warning("Meta Webhook Verification failed: Invalid token.")
            return {"statusCode": 403, "body": "Verification failed"}

    # 2. Payload Extraction & Normalization (POST)
    body_str = event.get("body", "{}")
    is_base64 = event.get("isBase64Encoded", False)
    
    if is_base64:
        import base64
        try:
            body_str = base64.b64decode(body_str).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to decode base64 body: {e}")
            return {"statusCode": 400, "body": json.dumps({"error": "invalid_encoding"})}
            
    # 3. SQS Decoupling (If configured)
    sqs_queue_url = os.environ.get("SQS_QUEUE_URL")
    if sqs_queue_url:
        import boto3
        sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        try:
            sqs.send_message(QueueUrl=sqs_queue_url, MessageBody=body_str)
            logger.info("Successfully queued webhook payload to SQS.")
            return {"statusCode": 200, "body": "OK"}
        except Exception as e:
            logger.error(f"Failed to queue to SQS: {e}")
            # Fall back to synchronous processing if SQS fails
    
    # 4. Asynchronous Thread Fallback (Local Dev or SQS Bypassed)
    import threading
    
    def background_task(body, conf):
        try:
            process_ingestion(body, conf)
        except Exception as e:
            logger.error(f"Background thread processing failed: {e}")
            
    thread = threading.Thread(target=background_task, args=(body_str, config))
    thread.start()
    
    # Always return 200 OK instantly to Meta to prevent retry floods
    return {"statusCode": 200, "body": "OK"}

def process_sqs_record(record):
    """
    Entry point for SQS worker triggering from the Webhook Queue.
    """
    logger.info("Processing SQS Webhook Record")
    body_str = record.get("body", "{}")
    config = get_config()
    return process_ingestion(body_str, config)

def process_ingestion(body_str: str, config):
    """
    Core logic: parses payload, saves to database, and sends WhatsApp reply.
    """
    try:
        payload_data = json.loads(body_str)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Invalid JSON"}

    # Meta webhook payloads are deeply nested
    # entry -> changes -> value
    try:
        entry = payload_data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
    except IndexError:
        return {"statusCode": 200, "body": "OK"} # Acknowledge malformed to prevent retries

    # Check if this is a status update (delivery/read receipt)
    if "statuses" in value:
        status_info = value["statuses"][0]
        logger.info(f"Received status update: {status_info.get('status')} for message ID {status_info.get('id')}")
        # We don't process these with the AI, just acknowledge
        return {"statusCode": 200, "body": "OK"}

    # Check if this is a message
    if "messages" not in value:
        return {"statusCode": 200, "body": "OK"} # Acknowledge other types of webhooks
        
    message_info = value["messages"][0]
    
    # We care about text and interactive messages
    msg_type = message_info.get("type")
    if msg_type not in ["text", "interactive"]:
        logger.info(f"Ignoring message type: {msg_type}")
        return {"statusCode": 200, "body": "OK"}

    # Extract required fields
    sender_phone = message_info.get("from")
    if not sender_phone:
        return {"statusCode": 400, "body": "Missing sender phone"}
        
    # Meta sends phone numbers without the '+' sign (e.g., 254712345678).
    if not sender_phone.startswith("+"):
        sender_phone = f"+{sender_phone}"

    message_body = ""
    interactive_id = None
    
    if msg_type == "text":
        message_body = message_info.get("text", {}).get("body", "")
    elif msg_type == "interactive":
        interactive = message_info.get("interactive", {})
        if interactive.get("type") == "list_reply":
            interactive_id = interactive.get("list_reply", {}).get("id")
            message_body = interactive.get("list_reply", {}).get("title", "")
    
    if not message_body and not interactive_id:
        return {"statusCode": 400, "body": "Missing message content"}

    # Normalize payload for the existing service architecture
    normalized_payload = {
        "From": sender_phone,
        "Body": message_body
    }

    # 3. Database Session Initialization
    db = SessionLocal()
    
    try:
        # --- Interactive Report Flow ---
        from repositories.transaction_repo import TransactionRepository
        from models.campaign import Campaign
        from models.group import Group
        from services.reporting.daily_summary import generate_campaign_whatsapp_report
        
        # 3.1 Check if it's an interactive menu selection for a report
        if interactive_id and interactive_id.startswith("REPORT_CAMPAIGN_"):
            campaign_id = interactive_id.replace("REPORT_CAMPAIGN_", "")
            try:
                report_text = generate_campaign_whatsapp_report(db, campaign_id)
                send_meta_reply(sender_phone, report_text, config)
            except Exception as e:
                logger.error(f"Failed to generate report for campaign {campaign_id}: {e}")
                send_meta_reply(sender_phone, "Error generating report. Please try again.", config)
            return {"statusCode": 200, "body": "OK"}
            
        # 3.2 Check if the user is explicitly requesting a report
        if msg_type == "text" and message_body.strip().upper() == "REPORT":
            repo = TransactionRepository(db)
            owner = repo.resolve_owner_by_phone(sender_phone)
            
            if not owner:
                send_meta_reply(sender_phone, "Unauthorized: Your phone number is not registered.", config)
            else:
                # Query all active campaigns for the user
                active_campaigns = db.query(Campaign).join(Group).filter(
                    Group.owner_id == parse_uuid(owner.user_id),
                    Campaign.is_active == True
                ).order_by(Campaign.created_at.desc()).all()
                
                if len(active_campaigns) == 0:
                    send_meta_reply(sender_phone, "Notice: You do not have any active campaigns.", config)
                elif len(active_campaigns) == 1:
                    # Only one campaign, send it directly
                    report_text = generate_campaign_whatsapp_report(db, str(active_campaigns[0].campaign_id))
                    send_meta_reply(sender_phone, report_text, config)
                else:
                    # Multiple campaigns, construct an interactive list
                    rows = []
                    for c in active_campaigns[:10]: # WhatsApp limits to 10 rows per list
                        # Title is limited to 24 chars
                        title = c.title[:24]
                        rows.append({
                            "id": f"REPORT_CAMPAIGN_{c.campaign_id}",
                            "title": title
                        })
                    
                    sections = [{
                        "title": "Active Campaigns",
                        "rows": rows
                    }]
                    
                    body_text = "You have multiple active campaigns. Please select the campaign you want to generate a report for:"
                    send_meta_interactive_list(sender_phone, body_text, "Select Campaign", sections, config)
            
            return {"statusCode": 200, "body": "OK"}

        # 4. Invoke Ingestion Service Logic
        ingestion_service = IngestionService(db)
        result = ingestion_service.process_webhook(normalized_payload)
        
        # Determine reply text
        if result["status"] == "ignored":
            reply_text = "You have already submitted this transaction. It is currently pending review."
        elif result["status"] == "error":
            reply_text = f"Unauthorized: Your phone number is not registered as a treasurer for any KapuLetu group. Please contact an admin or visit {config.FRONTEND_URL.rstrip('/')}/signup to create an account."
        else:
            parsed = result.get("parsed_data", {})
            amt = f"KES {parsed.get('amount', 0.0):,.2f}" if parsed.get('amount') else "the transaction"
            name = parsed.get("sender_name") or parsed.get("provider") or "the sender"
            reply_text = f"Success! We received {amt} from {name}. It is now awaiting for your approval in your kapuletu workspace"

        # 5. Send Reply via Meta Graph API
        send_meta_reply(sender_phone, reply_text, config)

        # Acknowledge receipt immediately to Meta
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"status": "OK"})
        }
        
    except Exception as e:
        logger.error(f"CRITICAL: Unexpected error in ingestion processing: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "internal_server_error", "message": str(e)})
        }
    finally:
        db.close()


def send_meta_reply(to_phone: str, message_text: str, config):
    """
    Helper function to send an outgoing text message via the Meta WhatsApp Cloud API.
    """
    if not config.META_ACCESS_TOKEN or not config.META_PHONE_NUMBER_ID:
        logger.warning("Skipping outgoing WhatsApp reply: META_ACCESS_TOKEN or META_PHONE_NUMBER_ID not configured.")
        return

    url = f"https://graph.facebook.com/v19.0/{config.META_PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {config.META_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code not in (200, 201):
            logger.error(f"Failed to send Meta reply. Status: {response.status_code}, Response: {response.text}")
        else:
            logger.info("Successfully sent outgoing Meta reply.")
    except Exception as e:
        logger.error(f"Error executing outgoing Meta HTTP request: {e}")

def send_meta_interactive_list(to_phone: str, body_text: str, button_text: str, sections: list, config):
    """
    Helper function to send an outgoing Interactive List message via the Meta WhatsApp Cloud API.
    sections format: [{"title": "Section Name", "rows": [{"id": "row_id", "title": "Row Title", "description": "Optional"}]}]
    """
    if not config.META_ACCESS_TOKEN or not config.META_PHONE_NUMBER_ID:
        logger.warning("Skipping outgoing WhatsApp reply: META_ACCESS_TOKEN or META_PHONE_NUMBER_ID not configured.")
        return

    url = f"https://graph.facebook.com/v19.0/{config.META_PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {config.META_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": body_text
            },
            "action": {
                "button": button_text[:20],  # Max 20 chars
                "sections": sections
            }
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code not in (200, 201):
            logger.error(f"Failed to send Meta interactive list. Status: {response.status_code}, Response: {response.text}")
        else:
            logger.info("Successfully sent outgoing Meta interactive list.")
    except Exception as e:
        logger.error(f"Error executing outgoing Meta HTTP request: {e}")
