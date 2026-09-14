from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any

from common.database import get_db
from common.auth_dependencies import get_verified_user, get_admin_user
from services.notifications.schemas import (
    NotificationListOut, 
    UnreadCountOut, 
    BroadcastIn
)
from services.notifications import service

router = APIRouter(prefix="/notifications", tags=["11. Notifications"])

@router.get("", response_model=NotificationListOut, summary="Get User Notifications")
async def get_notifications(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Fetch all notifications for the authenticated user."""
    user_id = current_user.get("sub")
    notifications = service.get_notifications_for_user(db, user_id)
    unread_count = service.get_unread_count(db, user_id)
    return NotificationListOut(
        notifications=notifications,
        unread_count=unread_count
    )

@router.get("/unread-count", response_model=UnreadCountOut, summary="Get Unread Count")
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Fetch just the count of unread notifications for the UI badge."""
    user_id = current_user.get("sub")
    unread_count = service.get_unread_count(db, user_id)
    return UnreadCountOut(unread_count=unread_count)

@router.patch("/{notification_id}/read", summary="Mark Notification as Read")
async def mark_notification_as_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Mark a specific notification as read."""
    user_id = current_user.get("sub")
    success = service.mark_as_read(db, notification_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success", "message": "Notification marked as read"}

@router.post("/mark-all-read", summary="Mark All as Read")
async def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Mark all unread notifications as read."""
    user_id = current_user.get("sub")
    updated_count = service.mark_all_as_read(db, user_id)
    return {"status": "success", "updated_count": updated_count}

@router.delete("/{notification_id}", summary="Delete Notification")
async def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Delete a specific notification."""
    user_id = current_user.get("sub")
    success = service.delete_notification(db, notification_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success", "message": "Notification deleted"}

@router.delete("/clear-all", summary="Clear All Notifications")
async def clear_all_notifications(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Delete all notifications for the current user."""
    user_id = current_user.get("sub")
    deleted_count = service.clear_all_notifications(db, user_id)
    return {"status": "success", "deleted_count": deleted_count}

@router.post("/broadcast", summary="Broadcast Notification (Admin Only)")
async def broadcast_notification(
    payload: BroadcastIn,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Admin endpoint to broadcast notifications.
    Can dispatch via in_app, email, and whatsapp channels.
    Can target all_members, specific_member, or custom_selection.
    """
    try:
        result = service.broadcast_notification(db, payload)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
