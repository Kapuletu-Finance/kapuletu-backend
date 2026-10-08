"""
Broadcast lifecycle and reporting.

Marketing broadcasts that would reach more people than the approval threshold (system config
comm_marketing_approval_threshold, default 500) wait for a second employee with manage_communications.
"""
import datetime
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from common.system_config_service import get_system_config
from models.communications import CommBroadcast, CommMessage, CommSuppression
from models.users import User

from . import rendering
from .audience import resolve, validate_audience
from .common import (
    APPROVAL_THRESHOLD_KEY,
    BROADCAST_STATUSES,
    CATEGORIES,
    CHANNELS,
    DEFAULT_APPROVAL_THRESHOLD,
    MESSAGE_STATUSES,
    CommError,
    as_uuid,
    audit,
    iso,
    now,
    page_bounds,
    paged,
)
from .dispatcher import message_counts, message_counts_for


def _name(user: Optional[User]) -> Optional[str]:
    return f"{user.first_name} {user.last_name}".strip() if user else None


class BroadcastService:
    def __init__(self, db: Session):
        self.db = db

    def approval_threshold(self) -> int:
        value = get_system_config(self.db, APPROVAL_THRESHOLD_KEY, DEFAULT_APPROVAL_THRESHOLD)
        try:
            return int(value)
        except (TypeError, ValueError):
            return DEFAULT_APPROVAL_THRESHOLD

    # --- composing ---

    def _target(self, data: dict) -> tuple:
        category = data.get("category", "service")
        if category not in CATEGORIES:
            raise CommError(f"category must be one of {', '.join(CATEGORIES)}")
        channels = list(dict.fromkeys(data.get("channels") or []))
        if not channels or any(c not in CHANNELS for c in channels):
            raise CommError(f"channels must be a non-empty list of {', '.join(CHANNELS)}")
        return category, channels, validate_audience(data.get("audience") or {})

    def _prepare(self, data: dict) -> dict:
        category, channels, audience = self._target(data)
        content = dict(data.get("content") or {})
        if "in_app" in channels and not content.get("in_app") and content.get("email"):
            # No separate in-app copy: use the email's subject and text
            content["in_app"] = rendering.default_in_app(rendering.validate_content(["email"], content)["email"])
        return {
            "category": category,
            "channels": channels,
            "audience": audience,
            "content": rendering.validate_content(channels, content),
        }

    def estimate(self, data: dict) -> dict:
        """Reach for an audience, category and channels; content is not needed yet."""
        category, channels, audience = self._target(data)
        summary = resolve(self.db, audience, channels, category).summary()
        threshold = self.approval_threshold()
        summary["needs_approval"] = category == "marketing" and summary["reachable_people"] > threshold
        summary["approval_threshold"] = threshold
        return summary

    def create(self, data: dict, actor_id) -> dict:
        title = (data.get("title") or "").strip()
        if not title or len(title) > 255:
            raise CommError("title is required (at most 255 characters)")
        prepared = self._prepare(data)
        scheduled_for = data.get("scheduled_for")
        if scheduled_for and scheduled_for.tzinfo:
            scheduled_for = scheduled_for.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        if scheduled_for and scheduled_for < now() - datetime.timedelta(minutes=1):
            raise CommError("scheduled_for is in the past")

        reach = resolve(self.db, prepared["audience"], prepared["channels"], prepared["category"])
        if not reach.recipients:
            raise CommError("Nobody in this audience can receive this broadcast on the chosen channels")
        threshold = self.approval_threshold()
        needs_approval = prepared["category"] == "marketing" and reach.people > threshold

        broadcast = CommBroadcast(
            title=title, created_by=as_uuid(actor_id), scheduled_for=scheduled_for,
            status="awaiting_approval" if needs_approval else "queued",
            recipients_count=reach.people, stats={"audience": reach.summary(), "channels": {}},
            **prepared,
        )
        self.db.add(broadcast)
        self.db.flush()
        audit(self.db, actor_id, "BROADCAST_CREATED", "BROADCAST", broadcast.broadcast_id, {
            "title": title, "category": broadcast.category, "channels": broadcast.channels,
            "audience": broadcast.audience, "estimated_people": reach.people, "needs_approval": needs_approval,
        })
        self.db.commit()
        return self.get(broadcast.broadcast_id)

    # --- decisions ---

    def _load(self, broadcast_id) -> CommBroadcast:
        broadcast = self.db.get(CommBroadcast, as_uuid(broadcast_id))
        if not broadcast:
            raise CommError("Broadcast not found", 404)
        return broadcast

    def approve(self, broadcast_id, actor_id, note: Optional[str] = None) -> dict:
        broadcast = self._load(broadcast_id)
        if broadcast.status != "awaiting_approval":
            raise CommError("Only broadcasts awaiting approval can be approved", 409)
        if broadcast.created_by and str(broadcast.created_by) == str(actor_id):
            raise CommError("A broadcast must be approved by someone other than its author", 403)
        broadcast.status, broadcast.approved_by, broadcast.decided_at, broadcast.decision_note = \
            "queued", as_uuid(actor_id), now(), note
        audit(self.db, actor_id, "BROADCAST_APPROVED", "BROADCAST", broadcast.broadcast_id, {"note": note})
        self.db.commit()
        return self.get(broadcast.broadcast_id)

    def reject(self, broadcast_id, actor_id, note: Optional[str] = None) -> dict:
        broadcast = self._load(broadcast_id)
        if broadcast.status != "awaiting_approval":
            raise CommError("Only broadcasts awaiting approval can be rejected", 409)
        broadcast.status, broadcast.approved_by, broadcast.decided_at, broadcast.decision_note = \
            "rejected", as_uuid(actor_id), now(), note
        audit(self.db, actor_id, "BROADCAST_REJECTED", "BROADCAST", broadcast.broadcast_id, {"note": note})
        self.db.commit()
        return self.get(broadcast.broadcast_id)

    def cancel(self, broadcast_id, actor_id) -> dict:
        """Stops a broadcast; messages already handed to a provider are not recalled."""
        broadcast = self._load(broadcast_id)
        if broadcast.status not in ("awaiting_approval", "queued", "sending"):
            raise CommError(f"A {broadcast.status} broadcast cannot be cancelled", 409)
        was = broadcast.status
        stopped = (self.db.query(CommMessage)
                   .filter(CommMessage.broadcast_id == broadcast.broadcast_id, CommMessage.status == "queued")
                   .update({"status": "cancelled"}, synchronize_session=False))
        broadcast.status, broadcast.completed_at = "cancelled", now()
        broadcast.stats = {**(broadcast.stats or {}), "channels": message_counts(self.db, broadcast.broadcast_id)}
        audit(self.db, actor_id, "BROADCAST_CANCELLED", "BROADCAST", broadcast.broadcast_id,
              {"previous_status": was, "messages_stopped": stopped})
        self.db.commit()
        return self.get(broadcast.broadcast_id)

    # --- reading ---

    def _row(self, b: CommBroadcast, author: Optional[User], approver: Optional[User]) -> dict:
        return {
            "id": str(b.broadcast_id),
            "title": b.title,
            "category": b.category,
            "status": b.status,
            "audience": b.audience,
            "channels": b.channels,
            "recipients_count": b.recipients_count,
            "stats": b.stats or {},
            "created_by": _name(author),
            "approved_by": _name(approver),
            "decision_note": b.decision_note,
            "scheduled_for": iso(b.scheduled_for),
            "started_at": iso(b.started_at),
            "completed_at": iso(b.completed_at),
            "created_at": iso(b.created_at),
        }

    def list(self, page: int = 1, limit: int = 25, status: Optional[str] = None, q: Optional[str] = None) -> dict:
        page, limit, offset = page_bounds(page, limit)
        author, approver = aliased(User), aliased(User)
        query = (self.db.query(CommBroadcast, author, approver)
                 .outerjoin(author, CommBroadcast.created_by == author.user_id)
                 .outerjoin(approver, CommBroadcast.approved_by == approver.user_id))
        if status:
            if status not in BROADCAST_STATUSES:
                raise CommError(f"status must be one of {', '.join(BROADCAST_STATUSES)}")
            query = query.filter(CommBroadcast.status == status)
        if q:
            query = query.filter(CommBroadcast.title.ilike(f"%{q.strip()}%"))
        total = query.count()
        rows = query.order_by(CommBroadcast.created_at.desc()).offset(offset).limit(limit).all()
        counts = message_counts_for(self.db, [b.broadcast_id for b, _, _ in rows])
        items = []
        for b, a, p in rows:
            row = self._row(b, a, p)
            row["stats"] = {**row["stats"], "channels": counts.get(b.broadcast_id, {})}
            items.append(row)
        return paged(items, total, page, limit)

    def get(self, broadcast_id) -> dict:
        b = self._load(broadcast_id)
        out = self._row(b, self.db.get(User, b.created_by) if b.created_by else None,
                        self.db.get(User, b.approved_by) if b.approved_by else None)
        out["content"] = b.content
        out["stats"] = {**(b.stats or {}), "channels": message_counts(self.db, b.broadcast_id)}
        return out

    def messages(self, broadcast_id=None, page: int = 1, limit: int = 50, channel: Optional[str] = None,
                 status: Optional[str] = None, q: Optional[str] = None) -> dict:
        """The delivery log: every message, or one broadcast's."""
        page, limit, offset = page_bounds(page, limit)
        query = (self.db.query(CommMessage, User, CommBroadcast.title)
                 .outerjoin(User, CommMessage.user_id == User.user_id)
                 .outerjoin(CommBroadcast, CommMessage.broadcast_id == CommBroadcast.broadcast_id))
        if broadcast_id:
            query = query.filter(CommMessage.broadcast_id == self._load(broadcast_id).broadcast_id)
        if channel:
            if channel not in CHANNELS:
                raise CommError(f"channel must be one of {', '.join(CHANNELS)}")
            query = query.filter(CommMessage.channel == channel)
        if status:
            if status not in MESSAGE_STATUSES:
                raise CommError(f"status must be one of {', '.join(MESSAGE_STATUSES)}")
            query = query.filter(CommMessage.status == status)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(or_(CommMessage.destination.ilike(like), User.first_name.ilike(like),
                                     User.last_name.ilike(like), CommMessage.subject.ilike(like)))
        total = query.count()
        rows = query.order_by(CommMessage.created_at.desc()).offset(offset).limit(limit).all()
        return paged([{
            "id": str(m.message_id),
            "broadcast_id": str(m.broadcast_id) if m.broadcast_id else None,
            "broadcast_title": title,
            "recipient": _name(u) or "Former user",
            "user_id": str(m.user_id) if m.user_id else None,
            "channel": m.channel,
            "destination": m.destination,
            "category": m.category,
            "subject": m.subject,
            "status": m.status,
            "attempts": m.attempts,
            "error": m.error,
            "next_attempt_at": iso(m.next_attempt_at),
            "sent_at": iso(m.sent_at),
            "created_at": iso(m.created_at),
        } for m, u, title in rows], total, page, limit)

    def overview(self, days: int = 30) -> dict:
        since = now() - datetime.timedelta(days=days)
        statuses = dict(self.db.query(CommBroadcast.status, func.count()).group_by(CommBroadcast.status).all())
        by_channel: dict = {}
        for channel, status, n in (self.db.query(CommMessage.channel, CommMessage.status, func.count())
                                   .filter(CommMessage.created_at >= since)
                                   .group_by(CommMessage.channel, CommMessage.status)):
            by_channel.setdefault(channel, {})[status] = n
        return {
            "period_days": days,
            "broadcasts_sent": self.db.query(func.count(CommBroadcast.broadcast_id)).filter(
                CommBroadcast.started_at >= since).scalar() or 0,
            "awaiting_approval": statuses.get("awaiting_approval", 0),
            "in_flight": statuses.get("queued", 0) + statuses.get("sending", 0),
            "messages": by_channel,
            "suppressions": self.db.query(func.count(CommSuppression.suppression_id)).scalar() or 0,
            "approval_threshold": self.approval_threshold(),
        }
