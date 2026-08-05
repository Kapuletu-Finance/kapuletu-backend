from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime
from uuid import UUID

class ApprovalSchema(BaseModel):
    transaction_id: str
    action: str

class SplitAllocation(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "John Doe"})
    amount: float = Field(..., json_schema_extra={"example": 500.0})

class TransactionSplit(BaseModel):
    allocations: List[SplitAllocation]
    campaign_id: Optional[str] = None
    group_id: Optional[str] = None



class ManualEntryIn(BaseModel):
    group_id: str = Field(..., description="Target group UUID or slug for the contribution")
    campaign_id: str = Field(..., description="Target campaign UUID or slug for the contribution")
    amount: float = Field(..., json_schema_extra={"example": 1500.0})
    sender_name: str = Field(..., json_schema_extra={"example": "Joseph Njoroge"})
    sender_phone: Optional[str] = Field(None, json_schema_extra={"example": "+254700000000"})
    purpose: Optional[str] = Field(None, json_schema_extra={"example": "January Contribution"})
    transaction_code: Optional[str] = Field(None, json_schema_extra={"example": "MANUAL-12345"})

class TransactionActionIn(BaseModel):
    internal_note: Optional[str] = Field(None, json_schema_extra={"example": "Matched with paper receipt #123"})
    group_id: UUID = Field(...)
    campaign_id: UUID = Field(...)

class TransactionEditIn(BaseModel):
    extracted_amount: Optional[float] = Field(None, json_schema_extra={"example": 1500.0})
    extracted_sender_name: Optional[str] = Field(None, json_schema_extra={"example": "Joseph Amuyunzu"})
    extracted_code: Optional[str] = Field(None, json_schema_extra={"example": "ABC123XYZ"})
    extracted_date: Optional[str] = Field(None, json_schema_extra={"example": "2026-05-08"})

class BulkActionIn(BaseModel):
    pending_ids: List[str] = Field(..., json_schema_extra={"example": ["uuid-1", "uuid-2"]})
    internal_note: Optional[str] = Field(None, json_schema_extra={"example": "Bulk approval for Sunday collection"})
    group_id: Optional[str] = None
    campaign_id: Optional[str] = None

class PendingTransactionOut(BaseModel):
    pending_id: UUID
    raw_message: str
    sender_name: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = "KES"
    transaction_code: Optional[str] = None
    sender_phone: Optional[str] = None
    purpose: Optional[str] = None
    confidence_score: float
    workflow_status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class PaginatedPendingResponse(BaseModel):
    items: List[PendingTransactionOut]
    total_items: int
    total_pages: int
    page: int
    limit: int

class TransactionOut(BaseModel):
    transaction_id: UUID
    transaction_code: Optional[str] = None
    status: str
    message: Optional[str] = None
