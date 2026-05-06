from sqlalchemy import Column, String, UUID, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class ReviewAllocation(Base):
    """
    ReviewAllocation Model: Handles split-payment logic for group contributions.
    
    In cases where a single large payment covers multiple people (e.g., a treasurer 
    paying for 5 members), this table tracks how the amount is split.
    """
    __tablename__ = "review_allocations"

    # Unique identifier for the allocation record
    allocation_id = Column(UUID(as_uuid=True), primary_key=True)
    # The associated finalized transaction
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=False)
    # The associated pending transaction (if still in review)
    pending_id = Column(UUID(as_uuid=True))
    # The name of the specific member receiving this portion of the funds
    member_name = Column(String)
    # The currency amount assigned to this member
    allocated_amount = Column(Numeric)

    transaction = relationship("Transaction", back_populates="allocations")
