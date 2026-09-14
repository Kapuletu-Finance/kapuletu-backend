from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class TicketCreate(BaseModel):
    subject: str
    message: str
    category: str
    priority: str

class TicketReply(BaseModel):
    message: str

class TicketRatingCreate(BaseModel):
    issue_resolved: bool
    satisfaction_level: int = Field(..., ge=1, le=5)
    response_quality: Optional[int] = Field(None, ge=1, le=5)
    response_speed: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None

class TicketMessageOut(BaseModel):
    message_id: UUID
    sender_id: UUID
    sender_name: Optional[str] = None
    message: str
    created_at: datetime
    
    class Config:
        orm_mode = True

class TicketOut(BaseModel):
    ticket_id: UUID
    user_id: UUID
    subject: str
    category: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
    sla_deadline: Optional[datetime] = None
    assigned_admin_id: Optional[UUID] = None
    has_rating: Optional[bool] = False
    
    class Config:
        orm_mode = True

class TicketDetailOut(TicketOut):
    messages: List[TicketMessageOut] = []
