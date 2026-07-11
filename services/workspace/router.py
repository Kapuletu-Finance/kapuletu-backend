from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime

from common.database import get_db
from common.auth_dependencies import get_verified_user
from models.group import Group
from models.campaign import Campaign
from models.transaction import Transaction
from models.pending_transaction import PendingTransaction
from models.subscription import Subscription, Plan
from models.audit_log import AuditLog
from services.workspace.schemas import WorkspaceOverviewOut, GroupOverview, SubscriptionOverview, WorkspaceActivity

router = APIRouter(prefix="/workspace", tags=["2. Workspace Overview"])

@router.get("/overview", response_model=WorkspaceOverviewOut, summary="Get Workspace Overview")
async def get_workspace_overview(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    owner_id = current_user.get("sub")
    
    # 1. Total Groups and Active Groups preview
    groups = db.execute(select(Group).where(Group.owner_id == owner_id, Group.is_active == True)).scalars().all()
    total_groups = len(groups)
    
    # 2. Total Campaigns
    campaigns = db.execute(select(Campaign).join(Group).where(Group.owner_id == owner_id)).scalars().all()
    total_campaigns = len(campaigns)
    
    # Count campaigns per group for the preview
    campaign_counts = {}
    for c in campaigns:
        cid = str(c.group_id)
        campaign_counts[cid] = campaign_counts.get(cid, 0) + 1
        
    active_groups = []
    for g in groups[:5]: # Return top 5 for overview
        active_groups.append(GroupOverview(
            group_id=str(g.group_id),
            name=g.group_name,
            currency=g.currency or "KES",
            total_campaigns=campaign_counts.get(str(g.group_id), 0)
        ))

    # 3. Total Members (Distinct sender_phone in finalized transactions for this owner)
    total_members = db.query(Transaction.sender_phone).filter(Transaction.owner_id == owner_id).distinct().count()
    
    # 4. Total Collected
    total_collected = db.query(func.sum(Transaction.amount)).filter(
        Transaction.owner_id == owner_id, 
        Transaction.status == "approved"
    ).scalar() or 0.0

    # 5. Pending Approvals
    pending_approvals = db.query(PendingTransaction).filter(
        PendingTransaction.owner_id == owner_id, 
        PendingTransaction.status == "pending" # or check is_processed == False depending on the model
    ).count()
    
    # If the model uses is_processed instead of status == "pending", let's be safe and check both or rely on what repo does.
    # From transaction_repo, fetch_pending_transactions_by_owner uses is_processed == False.
    pending_approvals = db.query(PendingTransaction).filter(
        PendingTransaction.owner_id == owner_id,
        PendingTransaction.is_processed == False
    ).count()

    # 6. Subscription Info
    sub = db.execute(
        select(Subscription).where(
            Subscription.user_id == owner_id,
            Subscription.status == "active"
        )
    ).scalars().first()
    
    if sub:
        plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
        plan_name = plan.name if plan else "Unknown"
        status = "active"
        days_left = (sub.current_period_end.replace(tzinfo=None) - datetime.utcnow()).days if sub.current_period_end else None
    else:
        # Check Free Plan fallback
        plan_name = "Free Plan"
        status = "active"
        days_left = None
        
    subscription = SubscriptionOverview(plan_name=plan_name, status=status, days_left=days_left)
    
    # 7. Recent Activities
    logs = db.execute(
        select(AuditLog).where(AuditLog.actor_id == owner_id)
        .order_by(AuditLog.created_at.desc()).limit(10)
    ).scalars().all()
    
    recent_activities = []
    for log in logs:
        recent_activities.append(WorkspaceActivity(
            log_id=str(log.log_id),
            action=log.action,
            entity_type=log.entity_type,
            created_at=log.created_at
        ))
        
    return WorkspaceOverviewOut(
        total_groups=total_groups,
        total_campaigns=total_campaigns,
        total_members=total_members,
        pending_approvals=pending_approvals,
        total_collected=float(total_collected),
        subscription=subscription,
        active_groups=active_groups,
        recent_activities=recent_activities
    )
