import logging
import traceback
from sqlalchemy.orm import Session
from common.worker import celery_app
from common.database import SessionLocal
from models.communication_logs import CommunicationLog
from services.notifications.providers.resend_client import ResendClient
from services.notifications.providers.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def send_email_task(self, log_id: str, to_email: str, subject: str, html_body: str):
    db: Session = SessionLocal()
    log = db.query(CommunicationLog).filter(CommunicationLog.log_id == log_id).first()
    
    if not log:
        logger.error(f"CommunicationLog {log_id} not found.")
        db.close()
        return

    try:
        resend_client = ResendClient()
        success = resend_client.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body
        )
        
        if success:
            log.status = "SENT"
        else:
            log.status = "FAILED"
            log.error_message = "Resend Client returned False"
            
        db.commit()
    except Exception as exc:
        log.status = "FAILED"
        log.error_message = traceback.format_exc()
        db.commit()
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def send_whatsapp_task(self, log_id: str, to_phone: str, message: str):
    db: Session = SessionLocal()
    log = db.query(CommunicationLog).filter(CommunicationLog.log_id == log_id).first()
    
    if not log:
        logger.error(f"CommunicationLog {log_id} not found.")
        db.close()
        return

    try:
        whatsapp_client = WhatsAppClient()
        success = whatsapp_client.send_text_message(
            to_phone=to_phone,
            message=message
        )
        
        if success:
            log.status = "SENT"
        else:
            log.status = "FAILED"
            log.error_message = "WhatsApp Client returned False"
            
        db.commit()
    except Exception as exc:
        log.status = "FAILED"
        log.error_message = traceback.format_exc()
        db.commit()
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    finally:
        db.close()
