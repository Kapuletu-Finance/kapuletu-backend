from models import Campaign
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import StreamingResponse
from common.utils import parse_uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, func, cast, String
import random
import io
import secrets
import logging

from common.database import get_db
from common.config import get_config
from common.auth_dependencies import get_verified_user
from services.campaigns.schemas import CampaignCreate, CampaignUpdate, CampaignOut, PaginatedCampaignResponse, PaginatedTransactionResponse, CampaignActivity, ChartDataPoint, CampaignReportPreview, PinResponse, PublicVerifyRequest, PublicWebReportOut
from services.auth.router import limiter
from repositories import campaign_repo, group_repo
from models.audit_log import AuditLog
from models.transaction import Transaction
from models.subscription import Subscription, Plan
from models.group import Group
from services.audit.service import AuditService

router = APIRouter(prefix="", tags=["5. Campaigns Management"])

def _verify_group_ownership(db: Session, group_id: str, owner_id: str):
    """Helper to verify that the group exists and belongs to the current user."""
    group = group_repo.get_group(db=db, identifier=str(group_id))
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    if str(group.owner_id) != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to manage campaigns for this group.")
    return group


@router.post("/groups/{group_id}/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED, summary="Create Campaign")
@limiter.limit("50/minute")
async def create_campaign(
    request: Request,
    group_id: str,
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Creates a new campaign for a specific group."""
    user_uuid = parse_uuid(current_user.get('sub'))
    group = _verify_group_ownership(db, str(group_id), str(user_uuid))
    
    # Enforce Plan Limits
    sub = db.execute(select(Subscription).where(Subscription.user_id == user_uuid)).scalars().first()
    if sub:
        plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
        if plan:
            # Get total campaigns across all groups owned by this user
            campaigns_count = db.execute(select(Campaign).join(Group).where(Group.owner_id == user_uuid)).scalars().all()
            if len(campaigns_count) >= plan.max_campaigns:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail="Campaign limit reached for your current plan. Please upgrade."
                )
                
    new_campaign = campaign_repo.create_campaign(
        db=db,
        group_id=str(group.group_id),
        title=payload.title,
        description=payload.description,
        target_amount=payload.target_amount,
        payment_instructions=payload.payment_instructions,
        short_code=secrets.token_hex(3)
    )
    
    AuditService(db).log_action(
        actor_id=current_user.get('sub'),
        action="CAMPAIGN_CREATED",
        entity_type="campaign",
        entity_id=str(new_campaign.campaign_id),
        details={"message": f"New campaign \"{new_campaign.title}\" created", "campaign_id": str(new_campaign.campaign_id)}
    )
    
    return new_campaign

@router.get("/groups/{group_id}/campaigns", response_model=PaginatedCampaignResponse, summary="List Campaigns")
@limiter.limit("50/minute")
async def list_campaigns(
    request: Request,
    group_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: str = Query(None, description="Search by title"),
    campaign_status: str = Query(None, description="active, archived, or all"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Lists all campaigns for a specific group with pagination, search, and dynamic stats."""
    group = _verify_group_ownership(db, str(group_id), current_user.get('sub'))
    
    campaigns = campaign_repo.get_group_campaigns(db=db, group_id=str(group.group_id), skip=skip, limit=limit, search=search, status=campaign_status)
    return campaigns

@router.get("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Get Campaign")
async def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Retrieves details of a specific campaign."""
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
        
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    from sqlalchemy import func
    from models.transaction import Transaction

    raised = db.query(func.sum(Transaction.amount)).filter(
        Transaction.campaign_id == parse_uuid(campaign.campaign_id),
        Transaction.status == "approved"
    ).scalar()
    
    raised = float(raised or 0.0)
    
    contributors = db.query(func.count(Transaction.transaction_id)).filter(
        Transaction.campaign_id == parse_uuid(campaign.campaign_id),
        Transaction.status == "approved"
    ).scalar()
    
    pm_sums = db.query(Transaction.payment_method, func.sum(Transaction.amount)).filter(
        Transaction.campaign_id == parse_uuid(campaign.campaign_id),
        Transaction.status == "approved"
    ).group_by(Transaction.payment_method).all()
    
    pm_map = {"mpesa": 0.0, "cash": 0.0, "bank": 0.0, "pledge": 0.0}
    for pm, amount in pm_sums:
        pm_lower = (pm or "cash").lower().replace("-", "").replace(" ", "")
        if "mpesa" in pm_lower:
            pm_map["mpesa"] += float(amount)
        elif "cash" in pm_lower:
            pm_map["cash"] += float(amount)
        elif "bank" in pm_lower:
            pm_map["bank"] += float(amount)
        elif "pledge" in pm_lower:
            pm_map["pledge"] += float(amount)
    
    campaign.total_raised = raised
    campaign.contributor_count = contributors or 0
    if campaign.target_amount and campaign.target_amount > 0:
        campaign.progress_percentage = round((raised / float(campaign.target_amount)) * 100, 2)
    else:
        campaign.progress_percentage = 0.0
        
    campaign.surplus_amount = max(0.0, float(raised) - float(campaign.target_amount)) if campaign.target_amount else 0.0
        
    campaign.total_mpesa = pm_map["mpesa"]
    campaign.total_cash = pm_map["cash"]
    campaign.total_bank = pm_map["bank"]
    campaign.total_pledges = pm_map["pledge"]
    
    campaign.mpesa_percentage = round((campaign.total_mpesa / raised) * 100, 2) if raised > 0 else 0.0
    campaign.cash_percentage = round((campaign.total_cash / raised) * 100, 2) if raised > 0 else 0.0
    campaign.bank_percentage = round((campaign.total_bank / raised) * 100, 2) if raised > 0 else 0.0
    campaign.pledges_percentage = round((campaign.total_pledges / raised) * 100, 2) if raised > 0 else 0.0
        
    return campaign

@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Update Campaign")
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Updates campaign details."""
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
        
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    if not campaign.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify an archived campaign.")
        
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    
    if "settings" in updates:
        settings_update = updates.pop("settings")
        # Ensure a completely new dict to force SQLAlchemy JSON update detection
        current_settings = dict(campaign.settings_override or {})
        current_settings.update(settings_update)
        updates["settings_override"] = current_settings
        
    if not updates:
        return campaign
        
    updated_campaign = campaign_repo.update_campaign(db=db, campaign_id=str(campaign.campaign_id), updates=updates)
    
    AuditService(db).log_action(
        actor_id=current_user.get('sub'),
        action="CAMPAIGN_UPDATED",
        entity_type="campaign",
        entity_id=str(campaign_id),
        details={"message": f"Campaign \"{updated_campaign.title}\" updated", "campaign_id": str(campaign_id)}
    )
    
    return updated_campaign

@router.patch("/campaigns/{campaign_id}/favorite", response_model=CampaignOut, summary="Toggle Favorite Campaign")
async def toggle_favorite_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Toggles the is_favorite status of a campaign."""
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
        
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    updated_campaign = campaign_repo.update_campaign(db=db, campaign_id=str(campaign.campaign_id), updates={"is_favorite": not campaign.is_favorite})
    return updated_campaign

@router.delete("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Archive Campaign")
async def archive_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Safely archives (soft deletes) a campaign."""
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
        
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    if not campaign.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is already archived.")
        
    archived_campaign = campaign_repo.archive_campaign(db=db, campaign_id=str(campaign.campaign_id))
    
    AuditService(db).log_action(
        actor_id=current_user.get('sub'),
        action="CAMPAIGN_ARCHIVED",
        entity_type="campaign",
        entity_id=str(campaign_id),
        details={"message": f"Campaign \"{archived_campaign.title}\" archived", "campaign_id": str(campaign_id)}
    )
    
    return archived_campaign

@router.post("/campaigns/{campaign_id}/regenerate-pin", response_model=PinResponse, summary="Regenerate Access PIN")
async def regenerate_campaign_pin(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    new_pin = str(random.randint(1000, 9999))
    current_settings = campaign.settings_override or {}
    current_settings["access_pin"] = new_pin
    
    updated_campaign = campaign_repo.update_campaign(db=db, campaign_id=str(campaign.campaign_id), updates={"settings_override": current_settings})
    return {"pin": new_pin}

@router.get("/campaigns/{campaign_id}/chart-data", response_model=List[ChartDataPoint], summary="Get Contribution Chart Data")
async def get_campaign_chart_data(
    campaign_id: str,
    filter: str = Query("this_month", description="this_week, this_month, this_year, all_time"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    transactions = db.execute(
        select(Transaction).where(Transaction.campaign_id == parse_uuid(str(campaign.campaign_id)), Transaction.status == "approved")
        .order_by(Transaction.created_at.asc())
    ).scalars().all()
    
    from datetime import datetime, timezone, timedelta
    import zoneinfo
    
    tz = zoneinfo.ZoneInfo("Africa/Nairobi")
    now_eat = datetime.now(timezone.utc).astimezone(tz)
    
    end_date = now_eat.date()
    start_date = None
    
    if filter == "this_week":
        start_date = end_date - timedelta(days=end_date.weekday())
    elif filter == "this_month":
        start_date = end_date.replace(day=1)
    elif filter == "this_year":
        start_date = end_date.replace(month=1, day=1)
    elif filter == "last_year":
        start_date = end_date.replace(year=end_date.year - 1, month=1, day=1)
        end_date = end_date.replace(year=end_date.year - 1, month=12, day=31)
    else: # all_time
        if transactions:
            start_date = transactions[0].created_at.replace(tzinfo=timezone.utc).astimezone(tz).date()
        else:
            start_date = end_date
            
    running_total = 0.0
    daily_sums = {}
    
    for txn in transactions:
        txn_eat = txn.created_at.replace(tzinfo=timezone.utc).astimezone(tz).date()
        if txn_eat < start_date:
            running_total += float(txn.amount)
        elif txn_eat <= end_date:
            daily_sums[txn_eat] = daily_sums.get(txn_eat, 0.0) + float(txn.amount)
            
    result = []
    
    if start_date not in daily_sums:
        result.append({
            "date": start_date.strftime("%Y-%m-%d"),
            "amount": running_total
        })
        
    sorted_dates = sorted(daily_sums.keys())
    for d in sorted_dates:
        running_total += daily_sums[d]
        result.append({
            "date": d.strftime("%Y-%m-%d"),
            "amount": running_total
        })
        
    if filter == "all_time" and (end_date - start_date).days > 365:
        monthly_result = {}
        for r in result:
            month_str = r["date"][:7]
            monthly_result[month_str] = r["amount"]
        return [{"date": k, "amount": v} for k, v in monthly_result.items()]
        
    return result

@router.get("/campaigns/{campaign_id}/transactions", response_model=PaginatedTransactionResponse, summary="List Campaign Transactions")
async def get_campaign_transactions(
    campaign_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str = Query(None),
    sort_by: Optional[str] = Query("date"),
    sort_order: Optional[str] = Query("desc"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    query = db.query(Transaction).filter(Transaction.campaign_id == parse_uuid(campaign.campaign_id), Transaction.status == "approved")
    if search:
        query = query.filter(Transaction.sender_name.ilike(f"%{search}%"))
        
    total_items = query.count()
    
    if sort_by == "amount":
        if sort_order == "asc":
            query = query.order_by(Transaction.amount.asc(), Transaction.created_at.desc())
        else:
            query = query.order_by(Transaction.amount.desc(), Transaction.created_at.desc())
    else:
        if sort_order == "asc":
            query = query.order_by(Transaction.created_at.asc())
        else:
            query = query.order_by(Transaction.created_at.desc())
            
    transactions = query.offset(skip).limit(limit).all()
    
    return {
        "items": transactions,
        "total_items": total_items,
        "total_pages": (total_items + limit - 1) // limit if limit > 0 else 0,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "limit": limit
    }

from services.approval.schemas import PaginatedPendingResponse
@router.get("/campaigns/{campaign_id}/inbox", response_model=PaginatedPendingResponse, summary="Get Campaign Inbox")
async def get_campaign_inbox(
    campaign_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    sort_by: Optional[str] = Query("date"),
    sort_order: Optional[str] = Query("desc"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    from repositories.transaction_repo import TransactionRepository
    repo = TransactionRepository(db)
    items, total = repo.fetch_pending_transactions_by_campaign(campaign.campaign_id, current_user.get('sub'), skip, limit, sort_by, sort_order)
    
    import math
    return {
        "items": items,
        "total_items": total,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
        "page": (skip // limit) + 1,
        "limit": limit
    }

@router.get("/campaigns/{campaign_id}/activities", response_model=List[CampaignActivity], summary="Get Campaign Activities")
async def get_campaign_activities(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    logs = db.execute(
        select(AuditLog).where(
            (
                (AuditLog.entity_type == "campaign") & 
                (AuditLog.entity_id == str(campaign.campaign_id))
            ) | (
                cast(AuditLog.details["campaign_id"], String).ilike(f'%{str(campaign.campaign_id)}%')
            )
        ).order_by(AuditLog.created_at.desc()).limit(5)
    ).scalars().all()
    
    return logs

@router.get("/campaigns/{campaign_id}/report-preview", response_model=CampaignReportPreview, summary="Generate WhatsApp Preview")
async def get_campaign_report_preview(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    settings = campaign.settings_override or {}
    title = settings.get("report_title")
    if not title or title == "Campaign Update":
        title = f"{campaign.title} Update"
        
    footer = settings.get("report_footer", "")
    indicator = settings.get("paid_indicator", "\u2713")
    
    def fmt_ksh(val: float) -> str:
        return f"{val:,.0f}" if float(val).is_integer() else f"{val:,.2f}"
    
    transactions = db.query(Transaction).filter(Transaction.campaign_id == parse_uuid(str(campaign.campaign_id)), Transaction.status == "approved").order_by(Transaction.created_at.desc()).all()
    
    raised = sum(t.amount for t in transactions)
    pm_map = {"mpesa": 0.0, "cash": 0.0, "bank": 0.0, "pledge": 0.0}
    for t in transactions:
        pm = (t.payment_method or "").lower().replace("-", "").replace(" ", "")
        if pm in pm_map:
            pm_map[pm] += float(t.amount)
        elif "mpesa" in pm:
            pm_map["mpesa"] += float(t.amount)
        elif "cash" in pm:
            pm_map["cash"] += float(t.amount)
        elif "bank" in pm:
            pm_map["bank"] += float(t.amount)
        elif "pledge" in pm:
            pm_map["pledge"] += float(t.amount)
    
    lines = []
    lines.append(f"*{title}*")
    lines.append("")
    if campaign.description:
        lines.append(campaign.description)
        lines.append("")
        
    remaining = max(0, float(campaign.target_amount) - float(raised))
    
    is_goal_met = float(campaign.target_amount) > 0 and float(raised) >= float(campaign.target_amount)
    
    if is_goal_met:
        lines.append("*Goal Achieved Update! 🌟*")
    else:
        lines.append("*Progress Update:*")
    
    if float(raised) >= float(campaign.target_amount):
        lines.append(f"So far, we have raised Ksh {fmt_ksh(raised)}, successfully surpassing our initial goal of Ksh {fmt_ksh(float(campaign.target_amount))}! Thank you to everyone who made this possible. The campaign remains open, and any further contributions are still greatly appreciated.")
    else:
        lines.append(f"So far, we have raised Ksh {fmt_ksh(raised)} against our goal of Ksh {fmt_ksh(float(campaign.target_amount))}. We have an amount remaining of Ksh {fmt_ksh(remaining)} to meet our goal. Every contribution counts.")
    
    lines.append("")
    
    if pm_map["mpesa"] > 0:
        lines.append(f"*Amount Received (M-Pesa):* Ksh {fmt_ksh(pm_map['mpesa'])}")
    if pm_map["cash"] > 0:
        lines.append(f"*Amount Received (Cash):* Ksh {fmt_ksh(pm_map['cash'])}")
    if pm_map["bank"] > 0:
        lines.append(f"*Amount Received (Bank):* Ksh {fmt_ksh(pm_map['bank'])}")
    if pm_map["pledge"] > 0:
        lines.append(f"*Amount Received (Pledge):* Ksh {fmt_ksh(pm_map['pledge'])}")
        
    if pm_map["mpesa"] > 0 or pm_map["cash"] > 0 or pm_map["bank"] > 0 or pm_map["pledge"] > 0:
        lines.append("")
        
    lines.append("To send your contributions, the payment instructions are as follows:")
    if campaign.payment_instructions:
        lines.append(f"{campaign.payment_instructions}")
    lines.append("")
    
    lines.append("*Contributions Received:*")
    if not transactions:
        dummy_contributors = [
            {"name": "Contributor A", "amount": 1000.0},
            {"name": "Contributor B", "amount": 2500.0},
            {"name": "Contributor C", "amount": 500.0},
            {"name": "Contributor D", "amount": 1500.0},
            {"name": "Contributor E", "amount": 2000.0},
            {"name": "Contributor F", "amount": 3000.0},
        ]
        for i, c in enumerate(dummy_contributors, 1):
            lines.append(f"{i}. {c['name']} - Ksh {fmt_ksh(c['amount'])} {indicator}")
        contributors_list = dummy_contributors
        start_idx = 7
    else:
        contributors_list = []
        for i, txn in enumerate(transactions, 1):
            name = txn.sender_name or "Anonymous"
            amount = float(txn.amount)
            contributors_list.append({"name": name, "amount": amount})
            lines.append(f"{i}. {name} - Ksh {fmt_ksh(amount)} {indicator}")
        start_idx = len(transactions) + 1
        
    try:
        blank_slots = int(settings.get("blank_slots", 3))
    except (ValueError, TypeError):
        blank_slots = 3
        
    for i in range(blank_slots):
        lines.append(f"{start_idx + i}.")
        
    lines.append("")
    if is_goal_met:
        lines.append("Thank you to everyone who has contributed so far. Your overwhelming support has helped us successfully reach our goal! The campaign is still ongoing, and we encourage you to continue supporting the cause.")
    else:
        lines.append("Thank you to everyone who has contributed so far. Your continued support is greatly appreciated as we work towards our goal.")
    lines.append("")
    
    if footer:
        lines.append(footer)
        lines.append("")
        
    frontend_url = get_config().FRONTEND_URL.rstrip('/')
    short_code = campaign.short_code or campaign.campaign_id
    public_url = f"{frontend_url}/r/{short_code}"
    
    lines.append("To view a more comprehensive report, click the link below:")
    lines.append(f"{public_url}")
    if settings.get("require_pin", True) and settings.get("access_pin"):
        lines.append(f"Access PIN: {settings.get('access_pin')}")
    if not settings.get("remove_watermark", False):
        lines.append("\n*Generated via KapuLetu*")
        
    return {
        "preview_text": "\n".join(lines),
        "title": title,
        "description": campaign.description,
        "raised": float(raised),
        "target": float(campaign.target_amount),
        "total_mpesa": pm_map["mpesa"],
        "total_cash": pm_map["cash"],
        "total_bank": pm_map["bank"],
        "total_pledges": pm_map["pledge"],
        "contributors": contributors_list,
        "payment_instructions": campaign.payment_instructions,
        "footer": footer,
        "public_url": public_url
    }

@router.get("/campaigns/{campaign_id}/export/excel", responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}}, summary="Export Transactions to Excel")
async def export_campaign_excel(
    campaign_id: str,
    tz: str = None,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    settings = campaign.settings_override or {}
    
    from services.reporting.excel_gen import generate_excel_report
    import base64
    
    txn_query = db.query(Transaction).filter(Transaction.campaign_id == parse_uuid(str(campaign.campaign_id)), Transaction.status == "approved")
    if txn_query.count() > 20000:
        raise HTTPException(status_code=400, detail="This campaign exceeds the 20,000 transaction limit for synchronous Excel export. Please contact support for a bulk export.")
        
    transactions = txn_query.order_by(Transaction.created_at.desc()).all()
    raised = txn_query.with_entities(func.sum(Transaction.amount)).scalar() or 0.0
    
    b64_excel = generate_excel_report(
        title=campaign.title,
        total_raised=float(raised),
        target_amount=float(campaign.target_amount),
        entries=transactions,
        settings=settings,
        tz=tz
    )
    
    excel_bytes = base64.b64decode(b64_excel)
    stream = io.BytesIO(excel_bytes)
    
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign.slug}_contributions.xlsx"}
    )

@router.get("/campaigns/{campaign_id}/export/pdf", responses={200: {"content": {"application/pdf": {}}}}, summary="Export Transactions to PDF")
async def export_campaign_pdf(
    campaign_id: str,
    tz: str = None,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    campaign = campaign_repo.get_campaign(db=db, identifier=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    settings = campaign.settings_override or {}
    
    from services.reporting.pdf_gen import generate_pdf_report
    import base64
    
    txn_query = db.query(Transaction).filter(Transaction.campaign_id == parse_uuid(str(campaign.campaign_id)), Transaction.status == "approved")
    if txn_query.count() > 5000:
        raise HTTPException(status_code=400, detail="This campaign exceeds the 5,000 transaction limit for synchronous PDF export. Please contact support for a bulk export.")
        
    transactions = txn_query.order_by(Transaction.created_at.desc()).all()
    raised = txn_query.with_entities(func.sum(Transaction.amount)).scalar() or 0.0
    
    b64_pdf = generate_pdf_report(
        title=campaign.title,
        total_raised=float(raised),
        target_amount=float(campaign.target_amount),
        entries=transactions,
        settings=settings,
        tz=tz
    )
    
    pdf_bytes = base64.b64decode(b64_pdf)
    stream = io.BytesIO(pdf_bytes)
    
    return StreamingResponse(
        stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign.slug}_contributions.pdf"}
    )

@router.post("/public/campaigns/{short_code}/verify", response_model=PublicWebReportOut, summary="Fetch Secure Public Web Report", description="Authenticates the PIN (if required) and returns a structured, professional JSON payload for rendering the public campaign web report.")
async def public_verify_campaign(
    short_code: str,
    req: PublicVerifyRequest,
    db: Session = Depends(get_db)
):
    import uuid
    from sqlalchemy import or_
    try:
        # Check if short_code is actually a UUID (fallback from missing short_codes)
        val = uuid.UUID(short_code)
        campaign = db.query(Campaign).filter(
            or_(Campaign.short_code == short_code, Campaign.campaign_id == str(val))
        ).first()
    except ValueError:
        campaign = db.query(Campaign).filter(Campaign.short_code == short_code).first()
        
    if not campaign or not campaign.group:
        raise HTTPException(status_code=404, detail="Campaign not found.")
        
    settings = campaign.settings_override or {}
    if settings.get("require_pin", True):
        access_pin = settings.get("access_pin")
        if access_pin and req.pin != access_pin:
            raise HTTPException(status_code=403, detail="Invalid PIN.")
            
    # Calculate raised
    raised = db.query(func.sum(Transaction.amount)).filter(Transaction.campaign_id == parse_uuid(str(campaign.campaign_id)), Transaction.status == "approved").scalar() or 0.0
    
    pm_sums = db.query(Transaction.payment_method, func.sum(Transaction.amount)).filter(
        Transaction.campaign_id == parse_uuid(str(campaign.campaign_id)),
        Transaction.status == "approved"
    ).group_by(Transaction.payment_method).all()
    
    pm_map = {"mpesa": 0.0, "cash": 0.0, "bank": 0.0, "pledge": 0.0}
    for pm, amount in pm_sums:
        pm_lower = (pm or "cash").lower().replace("-", "").replace(" ", "")
        if "mpesa" in pm_lower:
            pm_map["mpesa"] += float(amount)
        elif "cash" in pm_lower:
            pm_map["cash"] += float(amount)
        elif "bank" in pm_lower:
            pm_map["bank"] += float(amount)
        elif "pledge" in pm_lower:
            pm_map["pledge"] += float(amount)
            
    transactions_query = db.query(Transaction).filter(Transaction.campaign_id == parse_uuid(str(campaign.campaign_id)), Transaction.status == "approved").order_by(Transaction.created_at.desc())
    total_contributors = transactions_query.count()
    
    page = req.page
    limit = req.limit
    offset = (page - 1) * limit
    total_pages = (total_contributors + limit - 1) // limit if total_contributors > 0 else 1
    
    transactions = transactions_query.offset(offset).limit(limit).all()
    
    target_amount = float(campaign.target_amount)
    progress = (float(raised) / target_amount * 100) if target_amount > 0 else 0.0
    surplus_amount = max(0.0, float(raised) - target_amount)
    
    try:
        blank_slots = int(settings.get("blank_slots", 3))
    except (ValueError, TypeError):
        blank_slots = 3
        
    remaining = max(0, target_amount - float(raised))
    if float(raised) >= target_amount:
        remaining_message = f"We have successfully surpassed our initial goal of Ksh {target_amount:,.2f}! Thank you to everyone who made this possible. The campaign remains open, and any further contributions are still greatly appreciated."
    else:
        remaining_message = f"We still need Ksh {remaining:,.2f} to reach our goal. Every contribution counts."
    
    footer_message = settings.get("report_footer", None)
    watermark = "Generated via KapuLetu" if not settings.get("remove_watermark", False) else None
    
    frontend_url = get_config().FRONTEND_URL.rstrip('/')
    public_url = f"{frontend_url}/r/{campaign.short_code or campaign.campaign_id}"
    
    return {
        "campaign_id": str(campaign.campaign_id),
        "campaign_title": campaign.title,
        "campaign_description": campaign.description,
        "raised_amount": float(raised),
        "target_amount": target_amount,
        "progress_percentage": round(progress, 2),
        "surplus_amount": surplus_amount,
        "total_mpesa": pm_map["mpesa"],
        "total_cash": pm_map["cash"],
        "total_bank": pm_map["bank"],
        "total_pledges": pm_map["pledge"],
        "total_contributors": total_contributors,
        "page": page,
        "total_pages": total_pages,
        "contributors": [{"name": txn.sender_name or "Anonymous", "amount": float(txn.amount), "date": txn.created_at} for txn in transactions],
        "blank_slots_count": blank_slots,
        "payment_instructions": campaign.payment_instructions,
        "remaining_message": remaining_message,
        "raised": float(raised),
        "remaining": remaining,
        "payment_methods": pm_map,
        "footer_message": footer_message,
        "watermark": watermark,
        "public_url": public_url
    }
