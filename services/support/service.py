import datetime
from sqlalchemy.orm import Session
from models.support_ticket import SupportTicket
from models.support_ticket_message import SupportTicketMessage
from models.subscription import Subscription, Plan

class SupportService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_sla_deadline(self, user_id, priority: str) -> datetime.datetime:
        """
        Calculates the SLA deadline based on the user's active Plan and ticket priority.
        Defaults:
        - Basic: 24h
        - Professional: 8h
        - Enterprise: 2h
        """
        sub = self.db.query(Subscription).filter_by(user_id=user_id, status="active").first()
        sla_hours = 24
        
        if sub:
            plan = self.db.query(Plan).filter_by(plan_id=sub.plan_id).first()
            if plan and plan.allowed_features:
                sla_hours = plan.allowed_features.get("support_sla_hours", 24)
        
        # Priority modifiers
        if priority == "urgent":
            sla_hours = max(2, sla_hours // 2)
        elif priority == "high":
            sla_hours = max(4, sla_hours // 2)
            
        return datetime.datetime.utcnow() + datetime.timedelta(hours=sla_hours)

    def create_ticket(self, user_id, subject: str, message: str, category: str, priority: str):
        sla_deadline = self.calculate_sla_deadline(user_id, priority)
        
        ticket = SupportTicket(
            user_id=user_id,
            subject=subject,
            description=message, # initial message reference
            category=category,
            priority=priority,
            sla_deadline=sla_deadline,
            status="open"
        )
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        
        # Add thread message
        msg = SupportTicketMessage(
            ticket_id=ticket.ticket_id,
            sender_id=user_id,
            message=message
        )
        self.db.add(msg)
        self.db.commit()
        
        return ticket

    def list_user_tickets(self, user_id):
        return self.db.query(SupportTicket).filter_by(user_id=user_id).order_by(SupportTicket.updated_at.desc()).all()

    def get_ticket_details(self, user_id, ticket_id):
        ticket = self.db.query(SupportTicket).filter_by(user_id=user_id, ticket_id=ticket_id).first()
        if not ticket:
            return None, []
        messages = self.db.query(SupportTicketMessage).filter_by(ticket_id=ticket_id, is_internal=False).order_by(SupportTicketMessage.created_at.asc()).all()
        return ticket, messages
        
    def reply_to_ticket(self, user_id, ticket_id, message: str):
        ticket = self.db.query(SupportTicket).filter_by(user_id=user_id, ticket_id=ticket_id).first()
        if not ticket:
            raise ValueError("Ticket not found")
            
        msg = SupportTicketMessage(
            ticket_id=ticket.ticket_id,
            sender_id=user_id,
            message=message
        )
        ticket.updated_at = datetime.datetime.utcnow()
        ticket.last_reply_at = datetime.datetime.utcnow()
        ticket.status = "open" # Reopen if resolved
        
        self.db.add(msg)
        self.db.commit()
        return msg
