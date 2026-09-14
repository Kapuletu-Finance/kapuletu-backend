import datetime
import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, Float, Numeric, String, Text, UniqueConstraint

from .base import Base


class PendingTransaction(Base):
    """
    PendingTransaction Model: Represents a financial record in its 'Unvalidated' state.
    
    This table stores the raw data received from ingestion (SMS/WhatsApp) and the 
    accompanying AI-extracted fields. Data remains here until a treasurer reviews 
    and 'Approves' it, at which point it is transitioned to the immutable ledger.
    """
    __tablename__ = "pending_transactions"
    __table_args__ = (UniqueConstraint('owner_id', 'transaction_code', name='uix_pending_owner_txn_code'),)

    # Unique Identifier for the pending record
    pending_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Ownership & Context
    # owner_id: The treasurer responsible for this transaction.
    owner_id = Column(UUID(as_uuid=True), nullable=False) 
    # group_id: The community group this transaction belongs to (assigned during approval).
    group_id = Column(UUID(as_uuid=True), nullable=True)
    # campaign_id: The specific fundraising campaign this maps to (assigned during approval).
    campaign_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Raw Data: The original, unaltered message received from the webhook.
    raw_message = Column(Text, nullable=False)
    
    # Parsed Data (Extracted via AI/Heuristics)
    # sender_name: The name of the contributor identified in the message.
    sender_name = Column(String, nullable=True)
    # amount: The numerical value of the payment.
    amount = Column(Numeric(12, 2), nullable=True)
    # currency: Defaults to KES (Kenyan Shillings).
    currency = Column(String, default="KES")
    # transaction_code: The unique M-Pesa or Bank reference code (Used for Idempotency).
    transaction_code = Column(String, nullable=True)
    # sender_phone: The phone number of the person who made the payment.
    sender_phone = Column(String, nullable=True) 
    # purpose: Any notes or purpose extracted from the message (e.g. 'January Dues').
    purpose = Column(String, nullable=True)
    
    # AI Governance: Snapshot of the original output from the NLP engine.
    # This is used to track corrections for model retraining.
    from sqlalchemy import JSON
    original_ai_output = Column(JSON, nullable=True)
    
    # Metadata & Workflow State
    # confidence_score: The AI's certainty level (0.0 to 1.0) regarding the extraction.
    confidence_score = Column(Float, default=0.0)
    # workflow_status: Current state in the treasurer's pipeline (pending, approved, rejected).
    workflow_status = Column(String, default="pending") 
    # is_processed: Flag to indicate if the transaction has been finalized in the ledger.
    is_processed = Column(Boolean, default=False)
    
    # Audit trail for processed transactions
    processed_at = Column(DateTime, nullable=True)
    processed_by = Column(UUID(as_uuid=True), nullable=True) # ID of the treasurer who acted
    rejection_reason = Column(String, nullable=True)

    # payment_method: Automatic tag (e.g., "M-Pesa", "Cash").
    payment_method = Column(String, default="Cash")
    # source_evidence: The raw message or default text.
    source_evidence = Column(String, nullable=True)
    # created_at: Timestamp when the ingestion occurred.
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))