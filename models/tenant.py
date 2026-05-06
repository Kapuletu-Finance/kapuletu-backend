from sqlalchemy import Column, String, UUID, DateTime, ForeignKey
from sqlalchemy.orm import relationship
import datetime
import uuid
from .base import Base

class Group(Base):
    """
    Group (Tenant) Model: The primary multi-tenancy unit in KapuLetu.
    
    Each group represents an independent community organization (Chama).
    Data isolation is maintained by ensuring all transactions, members, 
    and campaigns are linked to a specific group_id.
    """
    __tablename__ = "groups"

    # Unique identifier for the group
    group_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The treasurer who owns this group
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    # The display name of the Chama
    name = Column(String, nullable=False)
    # Lifecycle status (active, archived)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="groups")
    campaigns = relationship("Campaign", back_populates="group")
