import datetime
import uuid

from sqlalchemy import UUID, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class SupportTicket(Base):
    """
    SupportTicket Model: Tracks user issues, questions, and platform suggestions.
    """
    __tablename__ = "support_tickets"

    ticket_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), default="support") # support, bug, suggestion, billing
    status = Column(String(20), default="open") # open, in_progress, resolved, closed
    priority = Column(String(10), default="medium") # low, medium, high, urgent
    
    # Forensic/Timeline data
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    resolved_at = Column(DateTime)
    
    # Enterprise SLA tracking
    sla_deadline = Column(DateTime)
    last_reply_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Admin context
    assigned_admin_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    internal_notes = Column(Text)

    user = relationship("User", foreign_keys=[user_id])
    assigned_admin = relationship("User", foreign_keys=[assigned_admin_id])
    
    # Relationship to thread messages
    messages = relationship("SupportTicketMessage", back_populates="ticket", cascade="all, delete-orphan", order_by="SupportTicketMessage.created_at")
