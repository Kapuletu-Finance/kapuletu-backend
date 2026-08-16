from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime

from common.utils import parse_uuid
from common.database import get_db
from common.auth_dependencies import get_verified_user
from models.group import Group
from models.campaign import Campaign
from models.transaction import Transaction
from models.pending_transaction import PendingTransaction
from models.subscription import Subscription, Plan
from models.audit_log import AuditLog
from services.workspace.schemas import WorkspaceOverviewOut, GroupOverview, SubscriptionOverview, WorkspaceActivity, CampaignOverview

router = APIRouter(prefix="/workspace", tags=["2. Workspace Overview"])

@router.get("/overview", response_model=WorkspaceOverviewOut, summary="Get Workspace Overview")
async def get_workspace_overview(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    import uuid
    owner_id_str = current_user.get("sub")
    owner_id = uuid.UUID(owner_id_str) if owner_id_str else None
    
    # 1. Total Groups and Active Groups preview
    groups = db.execute(select(Group).where(Group.owner_id ==parse_uuid(parse_uuid(owner_id)), Group.is_active == True)).scalars().all()
    total_groups = len(groups)
    
    # 2. Total Campaigns
    campaigns = db.execute(select(Campaign).join(Group).where(Group.owner_id ==parse_uuid(parse_uuid(owner_id)))).scalars().all()
    total_campaigns = len(campaigns)
    
    # Count campaigns per group with GROUP BY (Fix N+1 issue)
    campaign_counts = dict(
        db.query(Campaign.group_id, func.count(Campaign.campaign_id))
        .join(Group)
        .where(Group.owner_id ==parse_uuid(parse_uuid(owner_id)))
        .group_by(Campaign.group_id)
        .all()
    )
        
    # Get top 10 recent campaigns based on latest activity
    latest_txn_sq = (
        db.query(func.max(Transaction.created_at))
        .filter(Transaction.campaign_id == Campaign.campaign_id)
        .correlate(Campaign)
        .scalar_subquery()
    )
    
    recent_campaigns_query = (
        db.query(Campaign, Group.group_name, Group.currency, Group.slug.label("group_slug"))
        .join(Group)
        .filter(Group.owner_id == parse_uuid(parse_uuid(owner_id)))
        .order_by(func.coalesce(latest_txn_sq, Campaign.created_at).desc())
        .limit(10)
        .all()
    )
    
    recent_campaigns_list = []
    for camp, group_name, currency, group_slug in recent_campaigns_query:
        # Calculate amount raised for this campaign
        amount_raised = db.query(func.sum(Transaction.amount)).filter(
            Transaction.campaign_id == camp.campaign_id,
            Transaction.status == "approved"
        ).scalar() or 0.0
        
        recent_campaigns_list.append(CampaignOverview(
            campaign_id=str(camp.campaign_id),
            campaign_slug=camp.slug,
            title=camp.title,
            group_id=str(camp.group_id),
            group_slug=group_slug,
            group_name=group_name,
            target_amount=float(camp.target_amount or 0.0),
            amount_raised=float(amount_raised),
            currency=currency or "KES",
            status=camp.status,
            updated_at=camp.created_at # Note: sorting is now by latest_activity dynamically

        ))
        
    active_groups = []
    for g in groups[:5]: # Return top 5 for overview
        active_groups.append(GroupOverview(
            group_id=str(g.group_id),
            slug=g.slug,
            name=g.group_name,
            currency=g.currency or "KES",
            total_campaigns=campaign_counts.get(g.group_id, 0)
        ))

    # 3. Total Members (Distinct sender_phone in finalized transactions for this owner)
    total_members = db.query(Transaction.sender_phone).filter(Transaction.owner_id ==parse_uuid(parse_uuid(owner_id))).distinct().count()
    
    # 4. Total Collected (Currency Collision Fixed - Assuming KES Global Currency)
    total_collected = db.query(func.sum(Transaction.amount)).join(Group).filter(
        Transaction.owner_id ==parse_uuid(parse_uuid(owner_id)), 
        Transaction.status == "approved",
        Group.currency == "KES"
    ).scalar() or 0.0

    # 5. Pending Approvals
    # From transaction_repo, fetch_pending_transactions_by_owner uses is_processed == False.
    pending_approvals = db.query(PendingTransaction).filter(
        PendingTransaction.owner_id ==parse_uuid(parse_uuid(owner_id)),
        PendingTransaction.is_processed == False
    ).count()

    # 6. Subscription Info
    sub = db.execute(
        select(Subscription).where(
            Subscription.user_id ==parse_uuid(parse_uuid(owner_id)),
            Subscription.status == "active"
        )
    ).scalars().first()
    
    if sub:
        plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
        plan_name = plan.name if plan else "Unknown"
        status = "active"
        days_left = (sub.end_date.replace(tzinfo=None) - datetime.utcnow()).days if sub.end_date else None
    else:
        # Check Free Plan fallback
        plan_name = "Free Plan"
        status = "active"
        days_left = None
        
    subscription = SubscriptionOverview(plan_name=plan_name, status=status, days_left=days_left)
    
    # 7. Recent Activities
    logs = db.execute(
        select(AuditLog).where(AuditLog.actor_id ==parse_uuid(parse_uuid(owner_id)))
        .order_by(AuditLog.created_at.desc()).limit(10)
    ).scalars().all()
    
    recent_activities = []
    for log in logs:
        recent_activities.append(WorkspaceActivity(
            log_id=str(log.log_id),
            action=log.action,
            entity_type=log.entity_type,
            created_at=log.created_at,
            details=log.details
        ))
        
    return WorkspaceOverviewOut(
        total_groups=total_groups,
        total_campaigns=total_campaigns,
        total_members=total_members,
        pending_approvals=pending_approvals,
        total_collected=float(total_collected),
        subscription=subscription,
        active_groups=active_groups,
        recent_campaigns=recent_campaigns_list,
        recent_activities=recent_activities
    )
