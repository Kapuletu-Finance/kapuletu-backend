from typing import List, Optional
from pydantic import BaseModel, Field

class ReportSettingsIn(BaseModel):
    header_template: Optional[str] = None
    footer_template: Optional[str] = None
    use_emojis: bool = True
    show_status_text: bool = False
    blank_slots_count: int = 3
    
class ReportSettingsOut(ReportSettingsIn):
    public_access_pin: Optional[str] = None
    
    class Config:
        from_attributes = True

class PublicReportRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=4)

class PublicContributorOut(BaseModel):
    name: str
    amount: float

class PublicReportOut(BaseModel):
    campaign_title: str
    target_amount: float
    total_raised: float
    contributors: List[PublicContributorOut]
