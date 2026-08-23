import datetime
import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, String, JSON
from sqlalchemy.orm import relationship

from .base import Base
from common.enums import UserRole


class User(Base):
    """
    User Model: Represents the core identity for Treasurers and Admins.
    
    This is the top-level entity in the KapuLetu ecosystem. 
    A user (typically a treasurer) manages community groups and is the 
    authorizing entity for financial transactions ingested into the system.
    """
    __tablename__ = "users"

    # Unique identifier for the user (UUID)
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Personal Information
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    
    # URL-friendly slug for routing (e.g. dorothy-kahenya)
    slug = Column(String, unique=True, index=True, nullable=True)
    
    # Primary identifier for incoming webhook messages (Twilio/WhatsApp)
    # Must be a verified WhatsApp number via Cognito Custom Sender
    phone_number = Column(String, unique=True, nullable=False)
    
    # Security
    hashed_password = Column(String, nullable=True)
    email_verified = Column(Boolean, default=False)
    phone_number_verified = Column(Boolean, default=False)
    
    # Permissions Role: Controls access to specific dashboard features
    # - treasurer: Manages specific groups
    # - admin: Platform-level management
    # - super_admin: Infrastructure control
    role = Column(String, default=UserRole.TREASURER.value) 
    
    # Account Status
    is_active = Column(Boolean, default=True)
    # allow_ai_training: If True, the user's corrections are used to retrain the parsing model.
    allow_ai_training = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_active_at = Column(DateTime, nullable=True)
    
    preferences = Column(JSON, default=dict)

    # Relationships
    # A user can have multiple active feature subscriptions
    subscriptions = relationship("Subscription", back_populates="user")
    # A treasurer can own and manage multiple community groups
    groups = relationship("Group", back_populates="owner")