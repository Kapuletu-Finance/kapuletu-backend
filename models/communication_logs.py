import uuid
import datetime
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from .base import Base

class CommunicationLog(Base):
    __tablename__ = "communication_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True) # Optional, might send to non-users
    channel = Column(String(50), nullable=False) # 'EMAIL', 'SMS', 'WHATSAPP'
    destination = Column(String(255), nullable=False) # Email address or phone number
    subject = Column(String(255), nullable=True)
    status = Column(String(50), default="QUEUED") # 'QUEUED', 'SENT', 'FAILED', 'DELIVERED'
    provider_message_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
