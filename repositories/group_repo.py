import uuid
from sqlalchemy.orm import Session
from models import Group

def create_group(db: Session, owner_id: str, name: str, description: str = None):
    """Creates a new community group."""
    new_group = Group(
        group_id=uuid.uuid4(),
        owner_id=owner_id,
        group_name=name,
        description=description
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

def get_group(db: Session, group_id: str):
    """Retrieves a single group by ID."""
    return db.query(Group).filter(Group.group_id == group_id).first()

def get_owner_groups(db: Session, owner_id: str):
    """Lists all groups belonging to a treasurer."""
    return db.query(Group).filter(Group.owner_id == owner_id).all()

def update_group(db: Session, group_id: str, updates: dict):
    """Updates group properties."""
    if "name" in updates:
        updates["group_name"] = updates.pop("name")
    db.query(Group).filter(Group.group_id == group_id).update(updates)
    db.commit()
    return get_group(db, group_id)
