import uuid
import random
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Group, Campaign
from models.transaction import Transaction
from common.utils import generate_slug

def create_group(db: Session, owner_id: str, name: str, description: str = None, currency: str = "KES"):
    """Creates a new community group."""
    owner_id_uuid = owner_id if isinstance(owner_id, uuid.UUID) else uuid.UUID(owner_id)
    base_slug = generate_slug(name)
    slug = base_slug
    # Ensure slug uniqueness for this owner
    while db.query(Group).filter(Group.owner_id == owner_id_uuid, Group.slug == slug).first():
        slug = f"{base_slug}-{random.randint(1000, 9999)}"
        
    new_group = Group(
        group_id=uuid.uuid4(),
        owner_id=owner_id,
        group_name=name,
        description=description,
        currency=currency,
        slug=slug
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

def get_group(db: Session, group_id: str):
    """Retrieves a single group by ID."""
    return db.query(Group).filter(Group.group_id == group_id).first()

def get_owner_groups(db: Session, owner_id: str, skip: int = 0, limit: int = 100, search: str = None, status: str = None):
    """Lists all groups belonging to a treasurer with pagination, search, and dynamic stats."""
    owner_id_uuid = owner_id if isinstance(owner_id, uuid.UUID) else uuid.UUID(owner_id)
    query = db.query(Group).filter(Group.owner_id == owner_id_uuid)
    
    if search:
        query = query.filter(Group.group_name.ilike(f"%{search}%"))
        
    if status == "archived":
        query = query.filter(Group.is_active == False)
    elif status == "all":
        pass
    else:
        query = query.filter(Group.is_active == True)

    total_items = query.count()
    total_pages = (total_items + limit - 1) // limit if limit > 0 else 0
    page = (skip // limit) + 1 if limit > 0 else 1
    
    groups = query.offset(skip).limit(limit).all()
    
    if not groups:
        return {"items": [], "total_items": 0, "total_pages": 0, "page": page, "limit": limit}

    group_ids = [g.group_id for g in groups]
    
    # 1. Total Campaigns Count
    total_camps = dict(db.query(Campaign.group_id, func.count(Campaign.campaign_id)).filter(Campaign.group_id.in_(group_ids)).group_by(Campaign.group_id).all())
    
    # 2. Active Campaigns Count
    active_camps = dict(db.query(Campaign.group_id, func.count(Campaign.campaign_id)).filter(Campaign.group_id.in_(group_ids), Campaign.is_active == True).group_by(Campaign.group_id).all())
    
    # 3. Total Funds Raised (Approved Transactions)
    funds_raised = dict(db.query(Transaction.group_id, func.sum(Transaction.amount)).filter(Transaction.group_id.in_(group_ids), Transaction.status == "approved").group_by(Transaction.group_id).all())
    
    for g in groups:
        g.total_campaigns_count = total_camps.get(g.group_id, 0)
        g.active_campaigns_count = active_camps.get(g.group_id, 0)
        g.total_funds_raised = float(funds_raised.get(g.group_id, 0.0) or 0.0)
        
    return {
        "items": groups,
        "total_items": total_items,
        "total_pages": total_pages,
        "page": page,
        "limit": limit
    }

def update_group(db: Session, group_id: str, updates: dict):
    """Updates group properties."""
    if "name" in updates:
        updates["group_name"] = updates.pop("name")
    db.query(Group).filter(Group.group_id == group_id).update(updates)
    db.commit()
    return get_group(db, group_id)

def archive_group(db: Session, group_id: str):
    """Soft deletes a group by archiving it."""
    db.query(Group).filter(Group.group_id == group_id).update({
        "status": "archived",
        "is_active": False
    })
    db.commit()
    return get_group(db, group_id)
