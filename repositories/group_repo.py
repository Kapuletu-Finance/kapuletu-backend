import uuid
from sqlalchemy.orm import Session
from models import Group

def create_group(db: Session, owner_id: str, name: str, description: str = None, currency: str = "KES"):
    """Creates a new community group."""
    new_group = Group(
        group_id=uuid.uuid4(),
        owner_id=owner_id,
        group_name=name,
        description=description,
        currency=currency
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

def get_group(db: Session, group_id: str):
    """Retrieves a single group by ID."""
    return db.query(Group).filter(Group.group_id == group_id).first()

def get_owner_groups(db: Session, owner_id: str, skip: int = 0, limit: int = 100):
    """Lists all active groups belonging to a treasurer with pagination."""
    return db.query(Group).filter(Group.owner_id == owner_id, Group.is_active == True).offset(skip).limit(limit).all()

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
