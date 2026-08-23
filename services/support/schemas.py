from pydantic import BaseModel
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

class TicketMessageOut(BaseModel):
    message_id: UUID
    sender_id: UUID
    message: str
    created_at: datetime
    
    class Config:
        orm_mode = True

class TicketOut(BaseModel):
    ticket_id: UUID
    subject: str
    category: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
    sla_deadline: Optional[datetime] = None
    assigned_admin_id: Optional[UUID] = None
    
    class Config:
        orm_mode = True

class TicketDetailOut(TicketOut):
    messages: List[TicketMessageOut] = []
