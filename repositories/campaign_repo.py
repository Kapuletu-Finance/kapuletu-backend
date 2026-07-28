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

    new_campaign = Campaign(
        campaign_id=uuid.uuid4(),
        group_id=group_id,
        title=title,
        description=description,
        target_amount=target_amount,
        payment_instructions=payment_instructions,
        slug=slug
    )
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    return new_campaign

def get_campaign(db: Session, campaign_id: str):
    """Fetches a single campaign by its ID."""
    return db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()

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
    
    # 2. Contributor Count (distinct senders)
    contrib_counts = dict(db.query(Transaction.campaign_id, func.count(func.distinct(Transaction.sender_phone))).filter(Transaction.campaign_id.in_(camp_ids), Transaction.status == "approved").group_by(Transaction.campaign_id).all())
    
    for c in campaigns:
        raised = float(funds_raised.get(c.campaign_id, 0.0) or 0.0)
        c.total_raised = raised
        c.contributor_count = contrib_counts.get(c.campaign_id, 0)
        if c.target_amount and c.target_amount > 0:
            c.progress_percentage = round((raised / float(c.target_amount)) * 100, 2)
        else:
            c.progress_percentage = 0.0
            
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
