from sqlalchemy import UUID, Column, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from .base import Base

# from dataclasses import dataclass

# @dataclass
# class Campaign:
#     id: str
#     name: str
#     goal: float
#     current_amount: float


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
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.group_id"), nullable=False)
    # Descriptive title of the goal
    title = Column(String)
    description = Column(String, nullable=True)
    target_amount = Column(Numeric, default=0.0)
    payment_instructions = Column(String, nullable=True)

    group = relationship("Group", back_populates="campaigns")