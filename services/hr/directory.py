"""Employee lookups shared by the HR services (schedule, attendance, meetings)."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Query, Session

from common.enums import UserRole
from common.utils import distance_meters, parse_uuid
from models.hr import WorkLocation
from models.users import User

# Permission that grants access to HR administration (schedules, register, meetings).
HR_ADMIN_PERMISSION = "manage_employees"


def active_employees_query(db: Session) -> Query:
    """Internal staff (every role except treasurer) who are active and not deleted."""
    return staff_query(db).filter(User.is_active.is_(True), User.deleted_at.is_(None))


def staff_query(db: Session) -> Query:
    """All internal staff (every role except treasurer), including suspended accounts."""
    return db.query(User).filter(User.role != UserRole.TREASURER.value)


def get_employee_or_404(db: Session, user_id, include_inactive: bool = False) -> User:
    """Looks up an employee; suspended staff are only found when include_inactive (history views)."""
    try:
        uid = parse_uuid(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Employee not found")
    query = staff_query(db) if include_inactive else active_employees_query(db)
    employee = query.filter(User.user_id == uid).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


def full_name(user: User) -> str:
    return f"{user.first_name} {user.last_name}".strip()


def get_default_location(db: Session) -> Optional[WorkLocation]:
    return db.query(WorkLocation).filter(WorkLocation.is_default.is_(True)).first()


def assert_within_location(location: Optional[WorkLocation], latitude, longitude) -> float:
    """
    Validates GPS coordinates against a work location's geofence (the office or another venue).
    Returns the distance in meters; raises HTTPException when the check fails.
    """
    if location is None:
        raise HTTPException(
            status_code=503,
            detail="No work location has been configured by the administrator yet. Please contact your admin.",
        )
    if not latitude or not longitude:
        raise HTTPException(status_code=400, detail="GPS coordinates are required for physical attendance.")

    try:
        distance_m = distance_meters(float(latitude), float(longitude), location.latitude, location.longitude)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid GPS coordinates.")

    if distance_m > location.radius_meters:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Location rejected. You are {int(distance_m)}m from {location.name}. "
                f"Check-in is allowed within {location.radius_meters}m."
            ),
        )
    return distance_m
