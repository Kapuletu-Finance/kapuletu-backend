"""
Work schedule: which days are physical, online or off, company-wide and per employee.

Resolution order for (employee, date) — first match wins:
  1. employee date override
  2. company date override
  3. employee weekly pattern
  4. company weekly pattern (falls back to DEFAULT_WEEK when not configured)
Overrides carry a mode (and, for physical days, optionally a venue); start/cut-off times always come
from the weekly pattern. Physical days resolve to the override's venue, else the default work location.
"""
import datetime
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from common.utils import parse_uuid
from models.hr import WorkLocation, WorkScheduleDay, WorkScheduleOverride
from services.hr.directory import full_name, get_default_location, get_employee_or_404
from services.hr.location_service import require_active_location
from services.hr.schemas import (
    ResolvedDay, ScheduleDayIn, ScheduleDayOut, ScheduleOverrideCreate, ScheduleOverrideOut, WorkLocationOut,
)

DEFAULT_START = datetime.time(8, 0)
DEFAULT_CUTOFF = datetime.time(11, 0)
# Used for any weekday the admin has not configured yet: Mon-Fri physical, weekend off.
DEFAULT_WEEK = {
    weekday: ScheduleDayOut(
        weekday=weekday,
        mode="physical" if weekday < 5 else "off",
        start_time=DEFAULT_START,
        cutoff_time=DEFAULT_CUTOFF,
    )
    for weekday in range(7)
}

MAX_RANGE_DAYS = 92  # day-level views (register, overrides, personal history)
MAX_SUMMARY_DAYS = 366  # aggregated summaries (up to a leap year)


def validate_range(start: datetime.date, end: datetime.date, max_days: int = MAX_RANGE_DAYS) -> None:
    if end < start:
        raise HTTPException(status_code=400, detail="'end' must not be before 'start'.")
    if (end - start).days >= max_days:
        raise HTTPException(status_code=400, detail=f"Date range may not exceed {max_days} days.")


