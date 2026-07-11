import datetime
from sqlalchemy import UUID, Column, ForeignKey, Numeric, String, Boolean, DateTime
from sqlalchemy.orm import relationship

from .base import Base

class Campaign(Base):
    """
    Campaign Model: Represents a specific fundraising or savings goal.
    
    Examples: 'Welfare Fund', 'Investment Project A', 'End of Year Party'.
    All transactions in the system can optionally be mapped to a campaign
    to track progress against a target amount.
    """
    __tablename__ = "campaigns"

    # Unique identifier for the campaign
    campaign_id = Column(UUID(as_uuid=True), primary_key=True)
    # The group (tenant) this campaign belongs to
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.group_id"), nullable=False, index=True)
    # Descriptive title of the goal
    title = Column(String)
    description = Column(String, nullable=True)
    target_amount = Column(Numeric, default=0.0)
    payment_instructions = Column(String, nullable=True)
    
    # Lifecycle status
    status = Column(String, default="active")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    from sqlalchemy import JSON
    settings_override = Column(JSON, default=dict)

    group = relationship("Group", back_populates="campaigns")