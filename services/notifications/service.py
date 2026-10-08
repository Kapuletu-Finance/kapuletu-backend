from dataclasses import dataclass
import uuid
from typing import List, Optional
from common.utils import parse_uuid
from sqlalchemy.orm import Session
from sqlalchemy import delete, func, select, update
from datetime import datetime

from models.notification import Notification
from models.users import User

def _uid(user_id):
    """Convert a string or UUID to a uuid.UUID object for DB queries."""
    if isinstance(user_id, uuid.UUID):
        return user_id
    return uuid.UUID(str(user_id))


def get_notifications_for_user(db: Session, user_id: str, limit: int = 50) -> List[Notification]:
    stmt = select(Notification).where(
        Notification.user_id == parse_uuid(_uid(user_id))
    ).order_by(Notification.created_at.desc()).limit(limit)
    return db.execute(stmt).scalars().all()

def get_unread_count(db: Session, user_id: str) -> int:
    stmt = select(func.count()).select_from(Notification).where(
        Notification.user_id == parse_uuid(_uid(user_id)),
        Notification.is_read == False
    )
    return db.execute(stmt).scalar() or 0

def mark_as_read(db: Session, notification_id: str, user_id: str) -> bool:
    stmt = select(Notification).where(
        Notification.notification_id == notification_id,
        Notification.user_id == parse_uuid(_uid(user_id))
    )
    notification = db.execute(stmt).scalars().first()
    if notification:
        notification.is_read = True
        db.commit()
        return True
    return False

def mark_all_as_read(db: Session, user_id: str) -> int:
    stmt = update(Notification).where(
        Notification.user_id == parse_uuid(_uid(user_id)),
        Notification.is_read == False
    ).values(is_read=True)
    result = db.execute(stmt)
    db.commit()
    return result.rowcount

def delete_notification(db: Session, notification_id: str, user_id: str) -> bool:
    stmt = select(Notification).where(
        Notification.notification_id == notification_id,
        Notification.user_id == parse_uuid(_uid(user_id))
    )
    notification = db.execute(stmt).scalars().first()
    if notification:
        db.delete(notification)
        db.commit()
        return True
    return False

def clear_all_notifications(db: Session, user_id: str) -> int:
    stmt = delete(Notification).where(
        Notification.user_id == parse_uuid(_uid(user_id))
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount

@dataclass(frozen=True)
class EmailJob:
    """A queued email: hand its fields to send_email_task (inline, in a thread, or via BackgroundTasks)."""
    log_id: str
    to_email: str
    subject: str
    html_body: str


def queue_email(db: Session, user_id, to_email: str, subject: str, html_body: str) -> EmailJob:
    """
    Records a QUEUED CommunicationLog for an outgoing email and returns the job to dispatch.
    The caller commits and decides how to run send_email_task, keeping slow sends off the request path.
    """
    from models.communication_logs import CommunicationLog
    log = CommunicationLog(
        user_id=_uid(user_id) if user_id else None,
        channel="EMAIL",
        destination=to_email,
        subject=subject,
        status="QUEUED",
    )
    db.add(log)
    db.flush()
    return EmailJob(log_id=str(log.log_id), to_email=to_email, subject=subject, html_body=html_body)


def create_notification(db: Session, user_id: str, title: str, message: str, type: str, related_entity_id: Optional[str] = None):
    try:
        new_notification = Notification(
            user_id=_uid(user_id),
            title=title,
            message=message,
            type=type,
            related_entity_id=related_entity_id,
            is_read=False
        )
        db.add(new_notification)
        db.commit()
    except Exception as e:
        db.rollback()
        from common.logger import get_logger
        get_logger(__name__).error(f"Failed to create notification: {e}", exc_info=True)
