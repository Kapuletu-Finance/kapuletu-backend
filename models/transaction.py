import datetime
import uuid

from sqlalchemy import UUID, Column, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import Base


class Transaction(Base):
    """
    Transaction Model: Represents a finalized, official financial record.
    
    Once a pending transaction is approved by a treasurer, it is converted into 
    this model. Data in this table is mirrored in the immutable ledger (QLDB) 
    and serves as the 'Source of Truth' for all financial reporting and balance calculations.
    """
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint('owner_id', 'transaction_code', name='uix_owner_txn_code'),)

    # Unique identifier for the finalized transaction
    transaction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Ownership & Foreign Keys
    # owner_id: The treasurer who authorized this record.
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    # group_id: The community group (tenant) that owns this transaction.
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.group_id"), nullable=False)
    # campaign_id: The specific goal or campaign this money was contributed toward.
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"), nullable=True)
    
    # Financial Details
    # transaction_code: The unique identifier from the payment provider (e.g. M-Pesa ID).
    transaction_code = Column(String, nullable=False)
    # amount: The finalized, validated currency amount.
    amount = Column(Numeric(12, 2), nullable=False)
    # sender_phone: The phone number of the member who made the contribution.
    sender_phone = Column(String)
    # sender_name: The name of the member who made the contribution (if parsed or manual).
    sender_name = Column(String, nullable=True)
    
    # Workflow Status
    # status: Current state (approved, voided). Finalized transactions are usually 'approved'.
    status = Column(String, default="pending") 
    # created_at: The timestamp when this transaction was officially committed to the ledger.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # ledger_hash: A SHA-256 integrity seal that ensures the record has not been modified after approval.
    ledger_hash = Column(String, nullable=True)
    # payment_method: Automatic tag (e.g., "M-Pesa", "Cash", "Bank Transfer").
    payment_method = Column(String, default="Cash")
    # source_evidence: The raw SMS string or the manual entry note. Internal use only.
    source_evidence = Column(String, nullable=True)

    # Relationships
    # A single transaction can be split into multiple allocations (e.g. 50% Dues, 50% Social).
    allocations = relationship("ReviewAllocation", back_populates="transaction")