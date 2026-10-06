import logging
import threading
from common.database import SessionLocal
from models.system_config import SystemConfig
from services.notifications.providers.resend_client import ResendClient

logger = logging.getLogger(__name__)

def _send_admin_emails_sync(subject: str, html_content: str, category: str = None):
    db = SessionLocal()
    try:
        config_key = f"admin_notification_emails_{category}" if category else "admin_notification_emails"
        config = db.query(SystemConfig).filter(SystemConfig.config_key == config_key).first()
        
        # Fallback to general admin emails if specific category not set
        if not config or not config.config_value or not isinstance(config.config_value, dict) or not config.config_value.get("emails"):
             config = db.query(SystemConfig).filter(SystemConfig.config_key == "admin_notification_emails").first()
             
        if not config or not config.config_value or not isinstance(config.config_value, dict):
            logger.info("Admin notification emails not configured or invalid.")
            return

        emails = config.config_value.get("emails", [])
        if not emails or not isinstance(emails, list):
            logger.info("No admin emails found in configuration.")
            return
            
        resend_client = ResendClient()
        for email in emails:
            try:
                resend_client.send_email(
                    to_email=email,
                    subject=subject,
                    html_body=html_content
                )
            except Exception as e:
                logger.error(f"Failed to send admin alert to {email}: {e}")
                
    except Exception as exc:
        logger.error(f"Error in _send_admin_emails_sync: {exc}")
    finally:
        db.close()


def notify_admins_async(subject: str, html_content: str, category: str = None):
    """
    Fire-and-forget background task to notify admins.
    Supports a 'category' (e.g., 'hr', 'signups') for targeted emails.
    """
    thread = threading.Thread(
        target=_send_admin_emails_sync, 
        args=(subject, html_content, category)
    )
    thread.daemon = True
    thread.start()
