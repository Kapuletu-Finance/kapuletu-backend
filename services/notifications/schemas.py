from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

class TargetType(str, Enum):
    all_members = "all_members"
    specific_member = "specific_member"
    custom_selection = "custom_selection"

class BroadcastChannel(str, Enum):
    in_app = "in_app"
    email = "email"
    whatsapp = "whatsapp"

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

class BroadcastIn(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "System Maintenance"})
    message: str = Field(..., json_schema_extra={"example": "The system will be down for 2 hours."})
    channels: List[BroadcastChannel] = Field(default=[BroadcastChannel.in_app])
    target_type: TargetType = Field(default=TargetType.all_members)
    target_ids: Optional[List[str]] = Field(None, description="List of user UUIDs if specific_member or custom_selection")
    target_emails: Optional[List[str]] = Field(None, description="List of emails if custom_selection")