def date_range(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


class ScheduleResolver:
    """Loads schedule data for a set of employees and date range once, then resolves days in memory."""

    def __init__(self, db: Session, user_ids: Iterable, start: datetime.date, end: datetime.date):
        uids = [parse_uuid(u) for u in user_ids]

        weekly_rows = db.query(WorkScheduleDay).filter(
            or_(WorkScheduleDay.user_id.is_(None), WorkScheduleDay.user_id.in_(uids))
        ).all()
        self._company_weekly = {r.weekday: r for r in weekly_rows if r.user_id is None}
        self._employee_weekly = {(r.user_id, r.weekday): r for r in weekly_rows if r.user_id is not None}

        override_rows = db.query(WorkScheduleOverride).options(joinedload(WorkScheduleOverride.location)).filter(
            WorkScheduleOverride.date >= start,
            WorkScheduleOverride.date <= end,
            or_(WorkScheduleOverride.user_id.is_(None), WorkScheduleOverride.user_id.in_(uids)),
        ).all()
        self._company_dates = {o.date: o for o in override_rows if o.user_id is None}
        self._employee_dates = {(o.user_id, o.date): o for o in override_rows if o.user_id is not None}

        self._default_location = get_default_location(db)
        self._location_out: dict = {}  # WorkLocation.id -> WorkLocationOut, converted once

    def _location(self, location: Optional[WorkLocation]) -> Optional[WorkLocationOut]:
        if location is None:
            return None
        if location.id not in self._location_out:
            self._location_out[location.id] = WorkLocationOut.model_validate(location)
        return self._location_out[location.id]

    def resolve(self, user_id, day: datetime.date) -> ResolvedDay:
        uid = parse_uuid(user_id)
        weekday = day.weekday()

        employee_weekly = self._employee_weekly.get((uid, weekday))
        weekly = employee_weekly or self._company_weekly.get(weekday) or DEFAULT_WEEK[weekday]
        weekly_source = "employee_weekly" if employee_weekly else "company_weekly"

        override = self._employee_dates.get((uid, day))
        source = "employee_override"
        if not override:
            override = self._company_dates.get(day)
            source = "company_override"

        mode = override.mode if override else weekly.mode
        is_workday = mode != "off"
        venue = (override.location if override else None) or self._default_location
        return ResolvedDay(
            date=day,
            mode=mode,
            start_time=weekly.start_time if is_workday else None,
            cutoff_time=weekly.cutoff_time if is_workday else None,
            source=source if override else weekly_source,
            reason=override.reason if override else None,
            location=self._location(venue) if mode == "physical" else None,
        )


# --- Weekly patterns ---

def get_company_schedule(db: Session) -> list[ScheduleDayOut]:
    rows = {r.weekday: r for r in db.query(WorkScheduleDay).filter(WorkScheduleDay.user_id.is_(None))}
    return [ScheduleDayOut.model_validate(rows[d]) if d in rows else DEFAULT_WEEK[d] for d in range(7)]


def _replace_weekly_rows(db: Session, user_id, days: list[ScheduleDayIn]) -> None:
    owner_filter = WorkScheduleDay.user_id.is_(None) if user_id is None else WorkScheduleDay.user_id == user_id
    db.query(WorkScheduleDay).filter(owner_filter).delete(synchronize_session=False)
    db.add_all(
        WorkScheduleDay(
            user_id=user_id,
            weekday=d.weekday,
            mode=d.mode,
            start_time=d.start_time,
            cutoff_time=d.cutoff_time,
        )
        for d in days
    )
    db.commit()


def set_company_schedule(db: Session, days: list[ScheduleDayIn]) -> list[ScheduleDayOut]:
    _replace_weekly_rows(db, None, days)
    return get_company_schedule(db)


def get_employee_schedule(db: Session, user_id) -> list[ScheduleDayOut]:
    employee = get_employee_or_404(db, user_id, include_inactive=True)
    rows = db.query(WorkScheduleDay).filter(WorkScheduleDay.user_id == employee.user_id).order_by(WorkScheduleDay.weekday)
    return [ScheduleDayOut.model_validate(r) for r in rows]


def set_employee_schedule(db: Session, user_id, days: list[ScheduleDayIn]) -> list[ScheduleDayOut]:
    employee = get_employee_or_404(db, user_id)
    _replace_weekly_rows(db, employee.user_id, days)
    return get_employee_schedule(db, employee.user_id)


# --- Date overrides ---

def _override_out(override: WorkScheduleOverride) -> ScheduleOverrideOut:
    out = ScheduleOverrideOut.model_validate(override)
    if override.employee:
        out.employee_name = full_name(override.employee)
    if override.location:
        out.location_name = override.location.name
    return out


def list_overrides(db: Session, start: datetime.date, end: datetime.date, user_id: Optional[str] = None) -> list[ScheduleOverrideOut]:
    validate_range(start, end)
    query = db.query(WorkScheduleOverride).filter(
        WorkScheduleOverride.date >= start, WorkScheduleOverride.date <= end
    )
    if user_id:
        query = query.filter(WorkScheduleOverride.user_id == parse_uuid(user_id))
    return [_override_out(o) for o in query.order_by(WorkScheduleOverride.date, WorkScheduleOverride.user_id)]


def upsert_override(db: Session, payload: ScheduleOverrideCreate, actor_id) -> ScheduleOverrideOut:
    """Creates the override, or replaces the existing one for the same employee (or company) and date."""
    user_id = get_employee_or_404(db, payload.user_id).user_id if payload.user_id else None
    owner_filter = WorkScheduleOverride.user_id.is_(None) if user_id is None else WorkScheduleOverride.user_id == user_id

    override = db.query(WorkScheduleOverride).filter(owner_filter, WorkScheduleOverride.date == payload.date).first()
    if not override:
        override = WorkScheduleOverride(user_id=user_id, date=payload.date, created_by=parse_uuid(actor_id))
        db.add(override)
    override.mode = payload.mode
    override.reason = payload.reason
    # A venue only applies to physical days; None means the default location.
    venue = require_active_location(db, payload.location_id) if payload.mode == "physical" else None
    override.location_id = venue.id if venue else None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An override for this date already exists. Please retry.")
    db.refresh(override)
    return _override_out(override)


def delete_override(db: Session, override_id: str) -> None:
    try:
        oid = parse_uuid(override_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Override not found")
    deleted = db.query(WorkScheduleOverride).filter(WorkScheduleOverride.id == oid).delete(synchronize_session=False)
    if not deleted:
        raise HTTPException(status_code=404, detail="Override not found")
    db.commit()
