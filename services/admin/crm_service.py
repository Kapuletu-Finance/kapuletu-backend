import boto3
import json
import os
import datetime
from sqlalchemy.orm import Session
from models.support_ticket import SupportTicket
from models.support_ticket_message import SupportTicketMessage
from models.users import User

class CRMService:
    """
    CRMService: Handles platform-to-user communications and support lifecycle.
    """
    def __init__(self, db: Session):
        self.db = db
        self.sqs = boto3.client('sqs', region_name=os.environ.get('AWS_REGION', 'eu-west-1'))
        self.broadcast_queue_url = os.environ.get('BROADCAST_QUEUE_URL')

    def send_broadcast(self, title: str, message: str, target_audience: str, channels: list):
        """
        Queues a platform-wide message to users based on audience segment, and saves to DB.
        """
        from models.broadcast import BroadcastCampaign
        from models.subscription import Subscription
        
        # 1. Save campaign to database
        campaign = BroadcastCampaign(
            title=title,
            message_body=message,
            target_audience=target_audience,
            channels=channels,
            status="queued"
        )
        self.db.add(campaign)
        self.db.flush() # flush to get campaign_id
        
        # 2. Fetch target users
        if target_audience == "all_members":
            users = self.db.query(User).filter(User.is_active == True).all()
        elif target_audience == "active_subscribers":
            users = self.db.query(User).join(Subscription, User.user_id == Subscription.user_id).filter(
                Subscription.status == "active", User.is_active == True
            ).all()
        elif target_audience == "marketing_opt_in":
            users = self.db.query(User).filter(User.marketing_consent == True, User.is_active == True).all()
        else:
            # fallback to treasurer for legacy compatibility if segment not found
            users = self.db.query(User).filter(User.role == "treasurer", User.is_active == True).all()
            
        campaign.recipients_count = len(users)
        
        # 3. Push to SQS for background processing
        for user in users:
            # Simple variable replacement (can be expanded later)
            personalized_message = message.replace("{{first_name}}", user.first_name if user.first_name else "")
            
            payload = {
                "campaign_id": str(campaign.campaign_id),
                "user_id": str(user.user_id),
                "phone": user.phone_number,
                "email": user.email,
                "title": title,
                "message": personalized_message,
                "channels": channels
            }
            
            if self.broadcast_queue_url:
                self.sqs.send_message(
                    QueueUrl=self.broadcast_queue_url,
                    MessageBody=json.dumps(payload)
                )
                
        campaign.status = "sent"
        self.db.commit()
        
        return {"status": "broadcast_queued", "campaign_id": str(campaign.campaign_id), "recipients": len(users)}

    def list_tickets(self, status: str = "open"):
        """
        Retrieves support tickets filtered by status, returning user names and ordered by SLA.
        """
        from models.support_session_rating import SupportSessionRating
        results = self.db.query(SupportTicket, User).join(User, SupportTicket.user_id == User.user_id).filter(
            SupportTicket.status == status
        ).order_by(SupportTicket.sla_deadline.asc().nulls_last()).all()
        
        def _rating_for(ticket_id):
            return self.db.query(SupportSessionRating).filter_by(ticket_id=ticket_id).first()
        
        return [{
            "ticket_id": str(t.SupportTicket.ticket_id),
            "user_id": str(t.SupportTicket.user_id),
            "user_name": f"{t.User.first_name} {t.User.last_name}",
            "email": t.User.email,
            "subject": t.SupportTicket.subject,
            "category": t.SupportTicket.category,
            "status": t.SupportTicket.status,
            "priority": t.SupportTicket.priority,
            "sla_deadline": t.SupportTicket.sla_deadline.isoformat() if t.SupportTicket.sla_deadline else None,
            "last_reply_at": t.SupportTicket.last_reply_at.isoformat() if t.SupportTicket.last_reply_at else None,
            "created_at": t.SupportTicket.created_at.isoformat(),
            "has_rating": _rating_for(t.SupportTicket.ticket_id) is not None,
            "satisfaction_level": (_rating_for(t.SupportTicket.ticket_id) or type('', (), {'satisfaction_level': None})()).satisfaction_level,
        } for t in results]

    def get_ticket_details(self, ticket_id: str):
        from models.support_session_rating import SupportSessionRating
        ticket = self.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
        if not ticket:
            return None
        messages = self.db.query(SupportTicketMessage).filter_by(ticket_id=ticket_id).order_by(SupportTicketMessage.created_at.asc()).all()
        user = self.db.query(User).filter_by(user_id=ticket.user_id).first()
        rating = self.db.query(SupportSessionRating).filter_by(ticket_id=ticket.ticket_id).first()
        
        return {
            "ticket_id": str(ticket.ticket_id),
            "user_id": str(ticket.user_id),
            "user_name": f"{user.first_name} {user.last_name}" if user else "Unknown",
            "user_email": user.email if user else None,
            "user_phone": user.phone_number if user else None,
            "user_kyc": "Verified" if (user and user.email_verified and user.phone_number_verified) else "Pending",
            "subject": ticket.subject,
            "category": ticket.category,
            "status": ticket.status,
            "priority": ticket.priority,
            "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
            "assigned_admin_id": str(ticket.assigned_admin_id) if ticket.assigned_admin_id else None,
            "internal_notes": ticket.internal_notes,
            "created_at": ticket.created_at.isoformat(),
            "has_rating": rating is not None,
            "rating": {
                "issue_resolved": rating.issue_resolved,
                "satisfaction_level": rating.satisfaction_level,
                "response_quality": rating.response_quality,
                "response_speed": rating.response_speed,
                "comment": rating.comment,
                "created_at": rating.created_at.isoformat(),
            } if rating else None,
            "messages": [{
                "message_id": str(m.message_id),
                "sender_id": str(m.sender_id),
                "sender_name": f"{self.db.query(User).filter_by(user_id=m.sender_id).first().first_name} {self.db.query(User).filter_by(user_id=m.sender_id).first().last_name}" if self.db.query(User).filter_by(user_id=m.sender_id).first() else "Unknown",
                "message": m.message,
                "is_internal": m.is_internal,
                "created_at": m.created_at.isoformat()
            } for m in messages]
        }

    def update_ticket(self, ticket_id: str, admin_id: str, updates: dict):
        """
        Updates the status or adds internal notes to a ticket.
        """
        ticket = self.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
        if not ticket:
            return False
            
        if "status" in updates: 
            ticket.status = updates["status"]
            if updates["status"] == "resolved":
                ticket.resolved_at = datetime.datetime.utcnow()
        
        if "internal_notes" in updates: ticket.internal_notes = updates["internal_notes"]
        if "priority" in updates: ticket.priority = updates["priority"]
        
        ticket.assigned_admin_id = admin_id
        self.db.commit()
        return True
        
    def reply_to_ticket(self, ticket_id: str, admin_id: str, message: str):
        """
        Posts an admin reply to a ticket thread and notifies the user via Email.
        """
        ticket = self.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
        if not ticket:
            return False
            
        msg = SupportTicketMessage(
            ticket_id=ticket.ticket_id,
            sender_id=admin_id,
            message=message
        )
        ticket.updated_at = datetime.datetime.utcnow()
        ticket.last_reply_at = datetime.datetime.utcnow()
        ticket.assigned_admin_id = admin_id
        
        self.db.add(msg)
        self.db.commit()
        
        # Trigger Notification
        user = self.db.query(User).filter_by(user_id=ticket.user_id).first()
        admin = self.db.query(User).filter_by(user_id=admin_id).first()
        admin_name = f"{admin.first_name} {admin.last_name}" if admin else "Kapuletu Support"
        
        if user and user.email:
            from services.notifications.providers.resend_client import ResendClient
            from services.notifications.email_templates import get_ticket_reply_template
            
            reply_html = get_ticket_reply_template(ticket.subject, message, admin_name, is_admin=True)
            try:
                ResendClient().send_email(
                    to_email=user.email,
                    subject=f"Re: {ticket.subject}",
                    html_body=reply_html
                )
            except Exception:
                pass # Fail gracefully
            
        return True

    def get_suggestions(self):
        """
        Specific view for platform suggestions from treasurers.
        """
        return self.list_tickets(status="open") # Filtered by category 'suggestion' in real use
