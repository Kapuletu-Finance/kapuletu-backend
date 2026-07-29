from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete
from datetime import datetime

from models.notification import Notification
from models.users import User
from services.notifications.schemas import BroadcastIn, TargetType, BroadcastChannel

def get_notifications_for_user(db: Session, user_id: str, limit: int = 50) -> List[Notification]:
    stmt = select(Notification).where(
        Notification.user_id == user_id
    ).order_by(Notification.created_at.desc()).limit(limit)
    return db.execute(stmt).scalars().all()

def get_unread_count(db: Session, user_id: str) -> int:
    stmt = select(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read == False
    )
    return len(db.execute(stmt).scalars().all())

def mark_as_read(db: Session, notification_id: str, user_id: str) -> bool:
    stmt = select(Notification).where(
        Notification.notification_id == notification_id,
        Notification.user_id == user_id
    )
    notification = db.execute(stmt).scalars().first()
    if notification:
        notification.is_read = True
        db.commit()
        return True
    return False

def mark_all_as_read(db: Session, user_id: str) -> int:
    stmt = update(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read == False
    ).values(is_read=True)
    result = db.execute(stmt)
    db.commit()
    return result.rowcount

def delete_notification(db: Session, notification_id: str, user_id: str) -> bool:
    stmt = select(Notification).where(
        Notification.notification_id == notification_id,
        Notification.user_id == user_id
    )
    notification = db.execute(stmt).scalars().first()
    if notification:
        db.delete(notification)
        db.commit()
        return True
    return False

def clear_all_notifications(db: Session, user_id: str) -> int:
    stmt = delete(Notification).where(
        Notification.user_id == user_id
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount

def broadcast_notification(db: Session, payload: BroadcastIn) -> dict:
    target_users = []
    
    if payload.target_type == TargetType.all_members:
        target_users = db.execute(select(User)).scalars().all()
    elif payload.target_type in (TargetType.specific_member, TargetType.custom_selection):
        if not payload.target_ids:
            raise ValueError("target_ids must be provided for specific or custom selections")
        stmt = select(User).where(User.user_id.in_(payload.target_ids))
        target_users = db.execute(stmt).scalars().all()

    in_app_count = 0
    email_count = 0
    whatsapp_count = 0

    # 1. Handle In-App Delivery
    if BroadcastChannel.in_app in payload.channels:
        new_notifications = []
        for user in target_users:
            new_notifications.append(
                Notification(
                    user_id=str(user.user_id),
                    title=payload.title,
                    message=payload.message,
                    type="admin_broadcast",
                    is_read=False
                )
            )
        if new_notifications:
            db.add_all(new_notifications)
            db.commit()
            in_app_count = len(new_notifications)

    # 2. Handle Email Delivery (Mocked integration)
    if BroadcastChannel.email in payload.channels:
        # TODO: Hook into actual Kapuletu email service (e.g., SES/SendGrid)
        # For now, we simulate dispatch.
        email_count = len(target_users)
        
    # 3. Handle WhatsApp Delivery (Mocked integration)
    if BroadcastChannel.whatsapp in payload.channels:
        # TODO: Hook into actual Kapuletu WhatsApp service (e.g., Twilio/Infobip)
        whatsapp_count = len(target_users)

    return {
        "status": "success",
        "dispatched": {
            "in_app": in_app_count,
            "email": email_count,
            "whatsapp": whatsapp_count,
            "total_targets": len(target_users)
        }
    }

def create_notification(db: Session, user_id: str, title: str, message: str, type: str, related_entity_id: Optional[str] = None):
    try:
        new_notification = Notification(
            user_id=user_id,
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
        import logging
        logging.getLogger(__name__).error(f"Failed to create notification: {e}")
