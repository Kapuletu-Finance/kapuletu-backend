"""
Meetings: audience resolution, lifecycle (create / update / cancel), RSVP, self check-in,
admin attendance marking, reminders and participant notifications (in-app + email).

Functions that notify people return EmailJobs; callers dispatch them off the request path.
"""
import datetime
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException
from markupsafe import escape
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from common.config import get_config
from common.utils import NAIROBI_TZ, parse_uuid
from models.hr import Meeting, MeetingAttendee, WorkLocation
from models.users import User
from services.hr.directory import active_employees_query, assert_within_location, get_default_location
from services.hr.location_service import require_active_location
from services.hr.schemas import (
    AdminMeetingOut, MeetingAttendanceRecordIn, MeetingAttendeeOut, MeetingCheckInIn, MeetingCounts,
    MeetingCreate, MeetingDetailOut, MeetingResponse, MeetingUpdate, MyMeetingOut, WorkLocationOut,
)
from services.notifications.service import EmailJob, create_notification, queue_email
from services.notifications.templates.render import render_email_template

CHECK_IN_OPENS_BEFORE = datetime.timedelta(minutes=15)

# (attendee column, window lower bound, window upper bound, notice) — a reminder is due when
# lower < time until start <= upper. Windows do not overlap, so one run never sends both.
REMINDER_WINDOWS = (
    ("reminder_24h_sent_at", datetime.timedelta(hours=1), datetime.timedelta(hours=24), "reminder_24h"),
    ("reminder_1h_sent_at", datetime.timedelta(0), datetime.timedelta(hours=1), "reminder_1h"),
)

# notice -> (notification type, subject template, intro sentence, show "open workspace" button)
_NOTICES = {
    "invited": ("meeting_invited", "Meeting invitation: {title}",
                "You have been invited to the meeting below. Please confirm whether you can attend.", True),
    "updated": ("meeting_updated", "Meeting updated: {title}",
                "The details of a meeting you are invited to have changed. Please review them and confirm your attendance again.", True),
    "cancelled": ("meeting_cancelled", "Meeting cancelled: {title}",
                  "The meeting below has been cancelled.", False),
    "removed": ("meeting_removed", "Removed from meeting: {title}",
                "You are no longer on the attendee list for the meeting below.", False),
    "reminder_24h": ("meeting_reminder", "Reminder: {title} is in 24 hours",
                     "This is a reminder about your upcoming meeting.", True),
    "reminder_1h": ("meeting_reminder", "Starting soon: {title}",
                    "Your meeting starts in about an hour.", True),
}

_SCHEDULE_FIELDS = ("meeting_type", "location_id", "location_or_url", "start_time", "end_time")
_DETAIL_FIELDS = ("title", "description") + _SCHEDULE_FIELDS


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# --- Lookups & validation ---

