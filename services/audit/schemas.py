from typing import Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

class AuditLogOut(BaseModel):
    log_id: str
    actor_id: Optional[str]
    action: str
    entity_type: str
    entity_id: str
    details: Dict[str, Any]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
