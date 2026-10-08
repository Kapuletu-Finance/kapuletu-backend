"""
Communications: broadcasts, the per-recipient outbox they fan out into, suppressed destinations and
versioned email templates. See docs/communications/AUDIT_AND_REVAMP_PLAN.md.
"""
import datetime
import uuid

from sqlalchemy import (
    JSON,
    UUID,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


class CommBroadcast(Base):
    """
    One announcement or marketing send to an audience over one or more channels.

    Lifecycle: awaiting_approval -> queued -> sending -> completed, or rejected / cancelled.
    The audience is resolved into comm_messages by the dispatcher when the broadcast is due, not at request time.
    """
    __tablename__ = "comm_broadcasts"

    broadcast_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    # "service" (account/product notices, no consent needed) or "marketing" (needs users.marketing_consent)
    category = Column(String(20), nullable=False, default="service")
    status = Column(String(30), nullable=False, default="queued")

    # {"type": "all_users" | "active_subscribers" | "treasurers" | "selected_users", "user_ids": [...]}
    audience = Column(JSONType, nullable=False)
    channels = Column(JSONType, nullable=False)  # ["email", "in_app", "whatsapp"]
    # {"email": {"subject", "html"}, "in_app": {"title", "body"}, "whatsapp": {"template", "language", "params"}}
    content = Column(JSONType, nullable=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_note = Column(Text, nullable=True)

    scheduled_for = Column(DateTime, nullable=True)  # due time; null means as soon as possible
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    recipients_count = Column(Integer, nullable=False, default=0)  # people reached on at least one channel
    # {"email": {"queued": 0, "sent": 0, "failed": 0, "suppressed": 0, ...}, ...}; refreshed by the dispatcher
    stats = Column(JSONType, nullable=False, default=dict)

    legacy_campaign_id = Column(UUID(as_uuid=True), nullable=True)  # broadcast_campaigns row it was migrated from
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        Index("ix_comm_broadcasts_status_due", "status", "scheduled_for"),
        Index("ix_comm_broadcasts_created_at", "created_at"),
    )


class CommMessage(Base):
    """
    The outbox: one message to one destination on one channel. A row exists before anything is sent, so a
    restart resumes where it stopped, and (broadcast, user, channel) is unique so enqueueing twice is harmless.
    """
    __tablename__ = "comm_messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broadcast_id = Column(UUID(as_uuid=True), ForeignKey("comm_broadcasts.broadcast_id", ondelete="CASCADE"),
                          nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    channel = Column(String(20), nullable=False)  # email | whatsapp | in_app
    destination = Column(String(255), nullable=False)  # email address, phone number, or user id for in_app
    category = Column(String(20), nullable=False, default="service")
    # 0 = transactional (OTPs, receipts), 5 = bulk; lower goes first
    priority = Column(SmallInteger, nullable=False, default=5)

    subject = Column(String(255), nullable=True)
    # Per-recipient values merged into the broadcast content at send time (first_name, unsubscribe_url, ...)
    context = Column(JSONType, nullable=False, default=dict)

    # queued -> sending -> sent (-> delivered) | failed | suppressed | cancelled
    status = Column(String(20), nullable=False, default="queued")
    attempts = Column(SmallInteger, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    provider = Column(String(30), nullable=True)
    provider_message_id = Column(String(255), nullable=True)
    error = Column(Text, nullable=True)

    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id", "channel", name="uq_comm_messages_broadcast_user_channel"),
        Index("ix_comm_messages_due", "status", "priority", "next_attempt_at"),
        Index("ix_comm_messages_broadcast", "broadcast_id", "status"),
        Index("ix_comm_messages_user", "user_id"),
        Index("ix_comm_messages_provider_id", "provider_message_id"),
        Index("ix_comm_messages_created_at", "created_at"),
    )


class CommSuppression(Base):
    """
    A destination we must not message on a channel: unsubscribed, bounced, complained, or blocked by hand.
    category "marketing" only blocks marketing; "all" blocks everything except transactional security mail.
    """
    __tablename__ = "comm_suppressions"

    suppression_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel = Column(String(20), nullable=False)
    destination = Column(String(255), nullable=False)  # stored normalised: lower-case email, digits-only phone
    category = Column(String(20), nullable=False, default="all")
    reason = Column(String(30), nullable=False)  # unsubscribed | hard_bounce | complaint | manual
    note = Column(Text, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("channel", "destination", "category", name="uq_comm_suppressions_destination"),
    )


class CommTemplateVersion(Base):
    """
    An edit to one of the file-based email templates. The newest version overrides the file, so edits survive
    deploys and every change is attributable and can be rolled back.
    """
    __tablename__ = "comm_template_versions"

    version_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_name = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    note = Column(String(255), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("template_name", "version", name="uq_comm_template_versions"),
    )
