import datetime
import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class SupportTicketMessage(Base):
    """
    SupportTicketMessage Model: Represents a single message in a support thread.
    Can be from a user or an admin.
    """
    __tablename__ = "support_ticket_messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("support_tickets.ticket_id"), nullable=False)
    
    # Who sent the message
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    # Message content
    message = Column(Text, nullable=False)
    
    # If True, this is an internal note invisible to the user
    is_internal = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
