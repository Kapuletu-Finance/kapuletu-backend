import datetime
import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class AppFeedback(Base):
    """
    AppFeedback Model: Stores structured product feedback from users.

    Distinct from SupportTicket (reactive CRM) — this model captures
    proactive, structured feedback: bug reports, feature requests, UX issues,
    performance observations, and general suggestions. Each submission captures
    the area of the app, severity, what is working, what needs improvement,
    and an optional overall satisfaction rating.
    """

    __tablename__ = "app_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True)
    
    # Human-readable ticket number (e.g. FBK-8B2A)
    reference_number = Column(String, unique=True, index=True, nullable=True)

    # --- Classification ---
    # feedback_type: "bug" | "feature_request" | "ux_issue" | "performance" | "general"
    feedback_type = Column(String(30), nullable=False)

    # app_area: "dashboard" | "groups" | "campaigns" | "contributions" |
    #           "reports" | "inbox" | "notifications" | "settings" | "other"
    app_area = Column(String(50), nullable=False)

    # severity: "critical" | "high" | "medium" | "low"
    severity = Column(String(20), nullable=False, default="medium")

    # --- Content ---
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # Optional structured fields — shown conditionally based on feedback_type
    what_works = Column(Text, nullable=True)
    what_needs_improvement = Column(Text, nullable=True)
    steps_to_reproduce = Column(Text, nullable=True)   # bugs
    expected_behavior = Column(Text, nullable=True)    # bugs + feature requests

    # --- Rating ---
    overall_rating = Column(Integer, nullable=True)  # 1–5

    # --- Admin lifecycle ---
    # status: "new" | "reviewing" | "planned" | "in_progress" | "shipped" | "declined"
    status = Column(String(20), nullable=False, default="new")
    admin_response = Column(Text, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # --- Timestamps ---
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
