"""Daily attendance: schedule-enforced clock-in/out, the admin register, personal history and period reports."""
import datetime
from collections import defaultdict
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from common.utils import NAIROBI_TZ, nairobi_now, nairobi_today, parse_uuid
from models.hr import AttendanceAdjustment, EmployeeReport, Meeting, MeetingAttendee
from models.users import User
from services.hr.directory import active_employees_query, assert_within_location, get_employee_or_404
from services.hr.labels import ATTENDANCE_STATUS_LABELS
from services.hr.schedule_service import MAX_SUMMARY_DAYS, ScheduleResolver, date_range, validate_range
from services.hr.schemas import (
    AttendanceAdjustmentIn, AttendanceDayOut, AttendanceHighlights, AttendanceRegisterOut, AttendanceRegisterRow, AttendanceReportOut,
    AttendanceReportRow, AttendanceSummary, AttendanceTrendPoint, EmployeeBrief, EmployeeClockInCreate,
    EmployeeCount, EmployeeReportResponse, MeetingAttendanceSummary, MyAttendanceOut, ResolvedDay, TodayStatusOut,
)


def _today_report(db: Session, user_id) -> Optional[EmployeeReport]:
    return db.query(EmployeeReport).filter(
        EmployeeReport.user_id == parse_uuid(user_id),
        EmployeeReport.report_date == nairobi_today(),
    ).first()


def _resolve_today(db: Session, user_id) -> ResolvedDay:
    today = nairobi_today()
    return ScheduleResolver(db, [user_id], today, today).resolve(user_id, today)


def _clock_in_blocker(day: ResolvedDay, report: Optional[EmployeeReport], now: datetime.datetime) -> Optional[str]:
    """Why the employee cannot clock in right now, or None when they can."""
    if report and report.clock_in_time:
        return "You have already clocked in today."
    if day.mode == "off":
        suffix = f" ({day.reason})" if day.reason else ""
        return f"Today is not a scheduled workday{suffix}."
    if day.mode == "physical" and day.location is None:
        return "No work location has been configured by the administrator yet. Please contact your admin."
    if now.time() > day.cutoff_time:
        return (
            f"Shift entry closed. It is past the {day.cutoff_time.strftime('%H:%M')} cut-off time for today's shift. "
            "Please contact your supervisor."
        )
    return None


def get_today_status(db: Session, user_id) -> TodayStatusOut:
    day = _resolve_today(db, user_id)
    report = _today_report(db, user_id)
    blocker = _clock_in_blocker(day, report, nairobi_now())
    return TodayStatusOut(
        day=day,
        report=EmployeeReportResponse.model_validate(report) if report else None,
        can_clock_in=blocker is None,
        message=blocker,
    )


def clock_in(db: Session, user_id, payload: EmployeeClockInCreate) -> EmployeeReport:
    """Clock in using the mode the schedule prescribes for today; physical days are geofenced to the day's venue."""
    now = nairobi_now()
    day = _resolve_today(db, user_id)
    report = _today_report(db, user_id)

    blocker = _clock_in_blocker(day, report, now)
    if blocker:
        raise HTTPException(status_code=400 if report and report.clock_in_time else 403, detail=blocker)

    if day.mode == "physical":
        assert_within_location(day.location, payload.latitude, payload.longitude)

    if not report:
        report = EmployeeReport(user_id=parse_uuid(user_id), report_date=now.date())
        db.add(report)
    report.clock_in_time = now
    report.work_mode = day.mode
    report.is_late = now.time() > day.start_time
    report.latitude = payload.latitude if day.mode == "physical" else None
    report.longitude = payload.longitude if day.mode == "physical" else None

    db.commit()
    db.refresh(report)
    return report


def clock_out(db: Session, user_id, work_summary: str) -> EmployeeReport:
    report = _today_report(db, user_id)
    if not report or not report.clock_in_time:
        raise HTTPException(status_code=400, detail="You have not clocked in today.")
    if report.clock_out_time:
        raise HTTPException(status_code=400, detail="Already clocked out today.")

    report.clock_out_time = nairobi_now()
    report.work_summary = work_summary
    report.status = "pending_review"
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, user_id) -> list[EmployeeReport]:
    return db.query(EmployeeReport).filter(
        EmployeeReport.user_id == parse_uuid(user_id)
    ).order_by(EmployeeReport.report_date.desc()).all()


