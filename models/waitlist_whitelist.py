import datetime
import uuid
from sqlalchemy import Column, String, DateTime, Boolean
from .base import Base


class WaitlistWhitelist(Base):
    """
    WaitlistWhitelist: One record per pre-approved person (tester/VIP).
    Both phone_number and email are required.
    - phone_number is the PRIMARY identifier used at signup and OTP verification.
    - email is the INVITE channel — the invite link is sent here.
    - invite_sent tracks whether an invitation email has been dispatched.
    """
    __tablename__ = "waitlist_whitelist"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(String, unique=True, nullable=False, index=True)
    email        = Column(String, unique=True, nullable=False, index=True)
    name         = Column(String, nullable=True)
    description  = Column(String, nullable=True)
    invite_sent  = Column(Boolean, default=False, nullable=False)
    created_at   = Column(DateTime, default=datetime.datetime.utcnow)
