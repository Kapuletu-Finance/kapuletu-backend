import uuid
import datetime
import secrets
from sqlalchemy.orm import Session
from models.invite import Invite

class InvitesService:
    def __init__(self, db: Session):
        self.db = db

    def generate_and_send_invite(self, email: str = None, phone_number: str = None, sender_id: str = None, message: str = "Welcome!", background_tasks=None) -> str:
        """Generates an invite token and sends an invitation."""
        from common.utils import parse_uuid
        token = str(uuid.uuid4())
        expires = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        
        invite = Invite(
            token=token,
            email=email,
            phone_number=phone_number,
            invited_by=parse_uuid(sender_id) if sender_id else None,
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
            invite_url = get_config().FRONTEND_URL.rstrip('/') + f"/accept-invite?token={token}"

            html_body = render_email_template(
                "invite_email.html",
                message=message,
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

            if background_tasks:
                background_tasks.add_task(send_email_task, str(log.log_id), email, subject, html_body)
            else:
                send_email_task(str(log.log_id), email, subject, html_body)
            
        return token
    
    def bulk_invite(self, emails: list, background_tasks=None, message: str = "Welcome!", sender_id: str = None) -> int:
        count = 0
        for email in emails:
            if email and "@" in email:
                self.generate_and_send_invite(email=email, sender_id=sender_id, message=message, background_tasks=background_tasks)
                count += 1
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
