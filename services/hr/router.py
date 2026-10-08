import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from common.auth_dependencies import get_admin_user, missing_permissions, require_permissions
from common.database import get_db
from common.utils import nairobi_today
from services.hr import attendance_service, location_service, meeting_service, schedule_service
from services.hr.attendance_document import render_attendance_report
from services.hr.directory import HR_ADMIN_PERMISSION, get_employee_or_404
from services.hr.schemas import (
    AdminMeetingOut, AttendanceAdjustmentIn, AttendanceAdjustmentOut, AttendanceRegisterOut, AttendanceReportOut, CompanyScheduleUpdate, EmployeeClockInCreate, EmployeeReportCreate,
    EmployeeReportResponse, EmployeeScheduleOut, EmployeeScheduleUpdate, MeetingAttendanceUpdate, MeetingCheckInIn,
    MeetingCreate, MeetingDetailOut, MeetingResponse, MeetingRsvpIn, MeetingUpdate, MyAttendanceOut, MyMeetingOut,
    ScheduleDayOut, ScheduleOverrideCreate, ScheduleOverrideOut, SummaryPeriod, TodayStatusOut, WorkLocationIn,
    WorkLocationOut,
)

router = APIRouter(prefix="/hr", tags=["HR & Meetings"])

# Any internal employee (every role except treasurer).
employee_user = get_admin_user
# HR administration: super admins, admins, the CEO, or anyone holding the manage_employees permission.
hr_admin_user = require_permissions([HR_ADMIN_PERMISSION])



def _month_bounds(start: Optional[datetime.date], end: Optional[datetime.date]) -> tuple[datetime.date, datetime.date]:
    """Defaults to the current calendar month (Nairobi time)."""
    today = nairobi_today()
    first = today.replace(day=1)
    next_month = (first + datetime.timedelta(days=32)).replace(day=1)
    return start or first, end or next_month - datetime.timedelta(days=1)


# --- DAILY ATTENDANCE ---

@router.get("/attendance/today", response_model=TodayStatusOut, summary="Today's schedule and clock-in status")
def get_today_status(current_user: dict = Depends(employee_user), db: Session = Depends(get_db)):
    return attendance_service.get_today_status(db, current_user["user_id"])


@router.post("/reports/clock-in", response_model=EmployeeReportResponse)
def clock_in(payload: EmployeeClockInCreate, current_user: dict = Depends(employee_user), db: Session = Depends(get_db)):
    """Clock in for today using the mode set by the work schedule (physical days are geofenced)."""
    return attendance_service.clock_in(db, current_user["user_id"], payload)


@router.post("/reports/clock-out", response_model=EmployeeReportResponse)
def clock_out(payload: EmployeeReportCreate, current_user: dict = Depends(employee_user), db: Session = Depends(get_db)):
    """Clock out and submit the daily summary."""
    return attendance_service.clock_out(db, current_user["user_id"], payload.work_summary)


@router.get("/attendance/me", response_model=MyAttendanceOut, summary="My attendance history and summary")
def get_my_attendance(
    start: Optional[datetime.date] = None,
    end: Optional[datetime.date] = None,
    current_user: dict = Depends(employee_user),
    db: Session = Depends(get_db),
):
    start, end = _month_bounds(start, end)
    return attendance_service.get_my_attendance(db, current_user["user_id"], start, end)


@router.get("/attendance/register", response_model=AttendanceRegisterOut, summary="Attendance register (all employees)")
def get_attendance_register(
    start: Optional[datetime.date] = None,
    end: Optional[datetime.date] = None,
    current_user: dict = Depends(hr_admin_user),
    db: Session = Depends(get_db),
):
    start, end = _month_bounds(start, end)
    return attendance_service.get_register(db, start, end)


@router.put("/attendance/adjustments", response_model=AttendanceAdjustmentOut, summary="Correct an employee's day")
def upsert_attendance_adjustment(
    payload: AttendanceAdjustmentIn, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)
):
    return attendance_service.upsert_adjustment(db, payload, current_user["user_id"])


@router.delete("/attendance/adjustments/{user_id}/{day}", status_code=204, summary="Revert a day to recorded attendance")
def delete_attendance_adjustment(
    user_id: str, day: datetime.date, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)
):
    attendance_service.delete_adjustment(db, user_id, day, current_user["user_id"])


