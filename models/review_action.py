from sqlalchemy import Column, String, UUID
from .base import Base

class ReviewAction(Base):
    """
    ReviewAction Model: Tracks the history of actions taken on a pending transaction.
    
    This provides an audit trail of who approved, rejected, or edited a transaction
    before it reached the finalized ledger.
    """
    __tablename__ = "review_actions"

    # Unique identifier for the review event
    action_id = Column(UUID, primary_key=True)
    # The associated pending transaction
    pending_id = Column(UUID)
    # Type of action performed (e.g. 'APPROVE', 'REJECT', 'EDIT')
    action_type = Column(String)