from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid

from common.auth_dependencies import get_current_user, require_role, require_permissions
from common.database import get_db
from models.hr import EmployeeReport, Meeting, MeetingAttendee
from .schemas import EmployeeReportCreate, EmployeeReportResponse, MeetingCreate, MeetingResponse

router = APIRouter(prefix="/hr", tags=["HR & Meetings"])

# --- REPORTING ---

@router.post("/reports/clock-in", response_model=EmployeeReportResponse)
def clock_in(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Clock in for the day."""
    # Check if a report for today already exists
    today = datetime.now(timezone.utc).date()
    existing = db.query(EmployeeReport).filter(
        EmployeeReport.user_id == current_user["user_id"],
        EmployeeReport.report_date == today
    ).first()
    
    if existing:
        if existing.clock_in_time:
            raise HTTPException(status_code=400, detail="Already clocked in today.")
        existing.clock_in_time = datetime.now(timezone.utc)
        report = existing
    else:
        report = EmployeeReport(
            user_id=current_user["user_id"],
            report_date=today,
            clock_in_time=datetime.now(timezone.utc)
        )
        db.add(report)
        
    db.commit()
    db.refresh(report)
    return report

@router.post("/reports/clock-out", response_model=EmployeeReportResponse)
def clock_out(payload: EmployeeReportCreate, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Clock out and submit daily summary."""
    today = datetime.now(timezone.utc).date()
    report = db.query(EmployeeReport).filter(
        EmployeeReport.user_id == current_user["user_id"],
        EmployeeReport.report_date == today
    ).first()
    
    if not report:
        report = EmployeeReport(
            user_id=current_user["user_id"],
            report_date=today,
            clock_in_time=None
        )
        db.add(report)
        
    if report.clock_out_time:
        raise HTTPException(status_code=400, detail="Already clocked out today.")
        
    report.clock_out_time = datetime.now(timezone.utc)
    report.work_summary = payload.work_summary
    report.status = "pending_review"
    
    db.commit()
    db.refresh(report)
    return report

@router.get("/reports/{user_id}", response_model=list[EmployeeReportResponse])
def get_employee_reports(user_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fetch reports for a specific employee (Admin or self)."""
    if current_user["user_id"] != user_id and current_user["role"] not in ["super_admin", "admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Not authorized to view these reports")
        
    reports = db.query(EmployeeReport).filter(EmployeeReport.user_id == user_id).order_by(EmployeeReport.report_date.desc()).all()
    return reports

@router.put("/reports/{report_id}/confirm", response_model=EmployeeReportResponse)
def confirm_report(report_id: str, status: str, notes: str = None, current_user: dict = Depends(require_role(["super_admin", "admin", "ceo"])), db: Session = Depends(get_db)):
    """Admin confirms or rejects a report."""
    if status not in ["confirmed", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be confirmed or rejected.")
        
    report = db.query(EmployeeReport).filter(EmployeeReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
        
    report.status = status
    if notes:
        report.admin_notes = notes
        
    db.commit()
    db.refresh(report)
    return report

# --- MEETINGS ---

@router.post("/meetings", response_model=MeetingResponse)
def schedule_meeting(payload: MeetingCreate, current_user: dict = Depends(require_role(["super_admin", "admin", "ceo"])), db: Session = Depends(get_db)):
    """Schedule a new meeting."""
    meeting = Meeting(
        title=payload.title,
        description=payload.description,
        meeting_type=payload.meeting_type,
        location_or_url=payload.location_or_url,
        start_time=payload.start_time,
        end_time=payload.end_time,
        organizer_id=current_user["user_id"]
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    
    for uid in payload.attendee_ids:
        attendee = MeetingAttendee(
            meeting_id=meeting.id,
            user_id=uid,
            status="invited"
        )
        db.add(attendee)
        
    db.commit()
    
    # Trigger Email/In-App Notifications for invites
    from models.notification import Notification
    from services.notifications.admin_dispatcher import notify_admins_async
    
    for uid in payload.attendee_ids:
        notif = Notification(
            user_id=uid,
            title="New Meeting Scheduled",
            message=f"You have been invited to a new {payload.meeting_type} meeting: {payload.title}",
            related_entity_type="meeting",
            related_entity_id=str(meeting.id)
        )
        db.add(notif)
    db.commit()
    
    notify_admins_async(
        subject="New Meeting Scheduled",
        html_content=f"<p>A new {payload.meeting_type} meeting '<strong>{payload.title}</strong>' has been scheduled by admin/HR.</p>",
        category="hr"
    )
    
    return meeting

@router.get("/meetings")
def get_meetings(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get upcoming meetings for the authenticated user."""
    # Find meetings where they are the organizer OR an attendee
    attendee_subquery = db.query(MeetingAttendee.meeting_id).filter(MeetingAttendee.user_id == current_user["user_id"]).subquery()
    
    meetings = db.query(Meeting).filter(
        (Meeting.organizer_id == current_user["user_id"]) | 
        (Meeting.id.in_(attendee_subquery))
    ).order_by(Meeting.start_time.asc()).all()
    
    return [
        {
            "id": str(m.id),
            "title": m.title,
            "meeting_type": m.meeting_type,
            "start_time": m.start_time,
            "end_time": m.end_time,
            "location_or_url": m.location_or_url
        } for m in meetings
    ]

@router.put("/meetings/{meeting_id}/attendance/{user_id}")
def mark_attendance(meeting_id: str, user_id: str, attendance: str, current_user: dict = Depends(require_role(["super_admin", "admin", "ceo"])), db: Session = Depends(get_db)):
    """Mark if an employee attended or missed a meeting."""
    if attendance not in ["attended", "missed", "excused"]:
        raise HTTPException(status_code=400, detail="Invalid attendance state")
        
    att = db.query(MeetingAttendee).filter(
        MeetingAttendee.meeting_id == meeting_id,
        MeetingAttendee.user_id == user_id
    ).first()
    
    if not att:
        raise HTTPException(status_code=404, detail="Attendee record not found")
        
    att.attendance = attendance
    db.commit()
    return {"message": "Attendance marked successfully"}
