import datetime
import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from .base import Base


class SupportSessionRating(Base):
    """
    SupportSessionRating: Stores post-session satisfaction feedback submitted
    by the treasurer after a support ticket is resolved.

    Linked 1:1 to a SupportTicket (unique on ticket_id).
    Used by management to track resolution quality, communication clarity,
    and overall support performance over time.
    """
    __tablename__ = "support_session_ratings"

    rating_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Linked ticket (one rating per ticket)
    ticket_id = Column(
        UUID(as_uuid=True),
        ForeignKey("support_tickets.ticket_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Who submitted the rating
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=False,
    )

    # ── Core Questions ──────────────────────────────────────────────────────

    # Q1: Was your issue fully resolved? (Required)
    issue_resolved = Column(Boolean, nullable=False)

    # Q2: Overall satisfaction 1–5 (Required)
    satisfaction_level = Column(Integer, nullable=False)

    # Q3: Clarity of communication 1–5 (Optional)
    response_quality = Column(Integer, nullable=True)

    # Q4: Speed of response 1–5 (Optional)
    response_speed = Column(Integer, nullable=True)

    # Q5: Free-text comment (Optional)
    comment = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    ticket = relationship("SupportTicket", foreign_keys=[ticket_id])
    user = relationship("User", foreign_keys=[user_id])
