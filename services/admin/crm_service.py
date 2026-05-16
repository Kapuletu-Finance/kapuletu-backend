import boto3
import json
import os
from sqlalchemy.orm import Session
from models.support_ticket import SupportTicket
from models.users import User
import datetime

class CRMService:
    """
    CRMService: Handles platform-to-user communications and support lifecycle.
    """
    def __init__(self, db: Session):
        self.db = db
        self.sqs = boto3.client('sqs', region_name=os.environ.get('AWS_REGION', 'eu-west-1'))
        self.broadcast_queue_url = os.environ.get('BROADCAST_QUEUE_URL')

    def send_broadcast(self, message: str, channels: list = ["sms"], target_role: str = "treasurer"):
        """
        Queues a platform-wide message to all users of a specific role.
        """
        # 1. Fetch target users
        users = self.db.query(User).filter(User.role == target_role, User.is_active == True).all()
        
        # 2. Push to SQS for background processing (Worker will handle Twilio/SES calls)
        # We send one message per user to the queue for individual delivery tracking
        for user in users:
            payload = {
                "user_id": str(user.user_id),
                "phone": user.phone_number,
                "email": user.email,
                "message": message,
                "channels": channels
            }
            
            if self.broadcast_queue_url:
                self.sqs.send_message(
                    QueueUrl=self.broadcast_queue_url,
                    MessageBody=json.dumps(payload)
                )
        
        return {"status": "broadcast_queued", "recipients": len(users)}

    def list_tickets(self, status: str = "open"):
        """
        Retrieves support tickets filtered by status.
        """
        tickets = self.db.query(SupportTicket).filter(SupportTicket.status == status).order_by(SupportTicket.created_at.desc()).all()
        return [{
            "ticket_id": str(t.ticket_id),
            "user_id": str(t.user_id),
            "subject": t.subject,
            "category": t.category,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat()
        } for t in tickets]

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

    def get_suggestions(self):
        """
        Specific view for platform suggestions from treasurers.
        """
        return self.list_tickets(status="open") # Filtered by category 'suggestion' in real use