def review_report(db: Session, report_id: str, status: str, notes: Optional[str]) -> EmployeeReport:
    try:
        rid = parse_uuid(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Report not found")
    report = db.query(EmployeeReport).filter(EmployeeReport.id == rid).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.status = status
    if notes:
        report.admin_notes = notes
    db.commit()
    db.refresh(report)
    return report


# --- Register & history ---

def _day_status(day: ResolvedDay, report: Optional[EmployeeReport], now: datetime.datetime) -> str:
    if report and report.clock_in_time:
        return "late" if report.is_late else "present"
    if day.mode == "off":
        return "off"
    today = now.date()
    if day.date > today or (day.date == today and now.time() <= day.cutoff_time):
        return "upcoming"
    return "absent"


def _attendance_days(
    resolver: ScheduleResolver, reports: dict, adjustments: dict, user_id, dates, now
) -> list[AttendanceDayOut]:
    """Per-day attendance; an admin correction (if any) takes precedence over the recorded clock-in."""
    days = []
    for d in dates:
        resolved = resolver.resolve(user_id, d)
        report = reports.get(d)
        adjustment = adjustments.get(d)
        clock_in = report.clock_in_time if report else None
        clock_out = report.clock_out_time if report else None
        if adjustment:
            status = adjustment.status
            if adjustment.status in ("absent", "excused"):
                clock_in = clock_out = None
            else:
                clock_in = adjustment.clock_in_time or clock_in
                clock_out = adjustment.clock_out_time or clock_out
        else:
            status = _day_status(resolved, report, now)
        days.append(AttendanceDayOut(
            date=d,
            mode=resolved.mode,
            status=status,
            clock_in_time=clock_in,
            clock_out_time=clock_out,
            report_id=report.id if report else None,
            report_status=report.status if report and report.clock_in_time else None,
            reason=resolved.reason,
            adjusted=adjustment is not None,
            adjustment_reason=adjustment.reason if adjustment else None,
        ))
    return days


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator * 100, 1) if denominator else None


def _summarize(days: list[AttendanceDayOut], meetings: MeetingAttendanceSummary) -> AttendanceSummary:
    """The one place attendance figures are computed — used by the register, history and reports."""
    counted = [d for d in days if d.status in ("present", "late", "absent")]
    attended = [d for d in counted if d.status != "absent"]
    physical = [d for d in counted if d.mode == "physical"]
    late = sum(1 for d in attended if d.status == "late")

    seconds_worked = sum(
        (d.clock_out_time - d.clock_in_time).total_seconds()
        for d in attended
        if d.clock_in_time and d.clock_out_time
    )
    clock_in_minutes = [
        t.hour * 60 + t.minute
        for t in (d.clock_in_time.astimezone(NAIROBI_TZ) for d in attended if d.clock_in_time)
    ]
    avg_minutes = round(sum(clock_in_minutes) / len(clock_in_minutes)) if clock_in_minutes else None

    return AttendanceSummary(
        scheduled_days=len(counted),
        present=len(attended) - late,
        late=late,
        absent=len(counted) - len(attended),
        excused=sum(1 for d in days if d.status == "excused"),
        attendance_rate=_rate(len(attended), len(counted)),
        punctuality_rate=_rate(len(attended) - late, len(attended)),
        physical_expected=len(physical),
        physical_attended=sum(1 for d in physical if d.status != "absent"),
        hours_worked=round(seconds_worked / 3600, 1),
        avg_clock_in=f"{avg_minutes // 60:02d}:{avg_minutes % 60:02d}" if avg_minutes is not None else None,
        reports_confirmed=sum(1 for d in attended if d.report_status == "confirmed"),
        reports_pending=sum(1 for d in attended if d.report_status == "pending_review"),
        meetings=meetings,
    )


def _combine_meetings(summaries: Iterable[MeetingAttendanceSummary]) -> MeetingAttendanceSummary:
    totals = defaultdict(int)
    for m in summaries:
        for field in ("invited", "attended", "missed", "excused"):
            totals[field] += getattr(m, field)
    return MeetingAttendanceSummary(
        **totals, attendance_rate=_rate(totals["attended"], totals["attended"] + totals["missed"])
    )


