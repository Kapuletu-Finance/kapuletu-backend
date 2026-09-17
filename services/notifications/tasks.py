import logging
import traceback
from sqlalchemy.orm import Session
from common.database import SessionLocal
from models.communication_logs import CommunicationLog
from services.notifications.providers.resend_client import ResendClient
from services.notifications.providers.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)

import time

import os
import datetime
from jinja2 import Environment, FileSystemLoader

def send_email_task(log_id: str, to_email: str, subject: str, html_body: str):
    # Setup Jinja2 Environment
    template_dir = os.path.join(os.path.dirname(__file__), '../../templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('email_base.html')
    
    frontend_url = os.environ.get("FRONTEND_URL", "https://kapuletu.co.ke")
    
    # Wrap the provided html_body in the branded template
    final_html_body = template.render(
        subject=subject,
        body=html_body,
        frontend_url=frontend_url,
        current_year=datetime.datetime.utcnow().year
    )

    for attempt in range(3):
        db: Session = SessionLocal()
        try:
            log = db.query(CommunicationLog).filter(CommunicationLog.log_id == log_id).first()
            if not log:
                logger.error(f"CommunicationLog {log_id} not found.")
                return

            resend_client = ResendClient()
            success = resend_client.send_email(
                to_email=to_email,
                subject=subject,
                html_body=final_html_body
            )
            
            if success:
                log.status = "SENT"
                db.commit()
                return  # Success, exit the loop
            else:
                log.status = "FAILED"
                log.error_message = "Resend Client returned False"
                db.commit()
                if attempt == 2:
                    return # Give up
                
        except Exception as exc:
            log.status = "FAILED"
            log.error_message = traceback.format_exc()
            db.commit()
            if attempt == 2:
                logger.error(f"Email task failed after 3 attempts: {exc}")
                return
        finally:
            db.close()
            
        # Exponential backoff before retry
        time.sleep(1)


def send_whatsapp_task(log_id: str, to_phone: str, message: str):
    for attempt in range(3):
        db: Session = SessionLocal()
        try:
            log = db.query(CommunicationLog).filter(CommunicationLog.log_id == log_id).first()
            if not log:
                logger.error(f"CommunicationLog {log_id} not found.")
                return

            whatsapp_client = WhatsAppClient()
            success = whatsapp_client.send_text_message(
                to_phone=to_phone,
                message=message
            )
            
            if success:
                log.status = "SENT"
                db.commit()
                return
            else:
                log.status = "FAILED"
                log.error_message = "WhatsApp Client returned False"
                db.commit()
                if attempt == 2:
                    return
                
        except Exception as exc:
            log.status = "FAILED"
            log.error_message = traceback.format_exc()
            db.commit()
            if attempt == 2:
                logger.error(f"WhatsApp task failed after 3 attempts: {exc}")
                return
        finally:
            db.close()
            
        time.sleep(1)
