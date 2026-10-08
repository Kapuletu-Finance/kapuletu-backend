from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class NotificationOut(BaseModel):
    notification_id: str = Field(..., json_schema_extra={"example": "uuid-string"})
    title: str = Field(..., json_schema_extra={"example": "Transaction Approved"})
    message: str = Field(..., json_schema_extra={"example": "Your transaction of KES 500 has been approved."})
    type: str = Field(..., json_schema_extra={"example": "transaction_approved"})
    is_read: bool = Field(..., json_schema_extra={"example": False})
    related_entity_id: Optional[str] = Field(None, json_schema_extra={"example": "uuid-string"})
    created_at: datetime

    class Config:
        from_attributes = True

class NotificationListOut(BaseModel):
    notifications: List[NotificationOut]
    unread_count: int = Field(..., json_schema_extra={"example": 3})

class UnreadCountOut(BaseModel):
    unread_count: int = Field(..., json_schema_extra={"example": 3})
