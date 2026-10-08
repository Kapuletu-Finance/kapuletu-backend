"""Renders an AttendanceReportOut as an official Kapuletu document (company report or employee statement)."""
from typing import Optional

from sqlalchemy.orm import Session

from common.utils import NAIROBI_TZ
from services.documents.official import OfficialDocument
from services.hr.schemas import AttendanceReportOut, AttendanceSummary
from services.hr.labels import ATTENDANCE_STATUS_LABELS, DAY_MODE_LABELS, format_role

METHODOLOGY = (
    "Scheduled days follow the company work schedule, per-employee patterns and date overrides. "
    "A scheduled day without a clock-in is recorded as absent; clock-ins after the start time are late. "
    "Days corrected by HR (marked 'Adjusted') use the corrected outcome; excused days are excluded from the rates. "
    "Meeting attendance counts meetings that have started in the period (excused meetings are excluded from the rate). "
    "Times are East Africa Time (EAT)."
)


def _pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:g}%"


def _time(value) -> str:
    return value.astimezone(NAIROBI_TZ).strftime("%H:%M") if value else "—"


def _headline_figures(summary: AttendanceSummary) -> list[tuple[str, str, Optional[str]]]:
    attended = summary.present + summary.late
    return [
        ("Attendance rate", _pct(summary.attendance_rate), f"{attended} of {summary.scheduled_days} scheduled days"),
        ("Punctuality", _pct(summary.punctuality_rate), f"{summary.late} late arrival(s)"),
        ("Absences", str(summary.absent), f"{summary.excused} excused day(s) not counted"),
        ("Office days", f"{summary.physical_attended}/{summary.physical_expected}", "Physical days attended / expected"),
        ("Hours worked", f"{summary.hours_worked:g}", "Completed shifts (clock-in to clock-out)"),
        ("Average clock-in", summary.avg_clock_in or "—", "EAT"),
        ("Meeting attendance", _pct(summary.meetings.attendance_rate),
         f"{summary.meetings.attended} of {summary.meetings.invited} meetings"),
        ("Daily reports", f"{summary.reports_confirmed} confirmed", f"{summary.reports_pending} awaiting review"),
    ]


def render_attendance_report(db: Session, report: AttendanceReportOut, prepared_by: str, actor_id: str) -> tuple[bytes, str]:
    """Returns (pdf_bytes, filename)."""
    period_line = f"{report.label}  ·  {report.start:%d %B %Y} – {report.end:%d %B %Y}"
    statement = report.days is not None
    employee = report.rows[0].employee if statement else None

    doc = OfficialDocument(
        db,
        title="Employee Attendance Statement" if statement else "Staff Attendance Report",
        subtitle=(
            f"{employee.first_name} {employee.last_name} ({format_role(employee.role)})  ·  {period_line}"
            if employee else period_line
        ),
        department="HR",
        doc_type="ATS" if statement else "ATT",
        prepared_by=prepared_by,
        orientation="portrait" if statement else "landscape",
    )

    doc.section("Summary")
    figures = _headline_figures(report.totals)
    if not statement:
        figures.insert(0, ("Employees", str(report.employee_count), f"{report.meetings_held} meeting(s) held"))
        figures = figures[:8]
    doc.key_figures(figures)

    doc.section(f"Trend by {report.bucket}")
    doc.table(
        ["Period", "Scheduled days", "Attended", "Late", "Absent", "Attendance rate"],
        [
            [p.label, p.scheduled_days, p.attended, p.late, p.absent, _pct(p.attendance_rate)]
            for p in report.trend
        ],
        col_widths=[0.3, 0.14, 0.14, 0.14, 0.14, 0.14],
        numeric_cols={1, 2, 3, 4, 5},
    )

    if statement:
        doc.section("Daily log")
        doc.table(
            ["Date", "Expected", "Status", "Clock in", "Clock out", "Note"],
            [
                [f"{d.date:%a %d %b %Y}", DAY_MODE_LABELS[d.mode], ATTENDANCE_STATUS_LABELS[d.status],
                 _time(d.clock_in_time), _time(d.clock_out_time),
                 f"Adjusted: {d.adjustment_reason}" if d.adjusted else (d.reason or "")]
                for d in report.days
                if d.status != "upcoming"
            ],
            col_widths=[0.2, 0.13, 0.13, 0.12, 0.12, 0.3],
        )
    else:
        doc.section("Employee breakdown")
        doc.table(
            ["Employee", "Role", "Scheduled", "Present", "Late", "Absent", "Attendance",
             "Punctuality", "Office days", "Hours", "Avg in", "Meetings"],
            [
                [
                    f"{r.employee.first_name} {r.employee.last_name}",
                    format_role(r.employee.role),
                    s.scheduled_days, s.present, s.late, s.absent,
                    _pct(s.attendance_rate), _pct(s.punctuality_rate),
                    f"{s.physical_attended}/{s.physical_expected}",
                    f"{s.hours_worked:g}", s.avg_clock_in or "—",
                    f"{s.meetings.attended}/{s.meetings.invited}",
                ]
                for r in report.rows
                for s in [r.summary]
            ],
            col_widths=[0.15, 0.11, 0.07, 0.07, 0.06, 0.07, 0.08, 0.08, 0.08, 0.06, 0.07, 0.1],
            numeric_cols=set(range(2, 12)),
            empty_message="No active employees.",
        )

        h = report.highlights
        doc.section("Highlights")
        doc.bullet_list([
            "Perfect attendance: " + (
                ", ".join(f"{e.first_name} {e.last_name}" for e in h.perfect_attendance) or "none this period"
            ),
            "Most absences: " + (
                ", ".join(f"{c.employee.first_name} {c.employee.last_name} ({c.count})" for c in h.most_absences) or "none"
            ),
            "Most late arrivals: " + (
                ", ".join(f"{c.employee.first_name} {c.employee.last_name} ({c.count})" for c in h.most_late) or "none"
            ),
        ])

    doc.signature_block(note=METHODOLOGY)

    pdf = doc.build(
        actor_id=actor_id,
        audit_details={
            "period": report.period,
            "start": report.start.isoformat(),
            "end": report.end.isoformat(),
            "employee_id": str(employee.user_id) if employee else None,
        },
    )
    return pdf, f"{doc.filename_stem}.pdf"
