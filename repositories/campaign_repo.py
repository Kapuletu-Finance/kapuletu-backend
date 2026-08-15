import uuid
import random
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.campaign import Campaign
from models.transaction import Transaction
from common.utils import generate_slug

def create_campaign(db: Session, group_id: str, title: str, description: str = None, target_amount: float = 0.0, payment_instructions: str = None):
    """Creates a new campaign for a specific group with full reporting metadata."""
    base_slug = generate_slug(title)
    slug = base_slug
    # Ensure slug uniqueness for this group
    while db.query(Campaign).filter(Campaign.group_id == group_id, Campaign.slug == slug).first():
        slug = f"{base_slug}-{random.randint(1000, 9999)}"

    default_settings = {
        "report_title": "Campaign Update",
        "report_footer": "Thank you for your support.",
        "blank_slots": 3,
        "paid_indicator": "✔",
        "require_pin": True,
        "access_pin": str(random.randint(1000, 9999)),
        "remove_watermark": False,
        "auto_send_reports": False
    }

    new_campaign = Campaign(
        campaign_id=uuid.uuid4(),
        group_id=group_id,
        title=title,
        description=description,
        target_amount=target_amount,
        payment_instructions=payment_instructions,
        slug=slug,
        settings_override=default_settings
    )
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    return new_campaign

def get_campaign(db: Session, identifier: str):
    """Fetches a single campaign by its ID or slug."""
    try:
        valid_uuid = uuid.UUID(identifier)
        return db.query(Campaign).filter(Campaign.campaign_id == valid_uuid).first()
    except ValueError:
        return db.query(Campaign).filter(Campaign.slug == identifier).first()

def get_group_campaigns(db: Session, group_id: str, skip: int = 0, limit: int = 100, search: str = None, status: str = None):
    """Returns all campaigns belonging to a specific group with pagination, search, and dynamic stats."""
    query = db.query(Campaign).filter(Campaign.group_id == group_id)
    
    if search:
        query = query.filter(Campaign.title.ilike(f"%{search}%"))
        
    if status == "archived":
        query = query.filter(Campaign.is_active == False)
    elif status == "all":
        pass
    else:
        query = query.filter(Campaign.is_active == True)
        
    total_items = query.count()
    total_pages = (total_items + limit - 1) // limit if limit > 0 else 0
    page = (skip // limit) + 1 if limit > 0 else 1
    
    campaigns = query.offset(skip).limit(limit).all()
    
    if not campaigns:
        return {"items": [], "total_items": 0, "total_pages": 0, "page": page, "limit": limit}
        
    camp_ids = [c.campaign_id for c in campaigns]
    
    # 1. Total Raised
    funds_raised = dict(db.query(Transaction.campaign_id, func.sum(Transaction.amount)).filter(Transaction.campaign_id.in_(camp_ids), Transaction.status == "approved").group_by(Transaction.campaign_id).all())
    
    # 2. Contributor Count (total transactions)
    contrib_counts = dict(db.query(Transaction.campaign_id, func.count(Transaction.transaction_id)).filter(Transaction.campaign_id.in_(camp_ids), Transaction.status == "approved").group_by(Transaction.campaign_id).all())
    
    # 3. Payment Method Breakdown
    pm_sums = db.query(Transaction.campaign_id, Transaction.payment_method, func.sum(Transaction.amount)).filter(
        Transaction.campaign_id.in_(camp_ids), 
        Transaction.status == "approved"
    ).group_by(Transaction.campaign_id, Transaction.payment_method).all()
    
    pm_map = {}
    for cid, pm, amount in pm_sums:
        pm_lower = (pm or "cash").lower()
        if cid not in pm_map:
            pm_map[cid] = {"mpesa": 0.0, "cash": 0.0, "bank": 0.0, "pledge": 0.0}
            
        if "mpesa" in pm_lower:
            pm_map[cid]["mpesa"] += float(amount)
        elif "cash" in pm_lower:
            pm_map[cid]["cash"] += float(amount)
        elif "bank" in pm_lower:
            pm_map[cid]["bank"] += float(amount)
        elif "pledge" in pm_lower:
            pm_map[cid]["pledge"] += float(amount)
    
    for c in campaigns:
        raised = float(funds_raised.get(c.campaign_id, 0.0) or 0.0)
        c.total_raised = raised
        c.contributor_count = contrib_counts.get(c.campaign_id, 0)
        if c.target_amount and c.target_amount > 0:
            c.progress_percentage = round((raised / float(c.target_amount)) * 100, 2)
        else:
            c.progress_percentage = 0.0
            
        cmap = pm_map.get(c.campaign_id, {"mpesa": 0.0, "cash": 0.0, "bank": 0.0, "pledge": 0.0})
        c.total_mpesa = cmap["mpesa"]
        c.total_cash = cmap["cash"]
        c.total_bank = cmap["bank"]
        c.total_pledges = cmap["pledge"]
        
        c.mpesa_percentage = round((c.total_mpesa / raised) * 100, 2) if raised > 0 else 0.0
        c.cash_percentage = round((c.total_cash / raised) * 100, 2) if raised > 0 else 0.0
        c.bank_percentage = round((c.total_bank / raised) * 100, 2) if raised > 0 else 0.0
        c.pledges_percentage = round((c.total_pledges / raised) * 100, 2) if raised > 0 else 0.0
            
    return {
        "items": campaigns,
        "total_items": total_items,
        "total_pages": total_pages,
        "page": page,
        "limit": limit
    }

def update_campaign(db: Session, campaign_id: str, updates: dict):
    """Updates campaign details."""
    db.query(Campaign).filter(Campaign.campaign_id == campaign_id).update(updates)
    db.commit()
    return get_campaign(db, campaign_id)

def archive_campaign(db: Session, campaign_id: str):
    """Soft deletes a campaign by archiving it."""
    db.query(Campaign).filter(Campaign.campaign_id == campaign_id).update({
        "status": "archived",
        "is_active": False
    })
    db.commit()
    return get_campaign(db, campaign_id)
