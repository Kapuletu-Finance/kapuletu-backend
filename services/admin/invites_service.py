from services.notifications.tasks import send_email_task
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
            import jinja2
            from models.communication_logs import CommunicationLog
            from common.config import get_config
            import datetime
            
            subject = "You've been invited to KapuLetu!"
            invite_url = get_config().FRONTEND_URL.rstrip('/') + f"/sign-up?invite_token={token}"
            
            # Attempt to fetch the explicitly provided name from the whitelist
            from models.waitlist_whitelist import WaitlistWhitelist
            tester = self.db.query(WaitlistWhitelist).filter(WaitlistWhitelist.email == email).first()
            
            if tester and tester.name:
                # Use just their first name from the explicitly provided name
                invitee_name = tester.name.split(' ')[0].title()
            else:
                # Fallback: Extract just the first name from the email prefix
                invitee_name = email.split('@')[0].split('.')[0].split('+')[0].title() if email else ""
            
            env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))
            template = env.get_template('email_base.html')
            
            body_content = f"""
            <h2>You're Invited to KapuLetu!</h2>
            <p>Hello {invitee_name},</p>
            <p>{message.replace(chr(10), '<br>')}</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{invite_url}" style="background-color: #097255; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px; display: inline-block;">Accept Invitation & Register</a>
            </div>
            
            <p style="font-size: 14px; color: #718096;">This invitation link is secure and single-use.</p>
            <p style="font-size: 14px; color: #718096;">If you didn't expect this invitation, you can safely ignore this email.</p>
            """
            
            html_body = template.render(
                subject=subject,
                frontend_url=get_config().FRONTEND_URL.rstrip('/'),
                body=body_content,
                current_year=datetime.datetime.utcnow().year
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
