from sqlalchemy.orm import Session
from models.campaign import Campaign
import uuid

def create_campaign(db: Session, group_id: str, title: str, target_amount: float = 0.0):
    """Creates a new campaign for a specific group."""
    new_campaign = Campaign(
        campaign_id=uuid.uuid4(),
        group_id=group_id,
        title=title,
        target_amount=target_amount
    )
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    return new_campaign

def get_campaign(db: Session, campaign_id: str):
    """Fetches a single campaign by its ID."""
    return db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()

def get_group_campaigns(db: Session, group_id: str):
    """Returns all campaigns belonging to a specific group."""
    return db.query(Campaign).filter(Campaign.group_id == group_id).all()

def update_campaign(db: Session, campaign_id: str, updates: dict):
    """Updates campaign details."""
    db.query(Campaign).filter(Campaign.campaign_id == campaign_id).update(updates)
    db.commit()
    return get_campaign(db, campaign_id)
