from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from enum import Enum

class CampaignStatusEnum(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"

class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, json_schema_extra={"example": "Medical Fund - Jane Doe"})
    description: Optional[str] = Field(None, max_length=1000, json_schema_extra={"example": "Fundraising for hospital expenses."})
    target_amount: float = Field(0.0, ge=0, json_schema_extra={"example": 50000.0})
    payment_instructions: Optional[str] = Field(None, max_length=1000, json_schema_extra={"example": "Paybill 123456, Account: JANE"})

class CampaignUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    target_amount: Optional[float] = Field(None, ge=0)
    payment_instructions: Optional[str] = Field(None, max_length=1000)

class CampaignOut(BaseModel):
    id: UUID = Field(validation_alias="campaign_id", json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"})
    group_id: UUID = Field(..., json_schema_extra={"example": "987e6543-e21b-34d5-c678-426614174999"})
    title: str = Field(..., json_schema_extra={"example": "Medical Fund - Jane Doe"})
    description: Optional[str] = Field(None)
    target_amount: float = Field(..., json_schema_extra={"example": 50000.0})
    payment_instructions: Optional[str] = Field(None)
    status: CampaignStatusEnum = Field(..., json_schema_extra={"example": "active"})
    is_active: bool = Field(..., json_schema_extra={"example": True})
    created_at: datetime
    
    # New Operational Metrics
    total_raised: float = Field(0.0, json_schema_extra={"example": 25000.0})
    progress_percentage: float = Field(0.0, json_schema_extra={"example": 50.0})
    contributor_count: int = Field(0, json_schema_extra={"example": 12})

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class PaginatedCampaignResponse(BaseModel):
    items: List[CampaignOut]
    total_items: int = Field(..., json_schema_extra={"example": 120})
    total_pages: int = Field(..., json_schema_extra={"example": 12})
    page: int = Field(..., json_schema_extra={"example": 1})
    limit: int = Field(..., json_schema_extra={"example": 10})