@router.get("/attendance/summary", response_model=AttendanceReportOut, summary="Attendance report for a period")
def get_attendance_summary(
    period: SummaryPeriod = "month",
    anchor: Optional[datetime.date] = Query(None, description="Any date inside the period (default: today)"),
    start: Optional[datetime.date] = Query(None, description="Custom period start"),
    end: Optional[datetime.date] = Query(None, description="Custom period end"),
    user_id: Optional[str] = Query(None, description="Limit to one employee (attendance statement)"),
    current_user: dict = Depends(hr_admin_user),
    db: Session = Depends(get_db),
):
    return attendance_service.get_attendance_report(db, period, anchor, start, end, user_id)


@router.get("/attendance/summary/pdf", summary="Official attendance report (PDF)")
def download_attendance_summary(
    period: SummaryPeriod = "month",
    anchor: Optional[datetime.date] = None,
    start: Optional[datetime.date] = None,
    end: Optional[datetime.date] = None,
    user_id: Optional[str] = None,
    current_user: dict = Depends(hr_admin_user),
    db: Session = Depends(get_db),
):
    report = attendance_service.get_attendance_report(db, period, anchor, start, end, user_id)
    prepared_by = f"{current_user.get('given_name') or ''} {current_user.get('family_name') or ''}".strip()
    pdf, filename = render_attendance_report(db, report, prepared_by, current_user["user_id"])
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/{user_id}", response_model=list[EmployeeReportResponse])
def get_employee_reports(user_id: str, current_user: dict = Depends(employee_user), db: Session = Depends(get_db)):
    """Fetch daily reports for an employee (HR admins, or the employee themselves)."""
    if current_user["user_id"] != user_id and missing_permissions(current_user, [HR_ADMIN_PERMISSION]):
        raise HTTPException(status_code=403, detail="Not authorized to view these reports")
    return attendance_service.list_reports(db, user_id)


@router.put("/reports/{report_id}/confirm", response_model=EmployeeReportResponse)
def confirm_report(
    report_id: str,
    status: Literal["confirmed", "rejected"],
    notes: Optional[str] = None,
    current_user: dict = Depends(hr_admin_user),
    db: Session = Depends(get_db),
):
    """Admin confirms or rejects a daily report."""
    return attendance_service.review_report(db, report_id, status, notes)


# --- WORK SCHEDULE ---

