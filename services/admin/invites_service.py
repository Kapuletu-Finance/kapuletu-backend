import uuid
import datetime
import secrets
from sqlalchemy.orm import Session
from models.invite import Invite
from services.notifications.tasks import send_communication_async

class InvitesService:
    def __init__(self, db: Session):
        self.db = db

    def generate_and_send_invite(self, email: str = None, phone_number: str = None, sender_id: str = None, message: str = None) -> str:
        """Generates an invite token and sends an invitation."""
        token = secrets.token_urlsafe(16)
        
        # Invite expires in 7 days
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        
        invite = Invite(
            email=email,
            phone_number=phone_number,
            token=token,
            expires_at=expires_at,
            status="PENDING"
        )
        self.db.add(invite)
        self.db.commit()
        
        # Build invitation link
        from common.config import get_config
        frontend_url = get_config().FRONTEND_URL.rstrip('/')
        invite_link = f"{frontend_url}/register?invite_token={token}"
        
        # Send via email if provided
        if email:
            send_communication_async.delay(
                medium="email",
                destination=email,
                template_name="invite",
                context={
                    "invite_link": invite_link,
                    "expires_in_days": 7,
                    "custom_message": message
                },
                subject="You've been invited to KapuLetu!"
            )
            
        return token
    
    def bulk_invite(self, emails: list, message: str, sender_id: str = None) -> int:
        count = 0
        for email in emails:
            email = email.strip()
            if email:
                self.generate_and_send_invite(email=email, sender_id=sender_id, message=message)
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
