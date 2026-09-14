from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user
from services.feedback.service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["16. User Feedback"])

VALID_FEEDBACK_TYPES = {"bug", "feature_request", "ux_issue", "performance", "general"}
VALID_APP_AREAS = {
    "dashboard", "groups", "campaigns", "contributions",
    "reports", "inbox", "notifications", "settings", "other",
}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_STATUSES = {"new", "reviewing", "planned", "in_progress", "shipped", "declined"}


@router.post("", summary="Submit App Feedback")
async def submit_feedback(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user),
):
    """
    Authenticated endpoint — any verified user (treasurer) can submit feedback.
    """
    # Required field validation
    required = ["feedback_type", "app_area", "title", "description"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {missing}")

    if payload["feedback_type"] not in VALID_FEEDBACK_TYPES:
        raise HTTPException(status_code=422, detail="Invalid feedback_type")
    if payload["app_area"] not in VALID_APP_AREAS:
        raise HTTPException(status_code=422, detail="Invalid app_area")
    if payload.get("severity") and payload["severity"] not in VALID_SEVERITIES:
        raise HTTPException(status_code=422, detail="Invalid severity")

    rating = payload.get("overall_rating")
    if rating is not None and not (1 <= int(rating) <= 5):
        raise HTTPException(status_code=422, detail="overall_rating must be between 1 and 5")

    service = FeedbackService(db)
    feedback_id = service.submit(current_user["sub"], payload)
    return {"feedback_id": feedback_id, "message": "Feedback submitted"}


@router.get("/admin", summary="List App Feedback (Admin)")
async def list_feedback(
    feedback_type: Optional[str] = Query(None),
    app_area: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user),
):
    service = FeedbackService(db)
    return service.list_feedback(
        feedback_type=feedback_type,
        app_area=app_area,
        severity=severity,
        status=status,
        page=page,
        limit=limit,
    )


@router.get("/admin/{identifier}", summary="Get Feedback Details (Admin)")
async def get_feedback_details(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user),
):
    service = FeedbackService(db)
    details = service.get_feedback_details(identifier)
    if not details:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return details


@router.patch("/admin/{identifier}", summary="Update Feedback Status (Admin)")
async def update_feedback(
    identifier: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user),
):
    if "status" in payload and payload["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status value")

    service = FeedbackService(db)
    success = service.update_feedback(identifier, current_user["sub"], payload)
    if not success:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"message": "Feedback updated"}