def _range_bounds_utc(start: datetime.date, end: datetime.date):
    tz = nairobi_now().tzinfo
    lower = datetime.datetime.combine(start, datetime.time.min, tzinfo=tz)
    upper = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz)
    return lower, upper


def _meeting_summaries(db: Session, user_ids: list, start: datetime.date, end: datetime.date) -> dict:
    """Per-employee attendance counts for non-cancelled meetings that have already started within the range."""
    lower, upper = _range_bounds_utc(start, end)
    rows = db.query(MeetingAttendee.user_id, MeetingAttendee.attendance, func.count()).join(Meeting).filter(
        MeetingAttendee.user_id.in_(user_ids),
        Meeting.status == "scheduled",
        Meeting.start_time >= lower,
        Meeting.start_time < min(upper, datetime.datetime.now(datetime.timezone.utc)),
    ).group_by(MeetingAttendee.user_id, MeetingAttendee.attendance).all()

    counts = defaultdict(lambda: defaultdict(int))
    for uid, attendance, count in rows:
        counts[uid][attendance] += count

    summaries = {}
    for uid in user_ids:
        c = counts.get(uid, {})
        attended, missed, excused = c.get("attended", 0), c.get("missed", 0), c.get("excused", 0)
        summaries[uid] = MeetingAttendanceSummary(
            invited=sum(c.values()),
            attended=attended,
            missed=missed,
            excused=excused,
            attendance_rate=_rate(attended, attended + missed),
        )
    return summaries


def _reports_by_user_and_date(db: Session, user_ids: list, start: datetime.date, end: datetime.date) -> dict:
    reports = db.query(EmployeeReport).filter(
        EmployeeReport.user_id.in_(user_ids),
        EmployeeReport.report_date >= start,
        EmployeeReport.report_date <= end,
    ).all()
    by_user = defaultdict(dict)
    for r in reports:
        by_user[r.user_id][r.report_date] = r
    return by_user


def _adjustments_by_user_and_date(db: Session, user_ids: list, start: datetime.date, end: datetime.date) -> dict:
    rows = db.query(AttendanceAdjustment).filter(
        AttendanceAdjustment.user_id.in_(user_ids),
        AttendanceAdjustment.date >= start,
        AttendanceAdjustment.date <= end,
    ).all()
    by_user = defaultdict(dict)
    for a in rows:
        by_user[a.user_id][a.date] = a
    return by_user


def upsert_adjustment(db: Session, payload: AttendanceAdjustmentIn, actor_id) -> AttendanceAdjustment:
    """Creates or replaces an admin correction for one employee/date, then notifies them and audits it."""
    employee = get_employee_or_404(db, payload.user_id)
    if payload.date > nairobi_today():
        raise HTTPException(status_code=400, detail="Attendance can't be corrected for future dates.")

    adjustment = db.query(AttendanceAdjustment).filter(
        AttendanceAdjustment.user_id == employee.user_id, AttendanceAdjustment.date == payload.date
    ).first()
    previous = adjustment.status if adjustment else None
    if not adjustment:
        adjustment = AttendanceAdjustment(user_id=employee.user_id, date=payload.date)
        db.add(adjustment)
    adjustment.status = payload.status
    adjustment.reason = payload.reason.strip()
    adjustment.clock_in_time = payload.clock_in_time
    adjustment.clock_out_time = payload.clock_out_time
    adjustment.adjusted_by = parse_uuid(actor_id)
    db.commit()
    db.refresh(adjustment)

    label = ATTENDANCE_STATUS_LABELS[payload.status]
    _notify_adjustment(
        db, employee.user_id, payload.date,
        f"Your attendance for {payload.date:%a %d %b %Y} was marked {label}: {adjustment.reason}",
    )
    _audit_adjustment(db, actor_id, employee.user_id, payload.date, {
        "message": f"Attendance for {employee.first_name} {employee.last_name} on {payload.date:%d %b %Y} set to {label}",
        "status": payload.status,
        "previous_adjustment": previous,
        "reason": adjustment.reason,
    })
    return adjustment


