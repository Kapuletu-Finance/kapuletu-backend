import logging

from common.database import SessionLocal
from models.system_config import SystemConfig

logger = logging.getLogger(__name__)


def _admin_emails(db, category: str = None) -> list:
    """Recipients from system config: the category's list (e.g. admin_notification_emails_hr), else the general one."""
    keys = ([f"admin_notification_emails_{category}"] if category else []) + ["admin_notification_emails"]
    for key in keys:
        config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
        value = config.config_value if config else None
        emails = value.get("emails") if isinstance(value, dict) else None
        if isinstance(emails, list) and emails:
            return [e for e in emails if isinstance(e, str) and "@" in e]
    return []


def notify_admins_async(subject: str, html_content: str, category: str = None):
    """
    Queues an alert email to the internal team in the communications outbox (sent within seconds, with retries).
    Supports a 'category' (e.g., 'hr', 'signups', 'finance') for targeted recipients. Never raises.
    """
    from services.communications.outbox import queue_email
    db = SessionLocal()
    try:
        emails = _admin_emails(db, category)
        if not emails:
            logger.info("Admin notification emails not configured; alert not sent.")
            return
        for email in emails:
            queue_email(db, email, subject, html_content, kind=f"staff_alert_{category or 'general'}")
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Could not queue admin alert '{subject}': {exc}")
    finally:
        db.close()
