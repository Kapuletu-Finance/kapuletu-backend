from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

class GroupOverview(BaseModel):
    group_id: str
    name: str
    currency: str
    total_campaigns: int

class CampaignOverview(BaseModel):
    campaign_id: str
    title: str
    group_id: str
    group_name: str
    target_amount: float
    amount_raised: float
    currency: str
    updated_at: datetime

class SubscriptionOverview(BaseModel):
    plan_name: str
    status: str
    days_left: Optional[int]

class WorkspaceActivity(BaseModel):
    log_id: str
    action: str
    entity_type: str
    created_at: datetime
    details: Optional[dict] = None

class WorkspaceOverviewOut(BaseModel):
    total_groups: int
    total_campaigns: int
    total_members: int
    pending_approvals: int
    total_collected: float
    subscription: SubscriptionOverview
    active_groups: List[GroupOverview]
    recent_campaigns: List[CampaignOverview]
    recent_activities: List[WorkspaceActivity]
