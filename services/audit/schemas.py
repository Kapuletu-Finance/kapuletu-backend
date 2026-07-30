from typing import Dict, Any, Optional
from pydantic import BaseModel, field_validator
from datetime import datetime, timezone

class AuditLogOut(BaseModel):
    log_id: str
    actor_id: Optional[str]
    action: str
    entity_type: str
    entity_id: str
    details: Dict[str, Any]
    ip_address: Optional[str]
    created_at: datetime

    @field_validator('created_at', mode='after')
    @classmethod
    def set_timezone(cls, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    class Config:
        from_attributes = True
