from sqlalchemy import Column, String, UUID, Boolean, DateTime, Numeric, Text
import datetime
import uuid
from .base import Base

from sqlalchemy import Column, String, UUID, Numeric, Text, Boolean, DateTime, Float
from .users import Base
import datetime
import uuid

class PendingTransaction(Base):
    """
    PendingTransaction Model: Represents a financial record in its 'Unvalidated' state.
    
    This table stores the raw data received from ingestion (SMS/WhatsApp) and the 
    accompanying AI-extracted fields. Data remains here until a treasurer reviews 
    and 'Approves' it, at which point it is transitioned to the immutable ledger.
    """
    __tablename__ = "pending_transactions"

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
    transaction_code = Column(String, unique=True, nullable=True)
    # sender_phone: The phone number of the person who made the payment.
    sender_phone = Column(String, nullable=True) 
    # purpose: Any notes or purpose extracted from the message (e.g. 'January Dues').
    purpose = Column(String, nullable=True)
    
    # Metadata & Workflow State
    # confidence_score: The AI's certainty level (0.0 to 1.0) regarding the extraction.
    confidence_score = Column(Float, default=0.0)
    # workflow_status: Current state in the treasurer's pipeline (pending, approved, rejected).
    workflow_status = Column(String, default="pending") 
    # is_processed: Flag to indicate if the transaction has been finalized in the ledger.
    is_processed = Column(Boolean, default=False)
    # created_at: Timestamp when the ingestion occurred.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)