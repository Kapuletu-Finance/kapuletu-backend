import uuid
from sqlalchemy.orm import Session
from models.campaign import Campaign

def create_campaign(db: Session, group_id: str, title: str, description: str = None, target_amount: float = 0.0, payment_instructions: str = None):
    """Creates a new campaign for a specific group with full reporting metadata."""
    new_campaign = Campaign(
        campaign_id=uuid.uuid4(),
        group_id=group_id,
        title=title,
        description=description,
        target_amount=target_amount,
        payment_instructions=payment_instructions
    )
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    return new_campaign

def get_campaign(db: Session, campaign_id: str):
    """Fetches a single campaign by its ID."""
    return db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()

def get_group_campaigns(db: Session, group_id: str, skip: int = 0, limit: int = 100):
    """Returns all active campaigns belonging to a specific group with pagination."""
    return db.query(Campaign).filter(Campaign.group_id == group_id, Campaign.is_active == True).offset(skip).limit(limit).all()

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