def _get_meeting(db: Session, meeting_id) -> Meeting:
    try:
        mid = parse_uuid(meeting_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    meeting = db.query(Meeting).filter(Meeting.id == mid).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


def _get_attendee(db: Session, meeting: Meeting, user_id) -> MeetingAttendee:
    attendee = db.query(MeetingAttendee).filter(
        MeetingAttendee.meeting_id == meeting.id,
        MeetingAttendee.user_id == parse_uuid(user_id),
    ).first()
    if not attendee:
        raise HTTPException(status_code=404, detail="You are not on the attendee list for this meeting.")
    return attendee


def _validate_details(meeting: Meeting) -> None:
    if meeting.end_time <= meeting.start_time:
        raise HTTPException(status_code=400, detail="The meeting must end after it starts.")
    if meeting.end_time <= _utcnow():
        raise HTTPException(status_code=400, detail="The meeting cannot end in the past.")
    link = (meeting.location_or_url or "").strip()
    if meeting.meeting_type == "online" and link and not link.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Online meeting links must start with http:// or https://.")


def _ensure_open(meeting: Meeting) -> None:
    if meeting.status == "cancelled":
        raise HTTPException(status_code=400, detail="This meeting has been cancelled.")
    if meeting.end_time <= _utcnow():
        raise HTTPException(status_code=400, detail="This meeting has already ended.")


def _check_in_window_open(meeting: Meeting, now: datetime.datetime) -> bool:
    return meeting.start_time - CHECK_IN_OPENS_BEFORE <= now <= meeting.end_time


def _can_check_in(meeting: Meeting, attendee: MeetingAttendee, now: datetime.datetime) -> bool:
    return (
        meeting.status == "scheduled"
        and attendee.checked_in_at is None
        and attendee.attendance != "attended"
        and _check_in_window_open(meeting, now)
    )


def resolve_audience(db: Session, audience: str, roles: list[str], attendee_ids: list) -> list[User]:
    """Turns an audience choice (everyone / by role / custom list) into the active employees it covers."""
    query = active_employees_query(db)
    if audience == "roles":
        query = query.filter(User.role.in_(roles))
    elif audience == "custom":
        ids = {parse_uuid(i) for i in attendee_ids}
        query = query.filter(User.user_id.in_(ids))

    users = query.all()
    if audience == "custom" and len(users) != len(ids):
        raise HTTPException(status_code=400, detail="Some selected people are not active employees.")
    if not users:
        raise HTTPException(status_code=400, detail="No active employees match the selected audience.")
    return users


# --- Venues ---

def _venue(meeting: Meeting, default: Optional[WorkLocation]) -> Optional[WorkLocation]:
    """Where an in-person meeting takes place: its chosen venue, else the default work location."""
    if meeting.meeting_type != "physical":
        return None
    return meeting.location or default


def _apply_venue(db: Session, meeting: Meeting) -> None:
    """Online meetings have no venue; a chosen in-person venue must be an active location."""
    if meeting.meeting_type != "physical":
        meeting.location_id = None
    elif meeting.location_id is not None:
        require_active_location(db, meeting.location_id)
    elif get_default_location(db) is None:
        raise HTTPException(
            status_code=400,
            detail="Add a work location before scheduling in-person meetings, so check-ins can be verified.",
        )


def meeting_out(meeting: Meeting, default: Optional[WorkLocation]) -> MeetingResponse:
    out = MeetingResponse.model_validate(meeting)
    venue = _venue(meeting, default)
    out.location = WorkLocationOut.model_validate(venue) if venue else None
    return out


# --- Notifications ---

def _format_when(meeting: Meeting) -> str:
    start = meeting.start_time.astimezone(NAIROBI_TZ)
    end = meeting.end_time.astimezone(NAIROBI_TZ)
    end_fmt = "%H:%M" if start.date() == end.date() else "%a %d %b %Y, %H:%M"
    return f"{start.strftime('%a %d %b %Y, %H:%M')} – {end.strftime(end_fmt)} EAT"


def _notify(db: Session, meeting: Meeting, users: list[User], notice: str) -> list[EmailJob]:
    """Sends an in-app notification to each user and queues the matching email."""
    if not users:
        return []
    notif_type, subject_template, intro, show_cta = _NOTICES[notice]
    subject = subject_template.format(title=meeting.title)
    when = _format_when(meeting)
    is_online = meeting.meeting_type == "online"
    venue = _venue(meeting, get_default_location(db))
    # In person: "<venue> — <room details>"; online: the join link.
    place = (
        meeting.location_or_url if is_online
        else " — ".join(filter(None, [venue.name if venue else None, meeting.location_or_url]))
    )
    # The email Jinja environment does not autoescape, so escape admin-supplied text here.
    email_context = dict(
        heading=escape(subject),
        intro=intro,
        title=escape(meeting.title),
        when=when,
        mode_label="Online" if is_online else "In person",
        is_online=is_online,
        location=escape(place) if place else None,
        description=escape(meeting.description) if meeting.description else None,
        show_cta=show_cta,
        cta_url=f"{get_config().FRONTEND_URL.rstrip('/')}/employee",
    )

    jobs = []
    for user in users:
        create_notification(
            db=db,
            user_id=str(user.user_id),
            title=subject,
            message=f"{intro} {meeting.title} — {when}.",
            type=notif_type,
            related_entity_id=str(meeting.id),
        )
        if user.email:
            html = render_email_template("meeting_notice.html", name=escape(user.first_name or "there"), **email_context)
            jobs.append(queue_email(db, user.user_id, user.email, subject, html))
    db.commit()
    return jobs


# --- Read models ---

def _counts_by_meeting(db: Session, meeting_ids: list) -> dict:
    def count_where(condition):
        return func.sum(case((condition, 1), else_=0))

    rows = db.query(
        MeetingAttendee.meeting_id,
        func.count(MeetingAttendee.id),
        count_where(MeetingAttendee.status == "accepted"),
        count_where(MeetingAttendee.status == "declined"),
        count_where(MeetingAttendee.attendance == "attended"),
        count_where(MeetingAttendee.attendance == "missed"),
        count_where(MeetingAttendee.attendance == "excused"),
    ).filter(MeetingAttendee.meeting_id.in_(meeting_ids)).group_by(MeetingAttendee.meeting_id).all()

    return {
        row[0]: MeetingCounts(
            total=row[1], accepted=row[2] or 0, declined=row[3] or 0,
            attended=row[4] or 0, missed=row[5] or 0, excused=row[6] or 0,
        )
        for row in rows
    }


def _admin_out(meeting: Meeting, counts: dict, default: Optional[WorkLocation]) -> dict:
    return {**meeting_out(meeting, default).model_dump(), "counts": counts.get(meeting.id, MeetingCounts())}


def list_all_meetings(db: Session) -> list[AdminMeetingOut]:
    meetings = db.query(Meeting).options(joinedload(Meeting.location)).order_by(Meeting.start_time.desc()).all()
    counts = _counts_by_meeting(db, [m.id for m in meetings])
    default = get_default_location(db)
    return [AdminMeetingOut(**_admin_out(m, counts, default)) for m in meetings]


def get_meeting_detail(db: Session, meeting_id) -> MeetingDetailOut:
    meeting = _get_meeting(db, meeting_id)
    attendees = db.query(MeetingAttendee).options(joinedload(MeetingAttendee.user)).filter(
        MeetingAttendee.meeting_id == meeting.id
    ).all()
    attendees.sort(key=lambda a: (a.user.first_name.lower(), a.user.last_name.lower()))
    return MeetingDetailOut(
        **_admin_out(meeting, _counts_by_meeting(db, [meeting.id]), get_default_location(db)),
        attendees=[
            MeetingAttendeeOut(
                user_id=a.user_id,
                first_name=a.user.first_name,
                last_name=a.user.last_name,
                email=a.user.email,
                role=a.user.role,
                status=a.status,
                responded_at=a.responded_at,
                attendance=a.attendance,
                checked_in_at=a.checked_in_at,
                marked_by=a.marked_by,
            )
            for a in attendees
        ],
    )


def list_my_meetings(db: Session, user_id) -> list[MyMeetingOut]:
    now = _utcnow()
    rows = db.query(Meeting, MeetingAttendee).join(MeetingAttendee).options(joinedload(Meeting.location)).filter(
        MeetingAttendee.user_id == parse_uuid(user_id)
    ).order_by(Meeting.start_time.asc()).all()
    default = get_default_location(db)
    return [
        MyMeetingOut(
            **meeting_out(meeting, default).model_dump(),
            my_status=attendee.status,
            my_attendance=attendee.attendance,
            checked_in_at=attendee.checked_in_at,
            can_check_in=_can_check_in(meeting, attendee, now),
        )
        for meeting, attendee in rows
    ]


# --- Admin lifecycle ---

def create_meeting(db: Session, payload: MeetingCreate, organizer_id) -> tuple[MeetingResponse, list[EmailJob]]:
    meeting = Meeting(
        title=payload.title.strip(),
        description=payload.description,
        meeting_type=payload.meeting_type,
        location_or_url=payload.location_or_url,
        location_id=payload.location_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status="scheduled",
        audience=payload.audience,
        audience_roles=payload.audience_roles if payload.audience == "roles" else None,
        organizer_id=parse_uuid(organizer_id),
    )
    _validate_details(meeting)
    _apply_venue(db, meeting)
    users = resolve_audience(db, payload.audience, payload.audience_roles, payload.attendee_ids)

    meeting.attendees = [MeetingAttendee(user_id=u.user_id, status="invited") for u in users]
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    jobs = _notify(db, meeting, users, "invited")
    return meeting_out(meeting, get_default_location(db)), jobs


def update_meeting(db: Session, meeting_id, payload: MeetingUpdate) -> tuple[MeetingResponse, list[EmailJob]]:
    """
    Applies detail changes and, when an audience is supplied, re-resolves the attendee list.
    Newly added people are invited, removed people are told, and everyone else is told about
    detail changes. A change of time/place/mode resets RSVPs and reminders for existing attendees.
    """
    meeting = _get_meeting(db, meeting_id)
    _ensure_open(meeting)

    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if k in _DETAIL_FIELDS}
    if "title" in changes and changes["title"]:
        changes["title"] = changes["title"].strip()
    changed = {k for k, v in changes.items() if getattr(meeting, k) != v}
    for key in changed:
        setattr(meeting, key, changes[key])
    _validate_details(meeting)
    _apply_venue(db, meeting)

    existing = {a.user_id: a for a in meeting.attendees}
    added_users: list[User] = []
    removed_users: list[User] = []
    if payload.audience is not None:
        users = resolve_audience(db, payload.audience, payload.audience_roles, payload.attendee_ids)
        target_ids = {u.user_id for u in users}
        added_users = [u for u in users if u.user_id not in existing]
        for user_id, attendee in existing.items():
            if user_id not in target_ids:
                removed_users.append(attendee.user)
                meeting.attendees.remove(attendee)
        meeting.attendees.extend(MeetingAttendee(user_id=u.user_id, status="invited") for u in added_users)
        meeting.audience = payload.audience
        meeting.audience_roles = payload.audience_roles if payload.audience == "roles" else None

    removed_ids = {u.user_id for u in removed_users}
    kept = [a for uid, a in existing.items() if uid not in removed_ids]
    if changed & set(_SCHEDULE_FIELDS):
        for attendee in kept:
            attendee.status = "invited"
            attendee.responded_at = None
            attendee.reminder_24h_sent_at = None
            attendee.reminder_1h_sent_at = None

    db.commit()
    db.refresh(meeting)

    jobs = _notify(db, meeting, added_users, "invited")
    jobs += _notify(db, meeting, removed_users, "removed")
    if changed:
        jobs += _notify(db, meeting, [a.user for a in kept], "updated")
    return meeting_out(meeting, get_default_location(db)), jobs


