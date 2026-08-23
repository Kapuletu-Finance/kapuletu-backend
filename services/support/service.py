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
        from models.users import User
        from services.notifications.providers.resend_client import ResendClient
        from services.notifications.email_templates import get_ticket_created_template, get_admin_new_ticket_alert
        
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

        try:
            creator = self.db.query(User).filter_by(user_id=user_id).first()
            if creator:
                creator_name = f"{creator.first_name} {creator.last_name}"
                resend = ResendClient()
                if creator.email:
                    resend.send_email(
                        creator.email, 
                        "Ticket Received - Kapuletu Support", 
                        get_ticket_created_template(creator_name, subject, str(ticket.ticket_id))
                    )
                
                admins = self.db.query(User).filter_by(role="admin").all()
                admin_html = get_admin_new_ticket_alert(creator_name, subject, priority)
                for adm in admins:
                    if adm.email:
                        resend.send_email(adm.email, f"New Ticket: {subject}", admin_html)
        except Exception:
            pass # Fail gracefully
            
        return ticket

    def list_user_tickets(self, user_id):
        return self.db.query(SupportTicket).filter_by(user_id=user_id).order_by(SupportTicket.updated_at.desc()).all()

    def get_ticket_details(self, user_id, ticket_id):
        from models.users import User
        ticket = self.db.query(SupportTicket).filter_by(user_id=user_id, ticket_id=ticket_id).first()
        if not ticket:
            return None, []
        messages = self.db.query(SupportTicketMessage).filter_by(ticket_id=ticket_id, is_internal=False).order_by(SupportTicketMessage.created_at.asc()).all()
        
        for m in messages:
            sender = self.db.query(User).filter_by(user_id=m.sender_id).first()
            if sender:
                m.sender_name = f"{sender.first_name} {sender.last_name}"
            else:
                m.sender_name = "Unknown"
        
        return ticket, messages
        
    def reply_to_ticket(self, user_id, ticket_id, message: str):
        from models.users import User
        from services.notifications.providers.resend_client import ResendClient
        from services.notifications.email_templates import get_ticket_reply_template
        
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
        
        try:
            creator = self.db.query(User).filter_by(user_id=user_id).first()
            if creator:
                creator_name = f"{creator.first_name} {creator.last_name}"
                admin_ids = [ticket.assigned_admin_id] if ticket.assigned_admin_id else []
                if not admin_ids:
                    admins = self.db.query(User).filter_by(role="admin").all()
                    admin_ids = [adm.user_id for adm in admins]
                
                resend = ResendClient()
                reply_html = get_ticket_reply_template(ticket.subject, message, creator_name, is_admin=False)
                
                for aid in admin_ids:
                    adm = self.db.query(User).filter_by(user_id=aid).first()
                    if adm and adm.email:
                        resend.send_email(adm.email, f"New Reply: {ticket.subject}", reply_html)
        except Exception:
            pass # Fail gracefully
            
        return msg
