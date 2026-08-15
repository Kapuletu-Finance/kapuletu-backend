from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from common.utils import parse_uuid
from sqlalchemy.orm import Session
from sqlalchemy import select

from common.database import get_db
from common.auth_dependencies import get_verified_user
from services.finance.ledger_service import LedgerService
from services.reporting.template_engine import TemplateEngine
from services.reporting.schemas import ReportSettingsIn, ReportSettingsOut, PublicReportRequest, PublicReportOut, PublicContributorOut
from services.reporting.excel_gen import generate_excel_report
from services.reporting.pdf_gen import generate_pdf_report
from models.report_settings import CampaignReportSettings
from services.audit.service import AuditService

router = APIRouter(prefix="/reports", tags=["10. Reporting Service"])

from datetime import datetime, timedelta
from models.campaign import Campaign
from models.group import Group
from models.transaction import Transaction
from services.reporting.schemas import DashboardOverviewOut, CampaignSummary, RecentActivity, DailyCollection

@router.get("/dashboard", response_model=DashboardOverviewOut, summary="Executive Dashboard Summary")
async def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Returns comprehensive, high-level JSON data for frontend graphs and charts,
    including global totals, campaign breakdown, recent activity, and a 7-day 
    time-series chart of collections.
    """
    owner_id = current_user.get("sub")
    
    from sqlalchemy import func
    
    # 1. Total Collected
    total_stmt = select(func.sum(Transaction.amount)).where(
        Transaction.owner_id == parse_uuid(owner_id),
        Transaction.status == "approved"
    )
    total_collected = db.execute(total_stmt).scalar() or 0.0
    
    # True Transaction Count (Parent Txns - Split Parents + Allocations)
    total_parents_stmt = select(func.count(Transaction.transaction_id)).where(
        Transaction.owner_id == parse_uuid(owner_id),
        Transaction.status == "approved"
    )
    total_parents = db.execute(total_parents_stmt).scalar() or 0
    
    from models.review_allocation import ReviewAllocation
    alloc_count_stmt = select(func.count(ReviewAllocation.allocation_id)).join(Transaction).where(
        Transaction.owner_id == parse_uuid(owner_id),
        Transaction.status == "approved"
    )
    total_allocs = db.execute(alloc_count_stmt).scalar() or 0
    
    split_parents_stmt = select(func.count(func.distinct(ReviewAllocation.transaction_id))).join(Transaction).where(
        Transaction.owner_id == parse_uuid(owner_id),
        Transaction.status == "approved"
    )
    split_parents = db.execute(split_parents_stmt).scalar() or 0
    
    transaction_count = total_parents - split_parents + total_allocs
    
    # 2. Campaign Breakdown
    campaigns = db.execute(
        select(Campaign).join(Group).where(Group.owner_id == parse_uuid(owner_id))
    ).scalars().all()
    
    # Aggregate grouped by campaign
    breakdown_stmt = select(
        Transaction.campaign_id, 
        func.sum(Transaction.amount)
    ).where(
        Transaction.owner_id == parse_uuid(owner_id),
        Transaction.status == "approved"
    ).group_by(Transaction.campaign_id)
    
    raised_map = {str(row[0]): float(row[1]) for row in db.execute(breakdown_stmt).all() if row[0]}
    
    campaign_breakdown = []
    for c in campaigns:
        target = float(c.target_amount) if c.target_amount else 0.0
        raised = raised_map.get(str(c.campaign_id), 0.0)
        progress = (raised / target * 100) if target > 0 else 0.0
        surplus = max(0.0, raised - target)
        campaign_breakdown.append(
            CampaignSummary(
                campaign_id=str(c.campaign_id),
                title=c.title,
                target_amount=target,
                total_raised=raised,
                progress_percentage=round(progress, 2),
                surplus_amount=surplus
            )
        )
        
    # 3. Recent Activity (Top 10)
    from sqlalchemy.orm import joinedload
    recent_stmt = select(Transaction).options(joinedload(Transaction.allocations)).where(
        Transaction.owner_id == parse_uuid(owner_id),
        Transaction.status == "approved"
    ).order_by(Transaction.created_at.desc()).limit(10)
    
    recent_txns = db.execute(recent_stmt).scalars().unique().all()
    campaign_map = {str(c.campaign_id): c for c in campaigns}
    
    recent_activity = []
    for e in recent_txns:
        c_title = campaign_map[str(e.campaign_id)].title if e.campaign_id and str(e.campaign_id) in campaign_map else None
        
        if e.allocations:
            for alloc in e.allocations:
                recent_activity.append(
                    RecentActivity(
                        transaction_id=str(e.transaction_id),
                        sender_name=alloc.member_name or "Anonymous",
                        amount=float(alloc.allocated_amount),
                        campaign_title=c_title,
                        created_at=e.created_at
                    )
                )
        else:
            recent_activity.append(
                RecentActivity(
                    transaction_id=str(e.transaction_id),
                    sender_name=e.sender_name or "Unknown",
                    amount=float(e.amount),
                    campaign_title=c_title,
                    created_at=e.created_at
                )
            )
            
    # Sort and slice to ensure exactly 10 items even after flattening
    recent_activity.sort(key=lambda x: x.created_at, reverse=True)
    recent_activity = recent_activity[:10]
        
    # 4. Daily Collections (Last 7 Days)
    from datetime import timezone
    import zoneinfo
    now_eat = datetime.now(timezone.utc).astimezone(zoneinfo.ZoneInfo("Africa/Nairobi"))
    today = now_eat.date()
    daily_totals = { (today - timedelta(days=i)).strftime("%Y-%m-%d"): 0.0 for i in range(6, -1, -1) }
    
    cutoff_eat = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=zoneinfo.ZoneInfo("Africa/Nairobi"))
    cutoff_utc = cutoff_eat.astimezone(timezone.utc).replace(tzinfo=None)
    
    daily_txns = db.query(Transaction).filter(
        Transaction.owner_id == parse_uuid(owner_id),
        Transaction.status == "approved",
        Transaction.created_at >= cutoff_utc
    ).all()
    
    for txn in daily_txns:
        txn_eat = txn.created_at.replace(tzinfo=timezone.utc).astimezone(zoneinfo.ZoneInfo("Africa/Nairobi"))
        dt_str = txn_eat.strftime("%Y-%m-%d")
        if dt_str in daily_totals:
            daily_totals[dt_str] += float(txn.amount)
            
    daily_collections = [DailyCollection(date=k, amount=v) for k, v in daily_totals.items()]
    
    return DashboardOverviewOut(
        total_collected=float(total_collected),
        transaction_count=transaction_count,
        campaign_breakdown=campaign_breakdown,
        recent_activity=recent_activity,
        daily_collections_7_days=daily_collections
    )

@router.get("/whatsapp/{campaign_id}", summary="WhatsApp Smart Template")
async def get_whatsapp_report(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Returns the highly formatted, culturally aware WhatsApp text block.
    """
    engine = TemplateEngine(db)
    text = engine.generate_whatsapp_report(campaign_id)
    return {"whatsapp_format": text}

