import datetime
import uuid

from sqlalchemy import UUID, Column, DateTime, ForeignKey, JSON, String, Boolean
from sqlalchemy.orm import relationship

from .base import Base


class AIFeedback(Base):
    """
    AIFeedback Model: Stores treasurer corrections to parsed transaction data.
    These records are reviewed by admins and used to retrain the AI parser.
    """
    __tablename__ = "ai_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Link to the original pending transaction that was corrected
    pending_transaction_id = Column(UUID(as_uuid=True), ForeignKey("pending_transactions.pending_id"), nullable=False)
    # The treasurer who made the correction
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    # The actual data delta
    original_parsed_data = Column(JSON, nullable=False) # Data as extracted by AI
    corrected_data = Column(JSON, nullable=False) # Data as corrected by treasurer
    
    # Admin review status
    is_reviewed = Column(Boolean, default=False)
    is_approved_for_training = Column(Boolean, default=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    reviewed_at = Column(DateTime)

    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])

class ActiveLearningSample(Base):
    """
    ActiveLearningSample Model: Stores ground-truth NLP training samples 
    (raw text and exact character offsets of entities) for AI retraining.
    """
    __tablename__ = "active_learning_samples"

    sample_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_text = Column(String, nullable=False)
    entities = Column(JSON, nullable=False) # e.g. [(10, 15, "AMOUNT")]
    is_consumed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
