from typing import Optional

from pydantic import BaseModel


class ApprovalRequest(BaseModel):
    pending_id: str
    action_type: str  # approve, reject, split
    notes: Optional[str]