def delete_adjustment(db: Session, user_id, day: datetime.date, actor_id) -> None:
    """Removes a correction so the day reverts to what the employee actually recorded."""
    employee = get_employee_or_404(db, user_id)
    adjustment = db.query(AttendanceAdjustment).filter(
        AttendanceAdjustment.user_id == employee.user_id, AttendanceAdjustment.date == day
    ).first()
    if not adjustment:
        raise HTTPException(status_code=404, detail="No correction exists for this day.")
    removed = adjustment.status
    db.delete(adjustment)
    db.commit()

    _notify_adjustment(
        db, employee.user_id, day,
        f"The correction to your attendance for {day:%a %d %b %Y} was removed; your recorded attendance applies.",
    )
    _audit_adjustment(db, actor_id, employee.user_id, day, {
        "message": f"Attendance correction for {employee.first_name} {employee.last_name} on {day:%d %b %Y} removed",
        "removed_status": removed,
    })


def _notify_adjustment(db: Session, user_id, day: datetime.date, message: str) -> None:
    from services.notifications.service import create_notification
    create_notification(
        db=db, user_id=str(user_id), title="Attendance updated", message=message,
        type="attendance_adjusted", related_entity_id=day.isoformat(),
    )


def _audit_adjustment(db: Session, actor_id, user_id, day: datetime.date, details: dict) -> None:
    from services.audit.service import AuditService
    AuditService(db).log_action(
        actor_id=actor_id, action="ATTENDANCE_ADJUSTED", entity_type="ATTENDANCE",
        entity_id=f"{user_id}:{day.isoformat()}", details=details,
    )


def _load_attendance(db: Session, user_ids: list, start: datetime.date, end: datetime.date) -> dict:
    """user_id -> (per-day attendance, meeting summary) for every user over the range, using bulk queries."""
    dates = date_range(start, end)
    now = nairobi_now()
    resolver = ScheduleResolver(db, user_ids, start, end)
    reports = _reports_by_user_and_date(db, user_ids, start, end)
    adjustments = _adjustments_by_user_and_date(db, user_ids, start, end)
    meetings = _meeting_summaries(db, user_ids, start, end)
    return {
        uid: (
            _attendance_days(resolver, reports.get(uid, {}), adjustments.get(uid, {}), uid, dates, now),
            meetings[uid],
        )
        for uid in user_ids
    }


def _ordered_employees(db: Session) -> list[User]:
    return active_employees_query(db).order_by(User.first_name, User.last_name).all()


def get_my_attendance(db: Session, user_id, start: datetime.date, end: datetime.date) -> MyAttendanceOut:
    validate_range(start, end)
    uid = parse_uuid(user_id)
    days, meetings = _load_attendance(db, [uid], start, end)[uid]
    return MyAttendanceOut(start=start, end=end, days=days, summary=_summarize(days, meetings))


def get_register(db: Session, start: datetime.date, end: datetime.date) -> AttendanceRegisterOut:
    validate_range(start, end)
    employees = _ordered_employees(db)
    attendance = _load_attendance(db, [e.user_id for e in employees], start, end)

    rows = []
    for employee in employees:
        days, meetings = attendance[employee.user_id]
        rows.append(AttendanceRegisterRow(
            employee=EmployeeBrief.model_validate(employee),
            days=days,
            summary=_summarize(days, meetings),
        ))
    return AttendanceRegisterOut(start=start, end=end, dates=date_range(start, end), rows=rows)


# --- Period reports (weekly / monthly / quarterly / yearly / custom) ---

def _month_end(day: datetime.date) -> datetime.date:
    return (day.replace(day=1) + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)


def resolve_period(
    period: str,
    anchor: Optional[datetime.date] = None,
    start: Optional[datetime.date] = None,
    end: Optional[datetime.date] = None,
) -> tuple[datetime.date, datetime.date, str, str]:
    """Returns (start, end, label, trend bucket) for the period containing `anchor` (default: today, EAT)."""
    anchor = anchor or nairobi_today()
    if period == "week":
        start = anchor - datetime.timedelta(days=anchor.weekday())
        end = start + datetime.timedelta(days=6)
        return start, end, f"Week {anchor.isocalendar().week}, {start:%d %b} – {end:%d %b %Y}", "day"
    if period == "month":
        start = anchor.replace(day=1)
        return start, _month_end(start), f"{start:%B %Y}", "week"
    if period == "quarter":
        quarter = (anchor.month - 1) // 3
        start = datetime.date(anchor.year, quarter * 3 + 1, 1)
        end = _month_end(datetime.date(anchor.year, quarter * 3 + 3, 1))
        return start, end, f"Q{quarter + 1} {anchor.year}", "month"
    if period == "year":
        return datetime.date(anchor.year, 1, 1), datetime.date(anchor.year, 12, 31), str(anchor.year), "month"

    if not start or not end:
        raise HTTPException(status_code=400, detail="A custom period needs both 'start' and 'end'.")
    validate_range(start, end, MAX_SUMMARY_DAYS)
    span = (end - start).days + 1
    bucket = "day" if span <= 14 else "week" if span <= 93 else "month"
    return start, end, f"{start:%d %b %Y} – {end:%d %b %Y}", bucket


