import datetime
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from .base import Base

class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    topic = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="unread")  # unread, read, replied, resolved
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class ContactMessageReply(Base):
    """A reply to a website inquiry, sent by email from the communications hub."""
    __tablename__ = "contact_message_replies"

    reply_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_message_id = Column(UUID(as_uuid=True), ForeignKey("contact_messages.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    body = Column(Text, nullable=False)
    comm_message_id = Column(UUID(as_uuid=True), ForeignKey("comm_messages.message_id", ondelete="SET NULL"),
                             nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
