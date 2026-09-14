import uuid
import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from .base import Base

class Invite(Base):
    __tablename__ = "invites"

    invite_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=True)
    phone_number = Column(String(50), nullable=True)
    token = Column(String(255), unique=True, nullable=False)
    status = Column(String(50), default="PENDING") # PENDING, ACCEPTED, EXPIRED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
