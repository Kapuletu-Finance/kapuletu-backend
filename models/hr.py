import datetime
import uuid

from sqlalchemy import (
    JSON, UUID, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, Time,
    UniqueConstraint, text,
)
from sqlalchemy.orm import relationship

from .base import Base


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


# Vocabulary shared by the work schedule, daily attendance and meetings.
WORK_MODES = ("physical", "online")
DAY_MODES = WORK_MODES + ("off",)
# Outcomes an admin can set when correcting a day
ADJUSTMENT_STATUSES = ("present", "late", "absent", "excused")


class EmployeeReport(Base):
    """
    Daily attendance and work reports for employees.
    """
    __tablename__ = "employee_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True)
    report_date = Column(Date, nullable=False, default=datetime.date.today)

    clock_in_time = Column(DateTime(timezone=True), nullable=True)
    clock_out_time = Column(DateTime(timezone=True), nullable=True)

    work_summary = Column(Text, nullable=True)
    status = Column(String, default="pending_review", index=True) # pending_review, confirmed, rejected
    admin_notes = Column(Text, nullable=True)

    # Location & Mode tracking
    work_mode = Column(String, nullable=False, default="physical") # physical, online
    latitude = Column(String, nullable=True) # Store as string for precision
    longitude = Column(String, nullable=True)
    # True when the clock-in happened after the scheduled start time (but before the cut-off)
    is_late = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    employee = relationship("User", foreign_keys=[user_id])


class WorkScheduleDay(Base):
    """
    Weekly attendance pattern. Rows with user_id NULL form the company-wide pattern;
    rows with a user_id override that pattern for one employee on one weekday.
    """
    __tablename__ = "work_schedule_days"
    __table_args__ = (
        UniqueConstraint("user_id", "weekday", name="uq_work_schedule_user_weekday"),
        # Postgres treats NULLs as distinct, so the company rows need their own unique index.
        Index("uq_work_schedule_company_weekday", "weekday", unique=True,
              postgresql_where=text("user_id IS NULL"), sqlite_where=text("user_id IS NULL")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True, index=True)
    weekday = Column(Integer, nullable=False)  # 0 = Monday ... 6 = Sunday
    mode = Column(String, nullable=False)  # physical, online, off
    start_time = Column(Time, nullable=False)  # Nairobi local time; clock-ins after this are late
    cutoff_time = Column(Time, nullable=False)  # Nairobi local time; clock-ins are refused after this
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class WorkScheduleOverride(Base):
    """
    Date-specific schedule exceptions (holidays, special office days).
    user_id NULL applies to everyone; otherwise it applies to one employee and wins over the company override.
    """
    __tablename__ = "work_schedule_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_work_schedule_override_user_date"),
        Index("uq_work_schedule_override_company_date", "date", unique=True,
              postgresql_where=text("user_id IS NULL"), sqlite_where=text("user_id IS NULL")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True, index=True)
    date = Column(Date, nullable=False, index=True)
    mode = Column(String, nullable=False)  # physical, online, off
    reason = Column(String, nullable=True)
    # Venue for a physical override (e.g. an offsite day); NULL means the default work location
    location_id = Column(UUID(as_uuid=True), ForeignKey("work_locations.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    employee = relationship("User", foreign_keys=[user_id])
    location = relationship("WorkLocation")


class Meeting(Base):
    """
    Scheduled meetings for employees (physical or online).
    """
    __tablename__ = "meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    meeting_type = Column(String, nullable=False) # online, physical
    location_or_url = Column(String, nullable=True)  # Online: join link. Physical: room / directions.
    # Venue for physical meetings (check-ins are geofenced against it); NULL means the default work location
    location_id = Column(UUID(as_uuid=True), ForeignKey("work_locations.id", ondelete="SET NULL"), nullable=True)

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    status = Column(String, nullable=False, default="scheduled", server_default="scheduled")  # scheduled, cancelled
    # How the attendee list was chosen: all employees, by role, or a custom selection
    audience = Column(String, nullable=False, default="custom", server_default="custom")  # all, roles, custom
    audience_roles = Column(JSON, nullable=True)
    # Set by the meeting worker once unmarked attendees have been recorded as missed
    attendance_finalized_at = Column(DateTime(timezone=True), nullable=True)

    organizer_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    organizer = relationship("User", foreign_keys=[organizer_id])
    location = relationship("WorkLocation")
    attendees = relationship("MeetingAttendee", back_populates="meeting", cascade="all, delete-orphan")


class MeetingAttendee(Base):
    """
    Tracks which employees are invited to which meetings, and if they attended.
    """
    __tablename__ = "meeting_attendees"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id", name="uq_meeting_attendee"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String, default="invited") # invited, accepted, declined
    responded_at = Column(DateTime(timezone=True), nullable=True)

    attendance = Column(String, nullable=True) # attended, missed, excused
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checkin_latitude = Column(String, nullable=True)
    checkin_longitude = Column(String, nullable=True)
    marked_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)  # Admin who recorded attendance; NULL for self check-in

    reminder_24h_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_1h_sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    meeting = relationship("Meeting", back_populates="attendees")
    user = relationship("User", foreign_keys=[user_id])


class WorkLocation(Base):
    """
    A physical venue employees can be required to attend (the office, an offsite venue...).
    Exactly one active location is the default: it is used for physical days and meetings
    that don't name another venue. Check-ins must be within `radius_meters` of it.
    """
    __tablename__ = "work_locations"
    __table_args__ = (
        Index("uq_work_locations_default", "is_default", unique=True,
              postgresql_where=text("is_default"), sqlite_where=text("is_default")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius_meters = Column(Integer, nullable=False, default=200)
    is_default = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Inactive locations are hidden from pickers but still apply to records that reference them
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class AttendanceAdjustment(Base):
    """
    An admin correction to one employee's attendance on one date (e.g. excused sick day, failed GPS).
    It takes precedence over the computed status; the employee's own EmployeeReport is left untouched.
    """
    __tablename__ = "attendance_adjustments"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_attendance_adjustment_user_date"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    status = Column(String, nullable=False)  # present, late, absent, excused
    reason = Column(Text, nullable=False)
    clock_in_time = Column(DateTime(timezone=True), nullable=True)
    clock_out_time = Column(DateTime(timezone=True), nullable=True)
    adjusted_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    employee = relationship("User", foreign_keys=[user_id])
    adjuster = relationship("User", foreign_keys=[adjusted_by])
