from sqlalchemy import Column, String, UUID, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
import datetime
import uuid
from .base import Base

class Transaction(Base):
    """
    Transaction Model: Represents a finalized, official financial record.
    
    Once a pending transaction is approved by a treasurer, it is converted into 
    this model. Data in this table is mirrored in the immutable ledger (QLDB) 
    and serves as the 'Source of Truth' for all financial reporting and balance calculations.
    """
    __tablename__ = "transactions"

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
    transaction_code = Column(String, unique=True, nullable=False)
    # amount: The finalized, validated currency amount.
    amount = Column(Numeric(12, 2), nullable=False)
    # sender_phone: The phone number of the member who made the contribution.
    sender_phone = Column(String)
    
    # Workflow Status
    # status: Current state (approved, voided). Finalized transactions are usually 'approved'.
    status = Column(String, default="pending") 
    # created_at: The timestamp when this transaction was officially committed to the ledger.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    # A single transaction can be split into multiple allocations (e.g. 50% Dues, 50% Social).
    allocations = relationship("ReviewAllocation", back_populates="transaction")