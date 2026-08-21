import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models.app_feedback import AppFeedback
from models.users import User


class FeedbackService:
    """
    FeedbackService: Handles submission and admin management of structured app feedback.
    """

    def __init__(self, db: Session):
        self.db = db

    def submit(self, user_id: str, payload: dict) -> str:
        """
        Creates a new AppFeedback record from a user submission.
        Returns the generated feedback_id as a string.
        """
        record = AppFeedback(
            user_id=user_id,
            feedback_type=payload["feedback_type"],
            app_area=payload["app_area"],
            severity=payload.get("severity", "medium"),
            title=payload["title"],
            description=payload["description"],
            what_works=payload.get("what_works"),
            what_needs_improvement=payload.get("what_needs_improvement"),
            steps_to_reproduce=payload.get("steps_to_reproduce"),
            expected_behavior=payload.get("expected_behavior"),
            overall_rating=payload.get("overall_rating"),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return str(record.feedback_id)

    def list_feedback(
        self,
        feedback_type: Optional[str] = None,
        app_area: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """
        Returns paginated, filtered app feedback with submitter name joined.
        """
        query = (
            self.db.query(AppFeedback, User)
            .join(User, AppFeedback.user_id == User.user_id)
            .order_by(AppFeedback.created_at.desc())
        )

        if feedback_type:
            query = query.filter(AppFeedback.feedback_type == feedback_type)
        if app_area:
            query = query.filter(AppFeedback.app_area == app_area)
        if severity:
            query = query.filter(AppFeedback.severity == severity)
        if status:
            query = query.filter(AppFeedback.status == status)

        total = query.count()
        rows = query.offset((page - 1) * limit).limit(limit).all()

        items = [
            {
                "feedback_id": str(fb.feedback_id),
                "user_id": str(fb.user_id),
                "user_name": f"{user.first_name} {user.last_name}",
                "feedback_type": fb.feedback_type,
                "app_area": fb.app_area,
                "severity": fb.severity,
                "title": fb.title,
                "description": fb.description,
                "what_works": fb.what_works,
                "what_needs_improvement": fb.what_needs_improvement,
                "steps_to_reproduce": fb.steps_to_reproduce,
                "expected_behavior": fb.expected_behavior,
                "overall_rating": fb.overall_rating,
                "status": fb.status,
                "admin_response": fb.admin_response,
                "created_at": fb.created_at.isoformat(),
            }
            for fb, user in rows
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }

    def update_feedback(self, feedback_id: str, admin_id: str, updates: dict) -> bool:
        """
        Updates the status and/or admin response for a feedback record.
        Sets reviewed_by and reviewed_at on first admin interaction.
        """
        record = (
            self.db.query(AppFeedback)
            .filter(AppFeedback.feedback_id == feedback_id)
            .first()
        )
        if not record:
            return False

        if "status" in updates:
            record.status = updates["status"]
        if "admin_response" in updates:
            record.admin_response = updates["admin_response"]

        # Mark first review
        if not record.reviewed_by:
            record.reviewed_by = admin_id
            record.reviewed_at = datetime.datetime.utcnow()

        self.db.commit()
        return True
