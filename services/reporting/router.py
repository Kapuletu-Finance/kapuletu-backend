from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter(prefix="/reports", tags=["9. Reporting Service"])

from datetime import datetime, timedelta
from models.campaign import Campaign
from models.group import Group
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
    ledger_service = LedgerService(db)
    ledger = ledger_service.get_global_ledger(owner_id=owner_id)
    
    valid_entries = [e for e in ledger.entries if not e.is_tampered]
    total_collected = sum(e.amount for e in valid_entries)
    
    # Map Campaigns
    campaigns = db.execute(
        select(Campaign).join(Group).where(Group.owner_id == owner_id)
    ).scalars().all()
    campaign_map = {str(c.campaign_id): c for c in campaigns}
    
    # Campaign Breakdown
    breakdown_dict = {}
    for c in campaigns:
        breakdown_dict[str(c.campaign_id)] = {
            "title": c.title,
            "target": float(c.target_amount) if c.target_amount else 0.0,
            "raised": 0.0
        }
        
    for e in valid_entries:
        if e.campaign_id and e.campaign_id in breakdown_dict:
            breakdown_dict[e.campaign_id]["raised"] += e.amount

    campaign_breakdown = []
    for cid, data in breakdown_dict.items():
        progress = (data["raised"] / data["target"] * 100) if data["target"] > 0 else 0.0
        campaign_breakdown.append(
            CampaignSummary(
                campaign_id=cid,
                title=data["title"],
                target_amount=data["target"],
                total_raised=data["raised"],
                progress_percentage=round(progress, 2)
            )
        )
        
    # Recent Activity (Top 10)
    recent_activity = []
    for e in valid_entries[:10]:
        c_title = campaign_map[e.campaign_id].title if e.campaign_id and e.campaign_id in campaign_map else None
        recent_activity.append(
            RecentActivity(
                transaction_id=str(e.transaction_id),
                sender_name=e.sender_name or "Unknown",
                amount=e.amount,
                campaign_title=c_title,
                created_at=e.created_at
            )
        )
        
    # Daily Collections (Last 7 Days)
    today = datetime.utcnow().date()
    daily_totals = { (today - timedelta(days=i)).strftime("%Y-%m-%d"): 0.0 for i in range(6, -1, -1) }
    
    for e in valid_entries:
        dt_str = e.created_at.strftime("%Y-%m-%d")
        if dt_str in daily_totals:
            daily_totals[dt_str] += e.amount
            
    daily_collections = [DailyCollection(date=k, amount=v) for k, v in daily_totals.items()]
    
    return DashboardOverviewOut(
        total_collected=total_collected,
        transaction_count=len(valid_entries),
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

@router.post("/public/{campaign_id}", response_model=PublicReportOut, summary="Secure Public Ledger Access")
async def public_web_report(
    campaign_id: str,
    req: PublicReportRequest,
    db: Session = Depends(get_db)
):
    """
    The endpoint for the Public Web Report link. Requires the PIN.
    Strips out sensitive information like phone numbers.
    """
    settings = db.execute(select(CampaignReportSettings).where(CampaignReportSettings.campaign_id == campaign_id)).scalars().first()
    if not settings or settings.public_access_pin != req.pin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Access PIN")
        
    ledger_service = LedgerService(db)
    # Note: Using public bypass means we don't have owner_id, so we temporarily fetch owner_id from campaign
    from models.campaign import Campaign
    campaign = db.execute(select(Campaign).where(Campaign.campaign_id == campaign_id)).scalars().first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        
    ledger = ledger_service.get_campaign_ledger(campaign_id=campaign_id, owner_id=str(campaign.group.owner_id))
    
    contributors = []
    for e in ledger.entries:
        if not e.is_tampered:
            name = e.sender_name or "Anonymous Member"
            contributors.append(PublicContributorOut(name=name, amount=e.amount))
            
    return PublicReportOut(
        campaign_title=campaign.title,
        target_amount=ledger.summary.target_amount if ledger.summary else 0.0,
        total_raised=ledger.summary.total_raised if ledger.summary else 0.0,
        contributors=contributors
    )

@router.get("/export/excel/{campaign_id}", summary="Export Ledger (Excel)")
async def export_excel(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Generates a real-time Base64 Excel file of the immutable ledger.
    """
    ledger_service = LedgerService(db)
    ledger = ledger_service.get_campaign_ledger(campaign_id=campaign_id, owner_id=current_user.get("sub"))
    
    # Convert entries to dict
    data = []
    for e in ledger.entries:
        data.append({
            "Transaction ID": e.transaction_id,
            "Code": e.transaction_code,
            "Name": e.sender_name,
            "Phone": e.sender_phone,
            "Amount": e.amount,
            "Date": e.created_at.strftime("%Y-%m-%d"),
            "Tampered": e.is_tampered
        })
        
    b64_excel = generate_excel_report(data)
    return {"filename": f"ledger_{campaign_id}.xlsx", "file_data": b64_excel}

@router.get("/export/pdf/{campaign_id}", summary="Export Ledger (PDF)")
async def export_pdf(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Generates a real-time Base64 PDF document of the immutable ledger.
    """
    ledger_service = LedgerService(db)
    ledger = ledger_service.get_campaign_ledger(campaign_id=campaign_id, owner_id=current_user.get("sub"))
    
    title = ledger.summary.title if ledger.summary else "KapuLetu Campaign"
    target = ledger.summary.target_amount if ledger.summary else 0.0
    total = ledger.summary.total_raised if ledger.summary else 0.0
    
    b64_pdf = generate_pdf_report(title, total, target, ledger.entries)
    return {"filename": f"ledger_{campaign_id}.pdf", "file_data": b64_pdf}
