from typing import Dict, Any, List
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from common.utils import parse_uuid
from common.database import get_db
from common.auth_dependencies import get_verified_user
from models.subscription import Subscription, Plan, UsageTracking

def get_active_plan(
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
) -> Plan:
    """Helper to fetch the user's currently active plan."""
    user_id = current_user.get("sub")
    
    # Get active subscription
    sub = db.execute(
        select(Subscription).where(
            Subscription.user_id == parse_uuid(user_id),
            Subscription.status == "active"
        )
    ).scalars().first()
    
    if not sub:
        # Fallback to Free plan if no active subscription exists
        free_plan = db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
        if not free_plan:
            raise HTTPException(status_code=500, detail="System configuration error: Free plan not found.")
        return free_plan
        
    plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
    if not plan:
        raise HTTPException(status_code=500, detail="System configuration error: Linked plan not found.")
        
    return plan


class RequireFeature:
    """
    FastAPI Dependency to explicitly guard endpoints by feature flags.
    Usage:
        @router.get("/export/excel", dependencies=[Depends(RequireFeature("excel_exports"))])
    """
    def __init__(self, feature_name: str):
        self.feature_name = feature_name

    def __call__(self, plan: Plan = Depends(get_active_plan)):
        features = plan.allowed_features or {}
        if not features.get(self.feature_name, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Upgrade required. Your current plan ({plan.name}) does not support {self.feature_name}."
            )
        return True


class CheckLimit:
    """
    FastAPI Dependency to enforce resource constraints.
    Usage:
        @router.post("/campaigns", dependencies=[Depends(CheckLimit("max_campaigns"))])
    """
    def __init__(self, metric_name: str):
        self.metric_name = metric_name

    def __call__(
        self, 
        plan: Plan = Depends(get_active_plan),
        db: Session = Depends(get_db), 
        current_user: Dict[str, Any] = Depends(get_verified_user)
    ):
        # Dynamically map metric name to the Plan limit column
        limit_value = getattr(plan, self.metric_name, None)
        if limit_value is None:
            raise HTTPException(status_code=500, detail=f"Invalid limit metric: {self.metric_name}")
            
        user_id = current_user.get("sub")
        
        # In a real scenario, this would query current count. For example:
        if self.metric_name == "max_groups":
            from models.group import Group
            current_count = db.execute(select(Group).where(Group.owner_id == parse_uuid(user_id))).scalars().all()
            current_count = len(current_count)
        elif self.metric_name == "max_campaigns":
            from models.campaign import Campaign
            from models.group import Group
            current_count = db.execute(select(Campaign).join(Group).where(Group.owner_id == parse_uuid(user_id))).scalars().all()
            current_count = len(current_count)
        else:
            # Fallback to usage tracking table
            usage = db.execute(
                select(UsageTracking).where(
                    UsageTracking.user_id == parse_uuid(user_id),
                    UsageTracking.metric_name == self.metric_name
                )
            ).scalars().first()
            current_count = usage.current_value if usage else 0
            
        if current_count >= limit_value:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Resource limit reached. Your {plan.name} plan only allows {limit_value} {self.metric_name.replace('max_', '')}."
            )
        return True
