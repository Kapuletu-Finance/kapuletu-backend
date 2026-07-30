from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime
from uuid import UUID
from enum import Enum

class CampaignStatusEnum(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"

class CampaignSettings(BaseModel):
    report_title: Optional[str] = Field(None, description="Overrides the default campaign title on reports if set")
    report_footer: str = Field("Thank you for your support.")
    blank_slots: int = Field(3, ge=0)
    paid_indicator: str = Field("✔")
    require_pin: bool = Field(True)
    access_pin: Optional[str] = Field(None)
    remove_watermark: bool = Field(False)
    auto_send_reports: bool = Field(False)

class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, json_schema_extra={"example": "Medical Fund - Jane Doe"})
    description: Optional[str] = Field(None, max_length=1000, json_schema_extra={"example": "Fundraising for hospital expenses."})
    target_amount: float = Field(0.0, ge=0, json_schema_extra={"example": 50000.0})
    payment_instructions: Optional[str] = Field(None, max_length=1000, json_schema_extra={"example": "Paybill 123456, Account: JANE"})
    end_date: Optional[datetime] = Field(None)
    settings: Optional[CampaignSettings] = Field(None, alias="settings_override")

class CampaignUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    target_amount: Optional[float] = Field(None, ge=0)
    payment_instructions: Optional[str] = Field(None, max_length=1000)
    end_date: Optional[datetime] = Field(None)
    settings: Optional[CampaignSettings] = Field(None, alias="settings_override")

class CampaignOut(BaseModel):
    id: UUID = Field(alias="campaign_id", serialization_alias="id", json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"})
    group_id: UUID = Field(..., json_schema_extra={"example": "987e6543-e21b-34d5-c678-426614174999"})
    title: str = Field(..., json_schema_extra={"example": "Medical Fund - Jane Doe"})
    description: Optional[str] = Field(None)
    target_amount: float = Field(..., json_schema_extra={"example": 50000.0})
    payment_instructions: Optional[str] = Field(None)
    status: Optional[CampaignStatusEnum] = Field(CampaignStatusEnum.ACTIVE, json_schema_extra={"example": "active"})
    is_active: Optional[bool] = Field(True, json_schema_extra={"example": True})
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    slug: Optional[str] = Field(None, json_schema_extra={"example": "medical-fund-jane-doe"})
    is_favorite: Optional[bool] = Field(False, json_schema_extra={"example": True})
    end_date: Optional[datetime] = Field(None)
    
    # New Operational Metrics
    total_raised: float = Field(0.0, json_schema_extra={"example": 25000.0})
    progress_percentage: float = Field(0.0, json_schema_extra={"example": 50.0})
    contributor_count: int = Field(0, json_schema_extra={"example": 12})
    
    settings_override: Optional[CampaignSettings] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class PaginatedCampaignResponse(BaseModel):
    items: List[CampaignOut]
    total_items: int = Field(..., json_schema_extra={"example": 120})
    total_pages: int = Field(..., json_schema_extra={"example": 12})
    page: int = Field(..., json_schema_extra={"example": 1})
    limit: int = Field(..., json_schema_extra={"example": 10})

from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator
import zoneinfo
from datetime import timezone

class TransactionOut(BaseModel):
    transaction_id: UUID
    date: str = Field(alias="created_at", serialization_alias="date")
    amount: float
    name: Optional[str] = Field(None, alias="sender_name", serialization_alias="name")
    payment_method: str
    
    @field_validator('date', mode='before')
    def format_date(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            v = v.astimezone(zoneinfo.ZoneInfo("Africa/Nairobi"))
            return v.strftime("%Y-%m-%d %I:%M %p")
        return v
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class PaginatedTransactionResponse(BaseModel):
    items: List[TransactionOut]
    total_items: int
    total_pages: int
    page: int
    limit: int

class CampaignActivity(BaseModel):
    log_id: UUID
    action: str
    date: str = Field(alias="created_at", serialization_alias="date")
    details: Optional[Dict[str, Any]] = None
    
    @field_validator('date', mode='before')
    def format_date(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            v = v.astimezone(zoneinfo.ZoneInfo("Africa/Nairobi"))
            return v.strftime("%Y-%m-%d %I:%M %p")
        return v
    
    @model_validator(mode='after')
    def format_action_message(self) -> 'CampaignActivity':
        if self.details and self.details.get("message"):
            self.action = self.details.get("message")
        return self
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class ChartDataPoint(BaseModel):
    date: str
    amount: float

class ContributorPreview(BaseModel):
    name: str
    amount: float
    
class CampaignReportPreview(BaseModel):
    preview_text: str
    title: str
    description: Optional[str] = None
    raised: float
    target: float
    contributors: List[ContributorPreview]
    payment_instructions: Optional[str] = None
    footer: Optional[str] = None
    public_url: str

class PinResponse(BaseModel):
    pin: str

class PublicVerifyRequest(BaseModel):
    pin: Optional[str] = None

class PublicContributor(BaseModel):
    name: str
    amount: float
    date: datetime

class PublicWebReportOut(BaseModel):
    # Core Data
    campaign_title: str
    campaign_description: Optional[str] = None
    raised_amount: float
    target_amount: float
    progress_percentage: float
    
    # Contributors
    total_contributors: int
    contributors: List[PublicContributor]
    
    # Visual/Document Addons
    blank_slots_count: int
    payment_instructions: Optional[str] = None
    remaining_message: str
    footer_message: Optional[str] = None
    watermark: Optional[str] = None
    public_url: str