@router.post("/settings/{campaign_id}", response_model=ReportSettingsOut, summary="Update Report Settings")
async def update_settings(
    campaign_id: str,
    settings_in: ReportSettingsIn,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Overrides the Default KapuLetu Standard with custom Smart Templates.
    """
    engine = TemplateEngine(db)
    settings = engine.get_or_create_settings(campaign_id)
    
    settings.header_template = settings_in.header_template
    settings.footer_template = settings_in.footer_template
    settings.use_emojis = settings_in.use_emojis
    settings.show_status_text = settings_in.show_status_text
    settings.blank_slots_count = settings_in.blank_slots_count
    
    db.commit()
    db.refresh(settings)
    
    AuditService(db).log_action(
        actor_id=current_user.get("sub"),
        action="REPORT_SETTINGS_UPDATED",
        entity_type="CAMPAIGN",
        entity_id=campaign_id
    )
    
    return settings



@router.get("/export/excel/{campaign_id}", status_code=status.HTTP_202_ACCEPTED, summary="Export Ledger (Excel)")
async def export_excel(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    tz: str = None,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Triggers an asynchronous generation of an Excel file for the campaign.
    Allocations are flattened so splits appear as individual rows.
    """
    def _generate_and_upload():
        # Simulated async worker
        ledger_service = LedgerService(db)
        ledger = ledger_service.get_campaign_ledger(campaign_id=campaign_id, owner_id=current_user.get("sub"))
        
        # Flatten allocations for the Excel generator
        flattened_entries = []
        import copy
        for e in ledger.entries:
            if e.allocations:
                for alloc in e.allocations:
                    new_e = copy.deepcopy(e)
                    new_e.sender_name = alloc.member_name or e.sender_name
                    new_e.amount = float(alloc.allocated_amount)
                    flattened_entries.append(new_e)
            else:
                flattened_entries.append(e)
                
        title = ledger.summary.title if ledger.summary else "KapuLetu Campaign"
        target = ledger.summary.target_amount if ledger.summary else 0.0
        total = ledger.summary.total_raised if ledger.summary else 0.0

        # Simulate upload
        b64_excel = generate_excel_report(title=title, total_raised=total, target_amount=target, entries=flattened_entries, settings={}, tz=tz)
        import logging
        logging.getLogger(__name__).info(f"Excel Export Background Task Complete for Campaign {campaign_id}")

    background_tasks.add_task(_generate_and_upload)
    return {"status": "processing", "message": "Your report is generating in the background and will be ready shortly."}

@router.get("/export/pdf/{campaign_id}", status_code=status.HTTP_202_ACCEPTED, summary="Export Ledger (PDF)")
async def export_pdf(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    tz: str = None,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Triggers an asynchronous generation of a PDF document of the immutable ledger.
    """
    def _generate_and_upload():
        ledger_service = LedgerService(db)
        ledger = ledger_service.get_campaign_ledger(campaign_id=campaign_id, owner_id=current_user.get("sub"))
        
        # Flatten allocations for the PDF generator
        flattened_entries = []
        import copy
        for e in ledger.entries:
            if e.allocations:
                for alloc in e.allocations:
                    new_e = copy.deepcopy(e)
                    new_e.sender_name = alloc.member_name or e.sender_name
                    new_e.amount = float(alloc.allocated_amount)
                    flattened_entries.append(new_e)
            else:
                flattened_entries.append(e)

        title = ledger.summary.title if ledger.summary else "KapuLetu Campaign"
        target = ledger.summary.target_amount if ledger.summary else 0.0
        total = ledger.summary.total_raised if ledger.summary else 0.0
        
        b64_pdf = generate_pdf_report(title=title, total_raised=total, target_amount=target, entries=flattened_entries, settings={}, tz=tz)
        import logging
        logging.getLogger(__name__).info(f"PDF Export Background Task Complete for Campaign {campaign_id}")

    background_tasks.add_task(_generate_and_upload)
    return {"status": "processing", "message": "Your report is generating in the background and will be ready shortly."}
