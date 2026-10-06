import datetime
import uuid

from sqlalchemy import UUID, Column, DateTime, String, ForeignKey, Text, Enum, Date
from sqlalchemy.orm import relationship

from .base import Base

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
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))
    
    # Relationships
    employee = relationship("User", foreign_keys=[user_id])


class Meeting(Base):
    """
    Scheduled meetings for employees (physical or online).
    """
    __tablename__ = "meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    meeting_type = Column(String, nullable=False) # online, physical
    location_or_url = Column(String, nullable=True)
    
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    organizer_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    organizer = relationship("User", foreign_keys=[organizer_id])
    attendees = relationship("MeetingAttendee", back_populates="meeting", cascade="all, delete-orphan")


class MeetingAttendee(Base):
    """
    Tracks which employees are invited to which meetings, and if they attended.
    """
    __tablename__ = "meeting_attendees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    
    status = Column(String, default="invited") # invited, accepted, declined
    attendance = Column(String, nullable=True) # attended, missed, excused
    
    meeting = relationship("Meeting", back_populates="attendees")
    user = relationship("User", foreign_keys=[user_id])
