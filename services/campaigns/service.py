from sqlalchemy.orm import Session
from repositories import campaign_repo

def create_campaign(db: Session, group_id: str, data: dict):
    """
    Business logic for initializing a new fundraising goal.
    Captures metadata for WhatsApp reports.
    """
    return campaign_repo.create_campaign(
        db, 
        group_id=group_id, 
        title=data.get("title"), 
        description=data.get("description"),
        target_amount=data.get("target_amount", 0.0),
        payment_instructions=data.get("payment_instructions")
    )

def list_campaigns(db: Session, group_id: str):
    """
    Retrieves all campaigns associated with a specific organization.
    """
    return campaign_repo.get_group_campaigns(db, group_id)