def cancel_meeting(db: Session, meeting_id) -> tuple[MeetingResponse, list[EmailJob]]:
    meeting = _get_meeting(db, meeting_id)
    _ensure_open(meeting)
    meeting.status = "cancelled"
    db.commit()
    db.refresh(meeting)
    jobs = _notify(db, meeting, [a.user for a in meeting.attendees], "cancelled")
    return meeting_out(meeting, get_default_location(db)), jobs


def mark_attendance(db: Session, meeting_id, records: list[MeetingAttendanceRecordIn], actor_id) -> MeetingDetailOut:
    meeting = _get_meeting(db, meeting_id)
    if meeting.status == "cancelled":
        raise HTTPException(status_code=400, detail="This meeting has been cancelled.")
    if any(r.attendance != "excused" for r in records) and _utcnow() < meeting.start_time - CHECK_IN_OPENS_BEFORE:
        raise HTTPException(status_code=400, detail="Attended/missed can only be recorded once the meeting is under way. You can excuse people in advance.")

    attendees = {a.user_id: a for a in meeting.attendees}
    unknown = [str(r.user_id) for r in records if r.user_id not in attendees]
    if unknown:
        raise HTTPException(status_code=400, detail="Some people are not on this meeting's attendee list.")

    actor = parse_uuid(actor_id)
    for record in records:
        attendee = attendees[record.user_id]
        attendee.attendance = record.attendance
        attendee.marked_by = actor
    db.commit()
    return get_meeting_detail(db, meeting.id)


