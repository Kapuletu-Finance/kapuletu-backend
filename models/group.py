import datetime
import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from .base import Base


class Group(Base):
    """
    Group Model: Represents a community organization or Chamas.
    
    This is the primary organizational unit in KapuLetu. 
    A treasurer can manage multiple groups, each with its own members,
    campaigns, and financial history.
    """
    __tablename__ = "groups"
    __table_args__ = {'extend_existing': True}

    # Unique identifier for the group
    group_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The treasurer who owns/manages this group
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    # The name of the group (e.g. 'St. Peters Welfare')
    group_name = Column(String, nullable=False)
    # Optional description of the group's purpose
    description = Column(String, nullable=True)
    # Primary currency used for this group's transactions (Default: KES)
    currency = Column(String(3), default="KES")
    # Lifecycle status (active, archived)
    status = Column(String, default="active")
    # Boolean flag for quick status checks
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="groups")
    campaigns = relationship("Campaign", back_populates="group")