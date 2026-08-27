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
        from models.whatsapp_blocklist import WhatsAppBlocklist
        import datetime
        
        # 3.0 Check if user is blocked (gracefully handles missing table during migration window)
        try:
            blocked_record = db.query(WhatsAppBlocklist).filter(WhatsAppBlocklist.phone_number == sender_phone).first()
            if blocked_record and blocked_record.is_blocked:
                # Auto-unblock if last attempt was more than 24 hours ago
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                last_attempt = blocked_record.last_attempt_at
                if last_attempt and last_attempt.tzinfo is None:
                    last_attempt = last_attempt.replace(tzinfo=datetime.timezone.utc)
                    
                if last_attempt and (now_utc - last_attempt).total_seconds() > 86400:
                    blocked_record.is_blocked = False
                    blocked_record.attempt_count = 0
                    db.commit()
                else:
                    # Still blocked, silently drop the request
                    return {"statusCode": 200, "body": "OK"}
        except Exception as _blocklist_err:
            logger.warning(f"Blocklist table not available yet, skipping check: {_blocklist_err}")
            db.rollback()

        # --- Interactive Report Flow ---
        from repositories.transaction_repo import TransactionRepository
        from models.campaign import Campaign
        from models.group import Group
        from services.reporting.daily_summary import generate_campaign_whatsapp_report
        
        # 3.1 Check if it's an interactive menu selection for a report or approval
        if interactive_id:
            if interactive_id == "GREETING_WORKSPACE":
                send_meta_reply(sender_phone, f"You can access your KapuLetu dashboard here: {config.FRONTEND_URL.rstrip('/')}/treasurer", config)
                return {"statusCode": 200, "body": "OK"}
            elif interactive_id == "GREETING_APPROVALS":
                send_meta_reply(sender_phone, f"To review and approve pending member transactions, please visit your dashboard: {config.FRONTEND_URL.rstrip('/')}/treasurer", config)
                return {"statusCode": 200, "body": "OK"}
            elif interactive_id == "GREETING_HELP":
                send_whatsapp_help_menu(sender_phone, config)
                return {"statusCode": 200, "body": "OK"}
            elif interactive_id == "HELP_GROUP":
                send_meta_reply(sender_phone, "To create a new savings group, log in to your online workspace and navigate to the 'Groups' tab. Click 'New Group' and follow the setup wizard.", config)
                return {"statusCode": 200, "body": "OK"}
            elif interactive_id == "HELP_CAMPAIGN":
                send_meta_reply(sender_phone, "Once a group is active, you can create a campaign directly via WhatsApp by typing 'NEW CAMPAIGN', or through the 'Campaigns' tab in your online workspace.", config)
                return {"statusCode": 200, "body": "OK"}
            elif interactive_id == "HELP_APPROVE":
                send_meta_reply(sender_phone, "When members send payments, you will receive a notification. You can approve pending contributions by selecting 'Pending Contributions' from the main menu, or by reviewing them in the web dashboard.", config)
                return {"statusCode": 200, "body": "OK"}
            elif interactive_id == "HELP_BOT":
                send_meta_reply(sender_phone, "You can text the bot at any time using commands like 'REPORT' to get your campaign status, or 'HELP' to view this guide.", config)
                return {"statusCode": 200, "body": "OK"}
            elif interactive_id == "HELP_SETTINGS":
                send_meta_reply(sender_phone, "To customize your report formats, toggle WhatsApp features, or manage permissions, please visit the 'Settings' section of your online workspace.", config)
                return {"statusCode": 200, "body": "OK"}
        if interactive_id and interactive_id.startswith("REPORT_CAMPAIGN_"):
            campaign_id = interactive_id.replace("REPORT_CAMPAIGN_", "")
            try:
                report_text = generate_campaign_whatsapp_report(db, campaign_id)
                dispatch_whatsapp_report(db, sender_phone, campaign_id, report_text, config)
                
                from repositories.transaction_repo import TransactionRepository
                repo = TransactionRepository(db)
                owner = repo.resolve_owner_by_phone(sender_phone)
                if owner:
                    from services.audit.service import AuditService
                    # Ensure we have the campaign title
                    campaign_title = "Campaign"
                    campaign_record = db.query(Campaign).filter(Campaign.campaign_id == parse_uuid(campaign_id)).first()
                    if campaign_record:
                        campaign_title = campaign_record.title
                        
                    AuditService(db).log_action(
                        actor_id=str(owner.user_id),
                        action="REPORT_GENERATED",
                        entity_type="campaign",
                        entity_id=campaign_id,
                        details={
                            "message": f"WhatsApp report generated for \"{campaign_title}\"",
                            "campaign_id": campaign_id
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to generate report for campaign {campaign_id}: {e}")
                send_meta_reply(sender_phone, "Error generating report. Please try again.", config)
            return {"statusCode": 200, "body": "OK"}
            
        if interactive_id and interactive_id.startswith("APPROVE_"):
            # Format: APPROVE_{pending_id}_{campaign_id}
            parts = interactive_id.split("_")
            if len(parts) >= 3:
                pending_id = parts[1]
                campaign_id = parts[2]
                
                from services.approval.service import ApprovalService
                from models.campaign import Campaign
                from models.pending_transaction import PendingTransaction
                
                campaign = db.query(Campaign).filter(Campaign.campaign_id == parse_uuid(campaign_id)).first()
                if not campaign:
                    send_meta_reply(sender_phone, "Error: Campaign not found.", config)
                    return {"statusCode": 200, "body": "OK"}
                    
                pending = db.query(PendingTransaction).filter(PendingTransaction.pending_id == parse_uuid(pending_id)).first()
                if not pending:
                    send_meta_reply(sender_phone, "Error: Transaction not found.", config)
                    return {"statusCode": 200, "body": "OK"}

                approval_service = ApprovalService(db)
                try:
                    approval_service.approve_transaction(
                        pending_txn_id=pending_id,
                        treasurer_id=str(campaign.group.owner_id),
                        group_id=str(campaign.group_id),
                        campaign_id=campaign_id
                    )
                    send_meta_reply(sender_phone, "Success! The transaction has been approved and recorded in the ledger.", config)
                except Exception as e:
                    logger.error(f"Failed to approve transaction {pending_id}: {e}")
                    send_meta_reply(sender_phone, f"Error approving transaction: {e}", config)
                    send_meta_reply(sender_phone, f"Error approving transaction: {e}", config)
            return {"statusCode": 200, "body": "OK"}
            
        if interactive_id and interactive_id.startswith("NEW_CAMP_"):
            # Format: NEW_CAMP_{group_id}_{base64_encoded_title}
            parts = interactive_id.split("_", 3)
            if len(parts) >= 4:
                group_id = parts[2]
                import base64
                try:
                    title = base64.b64decode(parts[3]).decode('utf-8')
                except Exception:
                    title = "New Campaign"
                
                from models.group import Group
                from models.campaign import Campaign
                import uuid
                
                group = db.query(Group).filter(Group.group_id == parse_uuid(group_id)).first()
                if not group:
                    send_meta_reply(sender_phone, "Error: Group not found.", config)
                    return {"statusCode": 200, "body": "OK"}
                    
                new_camp = Campaign(
                    campaign_id=uuid.uuid4(),
                    group_id=group.group_id,
                    title=title,
                    status="active",
                    is_active=True
                )
                db.add(new_camp)
                db.commit()
                
                from services.audit.service import AuditService
                AuditService(db).log_action(
                    actor_id=str(group.owner_id),
                    action="CAMPAIGN_CREATED",
                    entity_type="campaign",
                    entity_id=str(new_camp.campaign_id),
                    details={
                        "message": f"New campaign \"{title}\" created via WhatsApp",
                        "campaign_id": str(new_camp.campaign_id),
                        "group_id": str(group.group_id),
                        "group_slug": group.slug,
                        "campaign_slug": new_camp.slug
                    }
                )
                send_meta_reply(sender_phone, f"Success! Campaign '{title}' created under group '{group.group_name}'.", config)
            return {"statusCode": 200, "body": "OK"}

        # 3.2 Check if the user is explicitly requesting a text command
        if msg_type == "text":
            repo = TransactionRepository(db)
            owner = repo.resolve_owner_by_phone(sender_phone)
            
            message_upper = message_body.strip().upper()
            greetings = ["HI", "HELLO", "HOLLA", "HOLA", "HEY", "GOOD MORNING", "GOOD AFTERNOON", "GOOD EVENING", "JAMBO", "SASA"]
            
            if message_upper in greetings:
                if not owner:
                    handle_unauthorized_access(sender_phone, config, db)
                    return {"statusCode": 200, "body": "OK"}
                send_whatsapp_main_menu(sender_phone, config)
                return {"statusCode": 200, "body": "OK"}
                
            if message_upper == "HELP":
                if not owner:
                    handle_unauthorized_access(sender_phone, config, db)
                    return {"statusCode": 200, "body": "OK"}
                send_whatsapp_help_menu(sender_phone, config)
                return {"statusCode": 200, "body": "OK"}
                
            if message_upper == "REPORT":
                if not owner:
                    handle_unauthorized_access(sender_phone, config, db)
                    return {"statusCode": 200, "body": "OK"}
                
                from services.settings.settings_service import SettingsService
                settings_service = SettingsService(db)
                user_settings = settings_service.get_global_settings(str(owner.user_id))
                
                if not user_settings.reporting.allow_whatsapp_reports:
                    send_meta_reply(sender_phone, "WhatsApp reporting is currently disabled. Please enable it in your KapuLetu portal settings.", config)
                    return {"statusCode": 200, "body": "OK"}
                    
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
                    dispatch_whatsapp_report(db, sender_phone, str(active_campaigns[0].campaign_id), report_text, config)
                    
                    from services.audit.service import AuditService
                    AuditService(db).log_action(
                        actor_id=str(owner.user_id),
                        action="REPORT_GENERATED",
                        entity_type="campaign",
                        entity_id=str(active_campaigns[0].campaign_id),
                        details={
                            "message": f"WhatsApp report generated for \"{active_campaigns[0].title}\"",
                            "campaign_id": str(active_campaigns[0].campaign_id)
                        }
                    )
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

        # 3.3 Check conversational NLP intents (Kapuletu AI)
        if msg_type == "text":
            from services.ingestion.local_intent_parser import intent_parser
            from repositories.transaction_repo import TransactionRepository
            from services.settings.settings_service import SettingsService
            
            repo = TransactionRepository(db)
            owner = repo.resolve_owner_by_phone(sender_phone)
            
            if owner:
                settings_service = SettingsService(db)
                user_settings = settings_service.get_global_settings(str(owner.user_id))
                
                parsed_intent = intent_parser.detect_intent(message_body)
                
                if parsed_intent["intent"] in ["create_group", "create_campaign"]:
                    if not user_settings.automation.allow_whatsapp_creation:
                        send_meta_reply(sender_phone, "WhatsApp creation commands are currently disabled. Please enable 'WhatsApp Creation' in your KapuLetu portal settings.", config)
                        return {"statusCode": 200, "body": "OK"}
                        
                    if parsed_intent["intent"] == "create_group":
                        group_name = parsed_intent["entities"].get("group_name")
                        if not group_name:
                            send_meta_reply(sender_phone, "I see you want to create a group! To do this, please reply in the format: *Create group [Group Name]* (e.g., Create group Welfare).", config)
                            return {"statusCode": 200, "body": "OK"}
                            
                        from models.group import Group
                        import uuid
                        import datetime
                        
                        # Check daily limit: Max 2 groups per day
                        yesterday = datetime.datetime.utcnow() - datetime.timedelta(days=1)
                        daily_group_count = db.query(Group).filter(
                            Group.owner_id == owner.user_id,
                            Group.created_at >= yesterday
                        ).count()
                        
                        if daily_group_count >= 2:
                            send_meta_reply(sender_phone, "You have reached the daily limit (2) for creating new groups via WhatsApp. Please try again tomorrow, or use the web portal.", config)
                            return {"statusCode": 200, "body": "OK"}
                            
                        new_group = Group(
                            group_id=uuid.uuid4(),
                            owner_id=owner.user_id,
                            group_name=group_name,
                            status="active",
                            is_active=True
                        )
                        db.add(new_group)
                        db.commit()
                        
                        from services.audit.service import AuditService
                        AuditService(db).log_action(
                            actor_id=str(owner.user_id),
                            action="GROUP_CREATED",
                            entity_type="group",
                            entity_id=str(new_group.group_id),
                            details={
                                "message": f"New group \"{group_name}\" created via WhatsApp",
                                "group_id": str(new_group.group_id)
                            }
                        )
                        send_meta_reply(sender_phone, f"Success! I've created the group '{group_name}'.", config)
                        return {"statusCode": 200, "body": "OK"}
                        
                    elif parsed_intent["intent"] == "create_campaign":
                        title = parsed_intent["entities"].get("campaign_title")
                        if not title:
                            send_meta_reply(sender_phone, "I see you want to create a campaign! To do this, please reply in the format: *Create campaign [Campaign Title]*.", config)
                            return {"statusCode": 200, "body": "OK"}
                            
                        from models.group import Group
                        from models.campaign import Campaign
                        import uuid
                        import base64
                        import datetime
                        
                        # Check daily limit: Max 2 campaigns per day across any groups
                        yesterday = datetime.datetime.utcnow() - datetime.timedelta(days=1)
                        daily_camp_count = db.query(Campaign).join(Group).filter(
                            Group.owner_id == owner.user_id,
                            Campaign.created_at >= yesterday
                        ).count()
                        
                        if daily_camp_count >= 2:
                            send_meta_reply(sender_phone, "You have reached the daily limit (2) for creating new campaigns via WhatsApp. Please try again tomorrow, or use the web portal.", config)
                            return {"statusCode": 200, "body": "OK"}
                            
                        active_groups = db.query(Group).filter(
                            Group.owner_id == owner.user_id,
                            Group.is_active == True
                        ).all()
                        
                        if len(active_groups) == 0:
                            send_meta_reply(sender_phone, "You need to create a group first before creating a campaign.", config)
                        elif len(active_groups) == 1:
                            new_camp = Campaign(
                                campaign_id=uuid.uuid4(),
                                group_id=active_groups[0].group_id,
                                title=title,
                                status="active",
                                is_active=True
                            )
                            db.add(new_camp)
                            db.commit()
                            
                            from services.audit.service import AuditService
                            AuditService(db).log_action(
                                actor_id=str(owner.user_id),
                                action="CAMPAIGN_CREATED",
                                entity_type="campaign",
                                entity_id=str(new_camp.campaign_id),
                                details={
                                    "message": f"New campaign \"{title}\" created via WhatsApp",
                                    "campaign_id": str(new_camp.campaign_id),
                                    "group_id": str(active_groups[0].group_id),
                                    "group_slug": active_groups[0].slug,
                                    "campaign_slug": new_camp.slug
                                }
                            )
                            send_meta_reply(sender_phone, f"Success! Campaign '{title}' created under your group '{active_groups[0].group_name}'.", config)
                        else:
                            encoded_title = base64.b64encode(title.encode('utf-8')).decode('utf-8')
                            rows = []
                            for g in active_groups[:10]:
                                rows.append({
                                    "id": f"NEW_CAMP_{g.group_id}_{encoded_title}",
                                    "title": g.group_name[:24]
                                })
                            
                            sections = [{
                                "title": "Your Groups",
                                "rows": rows
                            }]
                            
                            send_meta_interactive_list(sender_phone, f"Which group should the campaign '{title}' belong to?", "Select Group", sections, config)
                            
                        return {"statusCode": 200, "body": "OK"}

        # 4. Invoke Ingestion Service Logic
        ingestion_service = IngestionService(db)
        result = ingestion_service.process_webhook(normalized_payload)
        
        # Determine reply text and interactive list if configured
        if result["status"] == "ignored":
            reply_text = "You have already submitted this transaction. It is currently pending review."
            send_meta_reply(sender_phone, reply_text, config)
        elif result["status"] == "error":
            handle_unauthorized_access(sender_phone, config, db)
        elif result["status"] == "invalid":
            if result.get("message") == "REPORT_OR_SUMMARY":
                reply_text = "It looks like you forwarded a report or summary. To log contributions, please forward the original individual transaction receipts."
            elif result.get("message") == "CHATTER":
                reply_text = "I couldn't detect a valid transaction in that message. Please ensure you are forwarding a complete M-Pesa or bank receipt."
            else:
                reply_text = "I'm sorry, I didn't understand that request. Please forward a valid M-Pesa transaction receipt, or select an option from the menu below to get started."
            send_whatsapp_main_menu(sender_phone, config, reply_text)
        else:
            results_list = result.get("results", [])
            
            # Formulate the response text
            if len(results_list) > 1:
                reply_lines = [f"Successfully parsed {len(results_list)} transactions:"]
                for idx, r in enumerate(results_list, 1):
                    parsed = r.get("parsed_data", {})
                    amt = f"KES {parsed.get('amount', 0.0):,.2f}" if parsed.get('amount') else "a transaction"
                    name = parsed.get("sender_name") or parsed.get("provider") or "a sender"
                    reply_lines.append(f"{idx}. {amt} from {name}")
                reply_lines.append("\nThey are now awaiting your approval in the KapuLetu portal.")
                reply_text = "\n".join(reply_lines)
                send_meta_reply(sender_phone, reply_text, config)
                
                # We skip interactive approval for batches to avoid spamming 5 menus
                interactive_sent = True
            else:
                # Singular case
                single_res = results_list[0] if results_list else {}
                parsed = single_res.get("parsed_data", {})
                amt = f"KES {parsed.get('amount', 0.0):,.2f}" if parsed.get('amount') else "the transaction"
                name = parsed.get("sender_name") or parsed.get("provider") or "the sender"
                pending_id = single_res.get("pending_id")
                
                # Check if interactive approvals are enabled
                interactive_sent = False
            if pending_id:
                from repositories.transaction_repo import TransactionRepository
                repo = TransactionRepository(db)
                owner = repo.resolve_owner_by_phone(sender_phone)
                
                if owner:
                    from services.settings.settings_service import SettingsService
                    settings_service = SettingsService(db)
                    user_settings = settings_service.get_global_settings(str(owner.user_id))
                    
                    if user_settings.automation.auto_approve_enabled and user_settings.automation.auto_approve_campaign_id and user_settings.automation.auto_approve_group_id:
                        from services.approval.service import ApprovalService
                        from models.campaign import Campaign
                        
                        auto_campaign = db.query(Campaign).filter(Campaign.campaign_id == parse_uuid(user_settings.automation.auto_approve_campaign_id)).first()
                        if auto_campaign:
                            try:
                                approval_service = ApprovalService(db)
                                approval_service.approve_transaction(
                                    pending_txn_id=pending_id,
                                    treasurer_id=str(owner.user_id),
                                    group_id=user_settings.automation.auto_approve_group_id,
                                    campaign_id=user_settings.automation.auto_approve_campaign_id
                                )
                                reply_text = f"Success! We received {amt} from {name}. It was automatically approved to your campaign '{auto_campaign.title}'."
                                send_meta_reply(sender_phone, reply_text, config)
                                interactive_sent = True
                            except Exception as e:
                                logger.error(f"Failed to auto-approve transaction {pending_id}: {e}")
                                
                    if not interactive_sent and user_settings.automation.allow_whatsapp_approvals:
                        from models.campaign import Campaign
                        from models.group import Group
                        active_campaigns = db.query(Campaign).join(Group).filter(
                            Group.owner_id == parse_uuid(owner.user_id),
                            Campaign.is_active == True
                        ).order_by(Campaign.created_at.desc()).limit(10).all()
                        
                        if active_campaigns:
                            rows = []
                            for c in active_campaigns:
                                rows.append({
                                    "id": f"APPROVE_{pending_id}_{c.campaign_id}",
                                    "title": c.title[:24]
                                })
                            
                            sections = [{
                                "title": "Approve to Campaign",
                                "rows": rows
                            }]
                            
                            body_text = f"Success! We received {amt} from {name}. Select a campaign below to instantly approve it, or ignore this to leave it pending."
                            send_meta_interactive_list(sender_phone, body_text, "Approve Transaction", sections, config)
                            interactive_sent = True

            if not interactive_sent:
                reply_text = f"Success! We received {amt} from {name}. It is now awaiting for your approval in your kapuletu workspace"
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


def handle_unauthorized_access(phone: str, config, db_session):
    from models.whatsapp_blocklist import WhatsAppBlocklist
    
    record = db_session.query(WhatsAppBlocklist).filter(WhatsAppBlocklist.phone_number == phone).first()
    if not record:
        record = WhatsAppBlocklist(phone_number=phone, attempt_count=1, is_blocked=False)
        db_session.add(record)
        send_meta_reply(phone, f"Unauthorized Access: Your phone number is not registered as a KapuLetu treasurer. Please visit {config.FRONTEND_URL.rstrip('/')}/signup to create an account.", config)
    else:
        record.attempt_count += 1
        if record.attempt_count >= 3 and not record.is_blocked:
            record.is_blocked = True
            send_meta_reply(phone, "Security Alert: This phone number has been temporarily blocked from accessing KapuLetu due to multiple unauthorized attempts.", config)
        elif not record.is_blocked:
            send_meta_reply(phone, f"Unauthorized Access: Your phone number is not registered as a KapuLetu treasurer. Please visit {config.FRONTEND_URL.rstrip('/')}/signup to create an account.", config)
    
    db_session.commit()


def dispatch_whatsapp_report(db, sender_phone, campaign_id, report_text, config):
    if len(report_text) > 4000:
        from models.campaign import Campaign
        from common.utils import parse_uuid
        campaign = db.query(Campaign).filter(Campaign.campaign_id == parse_uuid(campaign_id)).first()
        if campaign:
            frontend_url = config.FRONTEND_URL.rstrip('/')
            group_slug = campaign.group.slug or campaign.group_id
            camp_slug = campaign.slug or campaign.campaign_id
            
            fallback_text = (
                f"*The comprehensive report for \"{campaign.title}\" is ready.*\n\n"
                f"*To view the full list of contributors and detailed metrics, please log in to your KapuLetu dashboard:*\n"
                f"{frontend_url}/treasurer/groups/{group_slug}/campaigns/{camp_slug}"
            )
            send_meta_reply(sender_phone, fallback_text, config)
            return
    send_meta_reply(sender_phone, report_text, config)


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

def send_whatsapp_main_menu(to_phone: str, config, prompt_text: str = None):
    text = prompt_text or "Hello! Welcome to KapuLetu. I am your automated treasury assistant. I can assist you with managing your campaigns, reviewing transactions, and accessing your workspace. Please select an option from the menu below."
    sections = [{
        "title": "Options",
        "rows": [
            {"id": "GREETING_WORKSPACE", "title": "Check your workspace", "description": "Link to KapuLetu dashboard"},
            {"id": "GREETING_APPROVALS", "title": "Pending Contributions", "description": "Review member transactions"},
            {"id": "GREETING_HELP", "title": "Help", "description": "Interactive KapuLetu guide"}
        ]
    }]
    send_meta_interactive_list(to_phone, text, "Main Menu", sections, config)

def send_whatsapp_help_menu(to_phone: str, config):
    text = "Welcome to the KapuLetu Help Center. Please select a topic from the menu below to view detailed instructions."
    sections = [{
        "title": "Topics",
        "rows": [
            {"id": "HELP_GROUP", "title": "Creating a Group"},
            {"id": "HELP_CAMPAIGN", "title": "Creating a Campaign"},
            {"id": "HELP_APPROVE", "title": "Approving Contributions"},
            {"id": "HELP_BOT", "title": "Using the WhatsApp Bot"},
            {"id": "HELP_SETTINGS", "title": "Settings"}
        ]
    }]
    send_meta_interactive_list(to_phone, text, "Help Topics", sections, config)


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