@router.get("/schedule", response_model=list[ScheduleDayOut], summary="Company weekly schedule")
def get_company_schedule(current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return schedule_service.get_company_schedule(db)


@router.put("/schedule", response_model=list[ScheduleDayOut], summary="Update company weekly schedule")
def set_company_schedule(payload: CompanyScheduleUpdate, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return schedule_service.set_company_schedule(db, payload.days)


@router.get("/schedule/employees/{user_id}", response_model=EmployeeScheduleOut, summary="Employee weekly overrides")
def get_employee_schedule(user_id: str, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return EmployeeScheduleOut(user_id=user_id, days=schedule_service.get_employee_schedule(db, user_id))


@router.put("/schedule/employees/{user_id}", response_model=EmployeeScheduleOut, summary="Replace employee weekly overrides")
def set_employee_schedule(
    user_id: str, payload: EmployeeScheduleUpdate, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)
):
    return EmployeeScheduleOut(user_id=user_id, days=schedule_service.set_employee_schedule(db, user_id, payload.days))


@router.get("/schedule/overrides", response_model=list[ScheduleOverrideOut], summary="List date overrides")
def list_schedule_overrides(
    start: Optional[datetime.date] = None,
    end: Optional[datetime.date] = None,
    user_id: Optional[str] = Query(None, description="Only this employee's overrides"),
    current_user: dict = Depends(hr_admin_user),
    db: Session = Depends(get_db),
):
    start, end = _month_bounds(start, end)
    return schedule_service.list_overrides(db, start, end, user_id)


@router.post("/schedule/overrides", response_model=ScheduleOverrideOut, summary="Create or replace a date override")
def upsert_schedule_override(payload: ScheduleOverrideCreate, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return schedule_service.upsert_override(db, payload, current_user["user_id"])


@router.delete("/schedule/overrides/{override_id}", status_code=204, summary="Delete a date override")
def delete_schedule_override(override_id: str, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    schedule_service.delete_override(db, override_id)


# --- MEETINGS ---

@router.get("/meetings", response_model=list[MyMeetingOut], summary="My meetings")
def get_my_meetings(current_user: dict = Depends(employee_user), db: Session = Depends(get_db)):
    return meeting_service.list_my_meetings(db, current_user["user_id"])


@router.get("/employees/{user_id}/meetings", response_model=list[MyMeetingOut], summary="An employee's meetings (admin)")
def get_employee_meetings(user_id: str, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    employee = get_employee_or_404(db, user_id, include_inactive=True)
    return meeting_service.list_my_meetings(db, employee.user_id)


@router.get("/meetings/all", response_model=list[AdminMeetingOut], summary="All meetings (admin)")
def get_all_meetings(current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return meeting_service.list_all_meetings(db)


@router.post("/meetings", response_model=MeetingResponse, status_code=201, summary="Schedule a meeting")
def schedule_meeting(
    payload: MeetingCreate,
    current_user: dict = Depends(hr_admin_user),
    db: Session = Depends(get_db),
):
    meeting, _emails = meeting_service.create_meeting(db, payload, current_user["user_id"])
    return meeting


@router.get("/meetings/{meeting_id}", response_model=MeetingDetailOut, summary="Meeting details and attendee roster")
def get_meeting(meeting_id: str, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return meeting_service.get_meeting_detail(db, meeting_id)


@router.patch("/meetings/{meeting_id}", response_model=MeetingResponse, summary="Update or reschedule a meeting")
def update_meeting(
    meeting_id: str,
    payload: MeetingUpdate,
    current_user: dict = Depends(hr_admin_user),
    db: Session = Depends(get_db),
):
    meeting, _emails = meeting_service.update_meeting(db, meeting_id, payload)
    return meeting


@router.post("/meetings/{meeting_id}/cancel", response_model=MeetingResponse, summary="Cancel a meeting")
def cancel_meeting(
    meeting_id: str,
    current_user: dict = Depends(hr_admin_user),
    db: Session = Depends(get_db),
):
    meeting, _emails = meeting_service.cancel_meeting(db, meeting_id)
    return meeting


@router.put("/meetings/{meeting_id}/attendance", response_model=MeetingDetailOut, summary="Record attendance (bulk)")
def mark_attendance(
    meeting_id: str, payload: MeetingAttendanceUpdate, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)
):
    return meeting_service.mark_attendance(db, meeting_id, payload.records, current_user["user_id"])


@router.post("/meetings/{meeting_id}/rsvp", summary="Accept or decline a meeting")
def respond_to_meeting(
    meeting_id: str, payload: MeetingRsvpIn, current_user: dict = Depends(employee_user), db: Session = Depends(get_db)
):
    attendee = meeting_service.respond(db, meeting_id, current_user["user_id"], payload.response)
    return {"status": attendee.status}


@router.post("/meetings/{meeting_id}/check-in", summary="Check in to a meeting")
def check_in_to_meeting(
    meeting_id: str, payload: MeetingCheckInIn, current_user: dict = Depends(employee_user), db: Session = Depends(get_db)
):
    attendee = meeting_service.check_in(db, meeting_id, current_user["user_id"], payload)
    return {"attendance": attendee.attendance, "checked_in_at": attendee.checked_in_at}


# --- WORK LOCATIONS ---

@router.get("/locations", response_model=list[WorkLocationOut], summary="Work locations (office and venues)")
def list_work_locations(current_user: dict = Depends(employee_user), db: Session = Depends(get_db)):
    return location_service.list_locations(db)


@router.post("/locations", response_model=WorkLocationOut, status_code=201, summary="Add a work location")
def create_work_location(payload: WorkLocationIn, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return location_service.create_location(db, payload)


@router.put("/locations/{location_id}", response_model=WorkLocationOut, summary="Update a work location")
def update_work_location(
    location_id: str, payload: WorkLocationIn, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)
):
    return location_service.update_location(db, location_id, payload)


@router.post("/locations/{location_id}/default", response_model=WorkLocationOut, summary="Make the default location")
def make_default_location(location_id: str, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return location_service.set_default_location(db, location_id)


@router.post("/locations/{location_id}/archive", response_model=WorkLocationOut, summary="Archive a location")
def archive_work_location(location_id: str, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return location_service.set_location_active(db, location_id, False)


@router.post("/locations/{location_id}/restore", response_model=WorkLocationOut, summary="Restore an archived location")
def restore_work_location(location_id: str, current_user: dict = Depends(hr_admin_user), db: Session = Depends(get_db)):
    return location_service.set_location_active(db, location_id, True)