# --- Attendee actions ---

def respond(db: Session, meeting_id, user_id, response: str) -> MeetingAttendee:
    meeting = _get_meeting(db, meeting_id)
    _ensure_open(meeting)
    attendee = _get_attendee(db, meeting, user_id)
    attendee.status = response
    attendee.responded_at = _utcnow()
    db.commit()
    return attendee


def check_in(db: Session, meeting_id, user_id, payload: MeetingCheckInIn) -> MeetingAttendee:
    """Self check-in during the meeting window; in-person meetings require being within the venue's radius."""
    meeting = _get_meeting(db, meeting_id)
    if meeting.status == "cancelled":
        raise HTTPException(status_code=400, detail="This meeting has been cancelled.")
    attendee = _get_attendee(db, meeting, user_id)

    now = _utcnow()
    if attendee.checked_in_at or attendee.attendance == "attended":
        raise HTTPException(status_code=400, detail="You have already checked in to this meeting.")
    if not _check_in_window_open(meeting, now):
        opens = int(CHECK_IN_OPENS_BEFORE.total_seconds() // 60)
        raise HTTPException(status_code=400, detail=f"Check-in opens {opens} minutes before the meeting starts and closes when it ends.")

    if meeting.meeting_type == "physical":
        assert_within_location(_venue(meeting, get_default_location(db)), payload.latitude, payload.longitude)
        attendee.checkin_latitude = payload.latitude
        attendee.checkin_longitude = payload.longitude

    attendee.checked_in_at = now
    attendee.attendance = "attended"
    attendee.marked_by = None
    if attendee.status == "invited":
        attendee.status = "accepted"
        attendee.responded_at = now
    db.commit()
    return attendee


# --- Background worker ---

def send_due_reminders(db: Session, now: Optional[datetime.datetime] = None) -> list[EmailJob]:
    now = now or _utcnow()
    jobs: list[EmailJob] = []
    for column_name, lower, upper, notice in REMINDER_WINDOWS:
        column = getattr(MeetingAttendee, column_name)
        due = db.query(MeetingAttendee).join(Meeting).options(
            joinedload(MeetingAttendee.meeting), joinedload(MeetingAttendee.user)
        ).filter(
            Meeting.status == "scheduled",
            Meeting.start_time > now + lower,
            Meeting.start_time <= now + upper,
            column.is_(None),
            MeetingAttendee.status != "declined",
        ).all()

        recipients = defaultdict(list)
        for attendee in due:
            setattr(attendee, column_name, now)
            # People invited inside this window already got the invitation with the same details.
            invited_at = attendee.created_at or attendee.meeting.created_at
            if invited_at and invited_at > attendee.meeting.start_time - upper:
                continue
            recipients[attendee.meeting].append(attendee.user)
        db.commit()

        for meeting, users in recipients.items():
            jobs += _notify(db, meeting, users, notice)
    return jobs


def finalize_ended_meetings(db: Session, now: Optional[datetime.datetime] = None) -> int:
    """Records everyone without an attendance mark as missed, once per ended meeting."""
    now = now or _utcnow()
    meetings = db.query(Meeting).filter(
        Meeting.status == "scheduled",
        Meeting.end_time < now,
        Meeting.attendance_finalized_at.is_(None),
    ).all()
    for meeting in meetings:
        db.query(MeetingAttendee).filter(
            MeetingAttendee.meeting_id == meeting.id,
            MeetingAttendee.attendance.is_(None),
        ).update({"attendance": "missed"}, synchronize_session=False)
        meeting.attendance_finalized_at = now
    db.commit()
    return len(meetings)
