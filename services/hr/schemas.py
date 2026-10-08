from datetime import date, datetime, time, timezone
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WorkMode = Literal["physical", "online"]
DayMode = Literal["physical", "online", "off"]
DaySource = Literal["employee_override", "company_override", "employee_weekly", "company_weekly"]
AttendanceDayStatus = Literal["present", "late", "absent", "excused", "off", "upcoming"]
AdjustmentStatus = Literal["present", "late", "absent", "excused"]
MeetingAttendanceMark = Literal["attended", "missed", "excused"]
RsvpResponse = Literal["accepted", "declined"]
MeetingAudience = Literal["all", "roles", "custom"]
SummaryPeriod = Literal["week", "month", "quarter", "year", "custom"]
TrendBucket = Literal["day", "week", "month"]


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Treat naive datetimes from clients as UTC so comparisons with stored values are safe."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# --- Daily reports (clock-in / clock-out) ---

class EmployeeClockInCreate(BaseModel):
    # The work mode comes from the schedule; coordinates are required on physical days.
    latitude: Optional[str] = None
    longitude: Optional[str] = None


class EmployeeReportCreate(BaseModel):
    work_summary: str = Field(..., min_length=1)


class EmployeeReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    report_date: date
    clock_in_time: Optional[datetime]
    clock_out_time: Optional[datetime]
    work_summary: Optional[str]
    status: str
    admin_notes: Optional[str]
    work_mode: Optional[str]
    latitude: Optional[str]
    longitude: Optional[str]
    is_late: bool = False
    created_at: datetime
    updated_at: datetime


# --- Work locations ---

class WorkLocationIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    address: Optional[str] = Field(None, max_length=255)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_meters: int = Field(200, ge=25, le=5000, description="Allowed check-in distance")


