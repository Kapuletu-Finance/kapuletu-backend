from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class ReviewAllocationOut(BaseModel):
    member_name: str
    allocated_amount: float
    
    class Config:
        from_attributes = True

class LedgerEntryOut(BaseModel):
    transaction_id: str
    owner_id: str
    group_id: str
    campaign_id: Optional[str]
    transaction_code: str
    amount: float
    sender_phone: Optional[str]
    sender_name: Optional[str]
    status: str
    created_at: datetime
    ledger_hash: Optional[str]
    payment_method: Optional[str]
    source_evidence: Optional[str]
    
    # Immutability Check
    is_tampered: bool = Field(..., description="If true, the record has been modified after approval and its cryptographic seal is broken.")
    
    allocations: List[ReviewAllocationOut] = []
    
    class Config:
        from_attributes = True

class CampaignLedgerSummaryOut(BaseModel):
    campaign_id: str
    title: str
    target_amount: float
    total_raised: float
    transaction_count: int
    progress_percentage: float
    
    class Config:
        from_attributes = True

class LedgerResponse(BaseModel):
    summary: Optional[CampaignLedgerSummaryOut]
    entries: List[LedgerEntryOut]
    
class IntegrityCheckOut(BaseModel):
    transaction_id: str
    is_valid: bool
    original_hash: Optional[str]
    recalculated_hash: str
    message: str
