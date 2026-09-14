import datetime
from sqlalchemy import UUID, Column, ForeignKey, Numeric, String, Boolean, DateTime, UniqueConstraint
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
    __table_args__ = (
        UniqueConstraint('group_id', 'slug', name='uq_campaign_group_slug'),
        {'extend_existing': True}
    )

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
    
    slug = Column(String, index=True, nullable=True)
    short_code = Column(String(8), unique=True, index=True, nullable=True)
    is_favorite = Column(Boolean, default=False)
    end_date = Column(DateTime, nullable=True)
    
    from sqlalchemy import JSON
    settings_override = Column(JSON, default=dict)

    group = relationship("Group", back_populates="campaigns")