class WorkLocationOut(WorkLocationIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_default: bool
    is_active: bool


# --- Work schedule ---

class ScheduleDayIn(BaseModel):
    weekday: int = Field(..., ge=0, le=6, description="0 = Monday ... 6 = Sunday")
    mode: DayMode
    start_time: time
    cutoff_time: time

    @model_validator(mode="after")
    def _cutoff_after_start(self):
        if self.cutoff_time < self.start_time:
            raise ValueError("cutoff_time must not be earlier than start_time")
        return self


class ScheduleDayOut(ScheduleDayIn):
    model_config = ConfigDict(from_attributes=True)


class CompanyScheduleUpdate(BaseModel):
    days: list[ScheduleDayIn]

    @field_validator("days")
    @classmethod
    def _one_row_per_weekday(cls, days: list[ScheduleDayIn]):
        if sorted(d.weekday for d in days) != list(range(7)):
            raise ValueError("Provide exactly one entry for each weekday (0-6)")
        return days


class EmployeeScheduleUpdate(BaseModel):
    # Only the weekdays that differ from the company pattern; omitted weekdays inherit it.
    days: list[ScheduleDayIn]

    @field_validator("days")
    @classmethod
    def _unique_weekdays(cls, days: list[ScheduleDayIn]):
        weekdays = [d.weekday for d in days]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("Each weekday may appear only once")
        return days


class EmployeeScheduleOut(BaseModel):
    user_id: UUID
    days: list[ScheduleDayOut]


class ScheduleOverrideCreate(BaseModel):
    date: date
    mode: DayMode
    reason: Optional[str] = Field(None, max_length=200)
    user_id: Optional[UUID] = Field(None, description="Omit to apply the override to everyone")
    location_id: Optional[UUID] = Field(None, description="Venue for a physical day; omit for the default location")


class ScheduleOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    date: date
    mode: DayMode
    reason: Optional[str]
    user_id: Optional[UUID]
    employee_name: Optional[str] = None
    location_id: Optional[UUID] = None
    location_name: Optional[str] = None
    created_at: Optional[datetime]


class ResolvedDay(BaseModel):
    date: date
    mode: DayMode
    start_time: Optional[time]
    cutoff_time: Optional[time]
    source: DaySource
    reason: Optional[str] = None
    # Where to be on a physical day (the override's venue, else the default location)
    location: Optional[WorkLocationOut] = None


class TodayStatusOut(BaseModel):
    day: ResolvedDay
    report: Optional[EmployeeReportResponse]
    can_clock_in: bool
    message: Optional[str] = None


# --- Attendance register ---

class AttendanceDayOut(BaseModel):
    date: date
    mode: DayMode
    status: AttendanceDayStatus
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    report_id: Optional[UUID] = None
    report_status: Optional[str] = None
    reason: Optional[str] = None
    # Set when an admin corrected this day; the reason explains why
    adjusted: bool = False
    adjustment_reason: Optional[str] = None


class MeetingAttendanceSummary(BaseModel):
    invited: int = 0
    attended: int = 0
    missed: int = 0
    excused: int = 0
    attendance_rate: Optional[float] = None


class AttendanceSummary(BaseModel):
    scheduled_days: int
    present: int
    late: int
    absent: int
    # Scheduled days excused by an admin; excluded from scheduled_days and the rates
    excused: int = 0
    attendance_rate: Optional[float]
    # Share of attended days that started on time
    punctuality_rate: Optional[float] = None
    physical_expected: int
    physical_attended: int
    # Total hours between clock-in and clock-out on completed days
    hours_worked: float = 0.0
    # Average clock-in time of day (EAT), "HH:MM"
    avg_clock_in: Optional[str] = None
    reports_confirmed: int = 0
    reports_pending: int = 0
    meetings: MeetingAttendanceSummary


class MyAttendanceOut(BaseModel):
    start: date
    end: date
    days: list[AttendanceDayOut]
    summary: AttendanceSummary


class EmployeeBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    first_name: str
    last_name: str
    email: str
    role: str


class AttendanceRegisterRow(BaseModel):
    employee: EmployeeBrief
    days: list[AttendanceDayOut]
    summary: AttendanceSummary


class AttendanceRegisterOut(BaseModel):
    start: date
    end: date
    dates: list[date]
    rows: list[AttendanceRegisterRow]


class AttendanceTrendPoint(BaseModel):
    label: str
    start: date
    end: date
    scheduled_days: int
    attended: int
    late: int
    absent: int
    attendance_rate: Optional[float]


class EmployeeCount(BaseModel):
    employee: EmployeeBrief
    count: int


class AttendanceHighlights(BaseModel):
    perfect_attendance: list[EmployeeBrief]
    most_absences: list[EmployeeCount]
    most_late: list[EmployeeCount]


class AttendanceReportRow(BaseModel):
    employee: EmployeeBrief
    summary: AttendanceSummary


class AttendanceReportOut(BaseModel):
    period: SummaryPeriod
    label: str
    start: date
    end: date
    bucket: TrendBucket
    employee_count: int
    meetings_held: int
    totals: AttendanceSummary
    trend: list[AttendanceTrendPoint]
    rows: list[AttendanceReportRow]
    highlights: AttendanceHighlights
    # Day-by-day log, only included for single-employee statements
    days: Optional[list[AttendanceDayOut]] = None


class AttendanceAdjustmentIn(BaseModel):
    user_id: UUID
    date: date
    status: AdjustmentStatus
    reason: str = Field(..., min_length=3, max_length=500)
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None

    @field_validator("clock_in_time", "clock_out_time", mode="after")
    @classmethod
    def _tz_aware(cls, value):
        return _as_utc(value)

    @model_validator(mode="after")
    def _validate(self):
        if self.clock_in_time and self.clock_out_time and self.clock_out_time <= self.clock_in_time:
            raise ValueError("clock_out_time must be after clock_in_time")
        if self.status in ("absent", "excused") and (self.clock_in_time or self.clock_out_time):
            raise ValueError("Clock times only apply to present or late days")
        return self


class AttendanceAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    date: date
    status: AdjustmentStatus
    reason: str
    clock_in_time: Optional[datetime]
    clock_out_time: Optional[datetime]
    adjusted_by: Optional[UUID]
    updated_at: Optional[datetime]


# --- Meetings ---

class _MeetingTimes(BaseModel):
    @field_validator("start_time", "end_time", mode="after", check_fields=False)
    @classmethod
    def _tz_aware(cls, value):
        return _as_utc(value)


class MeetingCreate(_MeetingTimes):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    meeting_type: WorkMode
    location_or_url: Optional[str] = None
    # Venue for in-person meetings; omit to use the default work location
    location_id: Optional[UUID] = None
    start_time: datetime
    end_time: datetime
    audience: MeetingAudience = "custom"
    audience_roles: list[str] = []
    attendee_ids: list[UUID] = []

    @model_validator(mode="after")
    def _validate_audience(self):
        if self.audience == "roles" and not self.audience_roles:
            raise ValueError("Select at least one role")
        if self.audience == "custom" and not self.attendee_ids:
            raise ValueError("Select at least one attendee")
        return self


class MeetingUpdate(_MeetingTimes):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    meeting_type: Optional[WorkMode] = None
    location_or_url: Optional[str] = None
    location_id: Optional[UUID] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    # When audience is provided the attendee list is re-resolved (added/removed people are notified).
    audience: Optional[MeetingAudience] = None
    audience_roles: list[str] = []
    attendee_ids: list[UUID] = []


class MeetingRsvpIn(BaseModel):
    response: RsvpResponse


class MeetingCheckInIn(BaseModel):
    latitude: Optional[str] = None
    longitude: Optional[str] = None


class MeetingAttendanceRecordIn(BaseModel):
    user_id: UUID
    attendance: MeetingAttendanceMark


class MeetingAttendanceUpdate(BaseModel):
    records: list[MeetingAttendanceRecordIn] = Field(..., min_length=1)


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: Optional[str]
    meeting_type: str
    location_or_url: Optional[str]
    location_id: Optional[UUID] = None
    # Resolved venue for in-person meetings (falls back to the default location)
    location: Optional[WorkLocationOut] = None
    start_time: datetime
    end_time: datetime
    status: str
    audience: str
    audience_roles: Optional[list[str]] = None
    organizer_id: UUID
    created_at: datetime


class MyMeetingOut(MeetingResponse):
    my_status: str
    my_attendance: Optional[str]
    checked_in_at: Optional[datetime]
    can_check_in: bool


class MeetingCounts(BaseModel):
    total: int = 0
    accepted: int = 0
    declined: int = 0
    attended: int = 0
    missed: int = 0
    excused: int = 0


class AdminMeetingOut(MeetingResponse):
    counts: MeetingCounts


class MeetingAttendeeOut(BaseModel):
    user_id: UUID
    first_name: str
    last_name: str
    email: str
    role: str
    status: str
    responded_at: Optional[datetime]
    attendance: Optional[str]
    checked_in_at: Optional[datetime]
    marked_by: Optional[UUID]


class MeetingDetailOut(AdminMeetingOut):
    attendees: list[MeetingAttendeeOut]
