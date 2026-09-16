import datetime
import uuid
from sqlalchemy import Column, String, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID

from .base import Base
import enum

class IdentifierType(enum.Enum):
    EMAIL = "email"
    PHONE = "phone"

class WaitlistWhitelist(Base):
    """
    WaitlistWhitelist: Stores emails or phone numbers of pre-approved users (like testers)
    who should bypass the waitlist when waitlist mode is enabled.
    """
    __tablename__ = "waitlist_whitelist"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    identifier = Column(String, unique=True, index=True, nullable=False)
    identifier_type = Column(SAEnum(IdentifierType), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