def _trend_buckets(start: datetime.date, end: datetime.date, bucket: str) -> list[tuple[str, datetime.date, datetime.date]]:
    buckets = []
    cursor = start
    while cursor <= end:
        if bucket == "day":
            b_end, label = cursor, f"{cursor:%a %d %b}"
        elif bucket == "week":
            b_end = min(cursor + datetime.timedelta(days=6 - cursor.weekday()), end)
            label = f"{cursor:%d %b} – {b_end:%d %b}"
        else:
            b_end = min(_month_end(cursor), end)
            label = f"{cursor:%b %Y}"
        buckets.append((label, cursor, b_end))
        cursor = b_end + datetime.timedelta(days=1)
    return buckets


def _trend(all_days: list[AttendanceDayOut], start: datetime.date, end: datetime.date, bucket: str) -> list[AttendanceTrendPoint]:
    no_meetings = MeetingAttendanceSummary()
    points = []
    for label, b_start, b_end in _trend_buckets(start, end, bucket):
        s = _summarize([d for d in all_days if b_start <= d.date <= b_end], no_meetings)
        points.append(AttendanceTrendPoint(
            label=label, start=b_start, end=b_end, scheduled_days=s.scheduled_days,
            attended=s.present + s.late, late=s.late, absent=s.absent, attendance_rate=s.attendance_rate,
        ))
    return points


def _highlights(rows: list[AttendanceReportRow], limit: int = 5) -> AttendanceHighlights:
    def top(metric: str) -> list[EmployeeCount]:
        ranked = sorted(
            (r for r in rows if getattr(r.summary, metric) > 0),
            key=lambda r: getattr(r.summary, metric),
            reverse=True,
        )
        return [EmployeeCount(employee=r.employee, count=getattr(r.summary, metric)) for r in ranked[:limit]]

    return AttendanceHighlights(
        perfect_attendance=[
            r.employee for r in rows if r.summary.scheduled_days and not r.summary.absent and not r.summary.late
        ],
        most_absences=top("absent"),
        most_late=top("late"),
    )


def _meetings_held(db: Session, start: datetime.date, end: datetime.date) -> int:
    lower, upper = _range_bounds_utc(start, end)
    return db.query(func.count(Meeting.id)).filter(
        Meeting.status == "scheduled",
        Meeting.start_time >= lower,
        Meeting.start_time < min(upper, datetime.datetime.now(datetime.timezone.utc)),
    ).scalar() or 0


def get_attendance_report(
    db: Session,
    period: str,
    anchor: Optional[datetime.date] = None,
    start: Optional[datetime.date] = None,
    end: Optional[datetime.date] = None,
    user_id: Optional[str] = None,
) -> AttendanceReportOut:
    """Company-wide attendance report, or one employee's statement when user_id is given."""
    start, end, label, bucket = resolve_period(period, anchor, start, end)
    # A single employee's statement also works for suspended staff (history stays reviewable).
    employees = [get_employee_or_404(db, user_id, include_inactive=True)] if user_id else _ordered_employees(db)
    attendance = _load_attendance(db, [e.user_id for e in employees], start, end)

    rows = [
        AttendanceReportRow(employee=EmployeeBrief.model_validate(e), summary=_summarize(*attendance[e.user_id]))
        for e in employees
    ]
    all_days = [day for days, _ in attendance.values() for day in days]

    return AttendanceReportOut(
        period=period,
        label=label,
        start=start,
        end=end,
        bucket=bucket,
        employee_count=len(employees),
        meetings_held=_meetings_held(db, start, end),
        totals=_summarize(all_days, _combine_meetings(m for _, m in attendance.values())),
        trend=_trend(all_days, start, end, bucket),
        rows=rows,
        highlights=_highlights(rows),
        days=attendance[employees[0].user_id][0] if user_id else None,
    )
