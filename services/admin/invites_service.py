import uuid
import datetime
import secrets
from sqlalchemy.orm import Session
from models.invite import Invite

def _dispatch_bulk_invite_background(emails: list, message: str, sender_id: str):
    from common.database import SessionLocal
    import concurrent.futures
    db = SessionLocal()
    try:
        service = InvitesService(db)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for email in emails:
                executor.submit(service.generate_and_send_invite, email=email, sender_id=sender_id, message=message)
    finally:
        db.close()

class InvitesService:
    def __init__(self, db: Session):
        self.db = db

    def generate_and_send_invite(self, email: str = None, phone_number: str = None, sender_id: str = None, message: str = "Welcome!") -> str:
        """Generates an invite token and sends an invitation."""
        from common.utils import parse_uuid
        token = str(uuid.uuid4())
        expires = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        
        invite = Invite(
            token=token,
            email=email,
            phone_number=phone_number,
            expires_at=expires,
            status="PENDING"
        )
        self.db.add(invite)
        self.db.commit()

        if email:
            from services.notifications.templates.render import render_email_template
            from services.notifications.tasks import send_email_task
            from models.communication_logs import CommunicationLog

            subject = "You've been invited to KapuLetu!"
            from common.config import get_config
            invite_url = get_config().FRONTEND_URL.rstrip('/') + f"/sign-up?invite_token={token}"

            html_body = render_email_template(
                "invite.html",
                message=message.replace('\n', '<br>'),
                invite_url=invite_url
            )
            
            log = CommunicationLog(
                channel="EMAIL",
                destination=email,
                subject=subject,
                status="QUEUED"
            )
            self.db.add(log)
            self.db.commit()

            # Synchronous Execution (Bulletproof for Serverless/Migration)
            send_email_task(str(log.log_id), email, subject, html_body)
            
        return token
    
    def bulk_invite(self, emails: list, message: str = "Welcome!", sender_id: str = None, background_tasks = None) -> int:
        valid_emails = [e for e in emails if e and "@" in e]
        count = len(valid_emails)
        
        if background_tasks:
            background_tasks.add_task(
                _dispatch_bulk_invite_background,
                valid_emails, message, sender_id
            )
        else:
            for email in valid_emails:
                self.generate_and_send_invite(email=email, sender_id=sender_id, message=message)
                
        return count

    def list_invites(self):
        invites = self.db.query(Invite).order_by(Invite.created_at.desc()).all()
        return [
            {
                "id": str(i.invite_id),
                "email": i.email,
                "phone_number": i.phone_number,
                "token": i.token,
                "status": i.status,
                "created_at": i.created_at.isoformat(),
                "expires_at": i.expires_at.isoformat()
            }
            for i in invites
        ]
