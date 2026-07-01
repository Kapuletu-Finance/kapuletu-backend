import datetime
import uuid

from sqlalchemy import Column, DateTime, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from .base import Base

class OTP(Base):
    """
    OTP Model: Stores short-lived verification codes for users.
    
    This is used for registration verification, password resets, and potentially
    MFA. Codes should expire usually within 10-15 minutes.
    """
    __tablename__ = "otps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    
    # The exact phone number or email this code was sent to
    identifier = Column(String, nullable=False)
    
    # The 6-digit code
    code = Column(String, nullable=False)
    
    # E.g., 'registration', 'password_reset'
    purpose = Column(String, nullable=False)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
