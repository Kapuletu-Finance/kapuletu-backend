"""Saved work locations (the office and other venues) used to geofence physical attendance."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from common.utils import parse_uuid
from models.hr import WorkLocation
from services.hr.schemas import WorkLocationIn


def list_locations(db: Session) -> list[WorkLocation]:
    """Default first, then active venues alphabetically, then archived ones."""
    return db.query(WorkLocation).order_by(
        WorkLocation.is_default.desc(), WorkLocation.is_active.desc(), WorkLocation.name
    ).all()


def get_location_or_404(db: Session, location_id) -> WorkLocation:
    try:
        lid = parse_uuid(location_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Work location not found")
    location = db.query(WorkLocation).filter(WorkLocation.id == lid).first()
    if not location:
        raise HTTPException(status_code=404, detail="Work location not found")
    return location


def require_active_location(db: Session, location_id) -> Optional[WorkLocation]:
    """Validates a venue chosen for a meeting or override; None means 'use the default'."""
    if location_id is None:
        return None
    location = get_location_or_404(db, location_id)
    if not location.is_active:
        raise HTTPException(status_code=400, detail=f"{location.name} is archived. Choose an active location.")
    return location


def create_location(db: Session, payload: WorkLocationIn) -> WorkLocation:
    has_default = db.query(WorkLocation.id).filter(WorkLocation.is_default.is_(True)).first() is not None
    # The first location becomes the default so physical attendance always has somewhere to check against.
    location = WorkLocation(**payload.model_dump(), is_default=not has_default, is_active=True)
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


def update_location(db: Session, location_id, payload: WorkLocationIn) -> WorkLocation:
    location = get_location_or_404(db, location_id)
    for field, value in payload.model_dump().items():
        setattr(location, field, value)
    db.commit()
    db.refresh(location)
    return location


def set_default_location(db: Session, location_id) -> WorkLocation:
    location = get_location_or_404(db, location_id)
    if not location.is_active:
        raise HTTPException(status_code=400, detail="Restore this location before making it the default.")
    db.query(WorkLocation).filter(WorkLocation.is_default.is_(True), WorkLocation.id != location.id).update(
        {"is_default": False}, synchronize_session=False
    )
    db.flush()  # release the single-default constraint before setting the new one
    location.is_default = True
    db.commit()
    db.refresh(location)
    return location


def set_location_active(db: Session, location_id, active: bool) -> WorkLocation:
    location = get_location_or_404(db, location_id)
    if not active and location.is_default:
        raise HTTPException(status_code=400, detail="The default location can't be archived. Make another location the default first.")
    location.is_active = active
    db.commit()
    db.refresh(location)
    return location
