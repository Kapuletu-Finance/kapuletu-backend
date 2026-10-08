"""
Transactional sends recorded in communication_logs (OTPs, receipts, invites). Each task tries up to three
times and records the final outcome only; broadcasts use the outbox in services/communications instead.
"""
import datetime
import logging
import time
from typing import Callable

from common.config import get_config
from common.database import SessionLocal
from models.communication_logs import CommunicationLog
from services.notifications.providers.resend_client import ResendClient
from services.notifications.providers.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)

ATTEMPTS = 3
BACKOFF_SECONDS = (1, 3)  # waits after attempts 1 and 2


def _record(log_id: str, status: str, error: str = None):
    db = SessionLocal()
    try:
        log = db.query(CommunicationLog).filter(CommunicationLog.log_id == log_id).first()
        if not log:
            logger.error(f"CommunicationLog {log_id} not found.")
            return
        log.status = status
        log.error_message = error
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Could not record status {status} for CommunicationLog {log_id}: {e}")
    finally:
        db.close()


def _send_with_retries(log_id: str, label: str, send: Callable[[], bool]):
    error = None
    for attempt in range(ATTEMPTS):
        try:
            if send():
                _record(log_id, "SENT")
                return
            error = f"{label} provider rejected the message"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(f"{label} attempt {attempt + 1} for log {log_id} raised: {error}")
        if attempt < ATTEMPTS - 1:
            time.sleep(BACKOFF_SECONDS[attempt])
    logger.error(f"{label} for log {log_id} failed after {ATTEMPTS} attempts: {error}")
    _record(log_id, "FAILED", error)


def send_email_task(log_id: str, to_email: str, subject: str, html_body: str, attachments: list = None):
    from services.communications.templates import layout_env
    # Wrap the provided html_body in the branded layout
    final_html_body = layout_env.get_template("email_base.html").render(
        subject=subject,
        body=html_body,
        frontend_url=get_config().FRONTEND_URL.rstrip("/"),
        current_year=datetime.datetime.utcnow().year,
    )
    client = ResendClient()
    _send_with_retries(log_id, "Email", lambda: client.send_email(
        to_email=to_email, subject=subject, html_body=final_html_body, attachments=attachments,
    ))


def send_whatsapp_task(log_id: str, to_phone: str, message: str):
    client = WhatsAppClient()
    _send_with_retries(log_id, "WhatsApp", lambda: client.send_text_message(to_phone=to_phone, message=message))
