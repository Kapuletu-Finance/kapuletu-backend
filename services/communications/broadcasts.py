"""
Broadcast lifecycle and reporting.

Marketing broadcasts that would reach more people than the approval threshold (system config
comm_marketing_approval_threshold, default 500) wait for a second employee with manage_communications.
"""
import datetime
import uuid
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from common.system_config_service import get_system_config
from models.communications import CommBroadcast, CommMessage, CommMessageEvent, CommSuppression
from models.notification import Notification
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
    normalize_destination,
    now,
    page_bounds,
    paged,
)
from .dispatcher import email_envelope, engagement_for, message_context, message_counts, message_counts_for
from .providers import ResendEmailProvider, SendResult, WhatsAppProvider
from .providers.whatsapp import approved_templates


def _name(user: Optional[User]) -> Optional[str]:
    return f"{user.first_name} {user.last_name}".strip() if user else None


class BroadcastService:
    def __init__(self, db: Session, email_provider=None, whatsapp_provider=None):
        self.db = db
        self._email_provider = email_provider
        self._whatsapp_provider = whatsapp_provider

    @property
    def email_provider(self):
        return self._email_provider or ResendEmailProvider()

    @property
    def whatsapp_provider(self):
        return self._whatsapp_provider or WhatsAppProvider()

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

    def _title(self, data: dict) -> str:
        title = (data.get("title") or "").strip()
        if not title or len(title) > 255:
            raise CommError("title is required (at most 255 characters)")
        return title

    @staticmethod
    def _when(value) -> Optional[datetime.datetime]:
        if isinstance(value, str):
            try:
                value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise CommError("scheduled_for must be an ISO date and time")
        if value and value.tzinfo:
            value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value

    def _check_whatsapp(self, prepared: dict) -> None:
        """When the Meta catalogue is available, the template must be approved, sendable and fully filled in."""
        if "whatsapp" not in prepared["channels"]:
            return
        wa = prepared["content"]["whatsapp"]
        try:
            catalogue = approved_templates()
        except Exception:
            raise CommError("Couldn't check the WhatsApp template with Meta. Try again in a minute.", 503)
        if catalogue is None:
            return  # not configured: Meta rejects unknown templates at send time
        match = next((t for t in catalogue if t["name"] == wa["template"] and t["language"] == wa["language"]), None)
        if not match:
            raise CommError(f"{wa['template']} ({wa['language']}) is not an approved WhatsApp template")
        if not match["sendable"]:
            raise CommError(f"{wa['template']} can't be broadcast: it {match['unsupported_reason']}")
        if len(wa["params"]) != match["variables"]:
            raise CommError(f"{wa['template']} needs {match['variables']} variable(s); {len(wa['params'])} given")

    def create(self, data: dict, actor_id) -> dict:
        """Creates and submits a broadcast in one step."""
        broadcast = CommBroadcast(title=self._title(data))
        return self._submit(broadcast, data, actor_id)

    def _submit(self, broadcast: CommBroadcast, data: dict, actor_id) -> dict:
        prepared = self._prepare(data)
        self._check_whatsapp(prepared)
        scheduled_for = self._when(data.get("scheduled_for"))
        if scheduled_for and scheduled_for < now() - datetime.timedelta(minutes=1):
            raise CommError("The scheduled time is in the past")

        reach = resolve(self.db, prepared["audience"], prepared["channels"], prepared["category"])
        if not reach.recipients:
            raise CommError("Nobody in this audience can receive this broadcast on the chosen channels")
        threshold = self.approval_threshold()
        needs_approval = prepared["category"] == "marketing" and reach.people > threshold

        for key, value in prepared.items():
            setattr(broadcast, key, value)
        # Whoever submits is the author the approval rule is checked against
        broadcast.created_by = as_uuid(actor_id)
        broadcast.status = "awaiting_approval" if needs_approval else "queued"
        broadcast.scheduled_for = scheduled_for
        broadcast.approved_by = broadcast.decided_at = broadcast.decision_note = None
        broadcast.recipients_count = reach.people
        broadcast.stats = {"audience": reach.summary(), "channels": {}}
        self.db.add(broadcast)
        self.db.flush()
        audit(self.db, actor_id, "BROADCAST_CREATED", "BROADCAST", broadcast.broadcast_id, {
            "title": broadcast.title, "category": broadcast.category, "channels": broadcast.channels,
            "audience": broadcast.audience, "estimated_people": reach.people, "needs_approval": needs_approval,
            "scheduled_for": iso(scheduled_for),
        })
        self.db.commit()
        return self.get(broadcast.broadcast_id)

    # --- drafts ---

    def _draft(self, broadcast_id) -> CommBroadcast:
        broadcast = self._load(broadcast_id)
        if broadcast.status != "draft":
            raise CommError("Only drafts can be changed. Return it to draft first.", 409)
        return broadcast

    def save_draft(self, data: dict, actor_id, broadcast_id=None) -> dict:
        """Saves work in progress; content is only checked when the draft is submitted."""
        category = data.get("category") or "service"
        if category not in CATEGORIES:
            raise CommError(f"category must be one of {', '.join(CATEGORIES)}")
        channels = list(dict.fromkeys(data.get("channels") or []))
        if any(c not in CHANNELS for c in channels):
            raise CommError(f"channels must be from {', '.join(CHANNELS)}")
        broadcast = self._draft(broadcast_id) if broadcast_id else CommBroadcast(
            status="draft", created_by=as_uuid(actor_id), recipients_count=0, stats={})
        broadcast.title = self._title(data)
        broadcast.category = category
        broadcast.channels = channels
        broadcast.audience = data.get("audience") or {"type": "customers"}
        broadcast.content = {k: v for k, v in (data.get("content") or {}).items() if v}
        broadcast.scheduled_for = self._when(data.get("scheduled_for"))
        self.db.add(broadcast)
        self.db.flush()
        if not broadcast_id:
            audit(self.db, actor_id, "BROADCAST_DRAFTED", "BROADCAST", broadcast.broadcast_id, {"title": broadcast.title})
        self.db.commit()
        return self.get(broadcast.broadcast_id)

    def submit(self, broadcast_id, actor_id) -> dict:
        broadcast = self._draft(broadcast_id)
        data = {"category": broadcast.category, "channels": broadcast.channels, "audience": broadcast.audience,
                "content": broadcast.content, "scheduled_for": broadcast.scheduled_for}
        return self._submit(broadcast, data, actor_id)

    def delete_draft(self, broadcast_id, actor_id) -> None:
        broadcast = self._draft(broadcast_id)
        audit(self.db, actor_id, "BROADCAST_DRAFT_DELETED", "BROADCAST", broadcast.broadcast_id, {"title": broadcast.title})
        self.db.delete(broadcast)
        self.db.commit()

    def duplicate(self, broadcast_id, actor_id) -> dict:
        """A new draft with the same audience, channels and content, for re-sending or a follow-up."""
        source = self._load(broadcast_id)
        # Pre-revamp audiences can't be resolved; the copy starts from all customers instead
        audience = {"type": "customers"} if source.audience.get("type") == "legacy" else source.audience
        copy = CommBroadcast(
            title=f"Copy of {source.title}"[:255], category=source.category, status="draft",
            audience=audience, channels=list(source.channels), content=dict(source.content),
            created_by=as_uuid(actor_id), recipients_count=0, stats={},
        )
        self.db.add(copy)
        self.db.flush()
        audit(self.db, actor_id, "BROADCAST_DUPLICATED", "BROADCAST", copy.broadcast_id,
              {"source": str(source.broadcast_id)})
        self.db.commit()
        return self.get(copy.broadcast_id)

    def return_to_draft(self, broadcast_id, actor_id) -> dict:
        """Pulls a broadcast that hasn't started back for editing. Any approval is void: edits need a fresh one."""
        broadcast = self._load(broadcast_id)
        if broadcast.status not in ("awaiting_approval", "queued", "rejected") or broadcast.started_at:
            raise CommError("Only broadcasts that haven't started sending can go back to draft", 409)
        was = broadcast.status
        broadcast.status = "draft"
        broadcast.approved_by = broadcast.decided_at = None
        audit(self.db, actor_id, "BROADCAST_RETURNED_TO_DRAFT", "BROADCAST", broadcast.broadcast_id,
              {"previous_status": was})
        self.db.commit()
        return self.get(broadcast.broadcast_id)

    # --- test sends ---

    def test_send(self, data: dict, actor_id) -> dict:
        """
        Sends the content, personalised for the person testing, to their own email, WhatsApp and in-app
        inbox, right away. Nothing is queued and the audience is not contacted.
        """
        me = self.db.get(User, as_uuid(actor_id))
        if not me:
            raise CommError("Your account wasn't found", 404)
        channels = list(dict.fromkeys(data.get("channels") or []))
        prepared = self._prepare({**data, "channels": channels, "audience": {"type": "staff"}})
        self._check_whatsapp(prepared)
        content, marketing = prepared["content"], prepared["category"] == "marketing"
        results = {}
        for channel in channels:
            context = message_context(me.user_id, me.first_name, me.last_name, me.email, channel, marketing)
            if channel == "email":
                envelope = email_envelope(f"test-{uuid.uuid4()}", me.email, content["email"], context, "[Test] ")
                result = self.email_provider.send_batch([envelope])[0]
                destination = me.email
            elif channel == "whatsapp":
                destination = normalize_destination("whatsapp", me.phone_number)
                wa = content["whatsapp"]
                result = self.whatsapp_provider.send_template(
                    destination, wa["template"], wa["language"], rendering.render_whatsapp_params(wa, context))
            else:
                title, body = rendering.render_in_app(content["in_app"], context)
                self.db.add(Notification(user_id=me.user_id, title=f"[Test] {title}", message=body,
                                         type="admin_broadcast_test", is_read=False))
                result, destination = SendResult(ok=True, provider="in_app"), "your notifications"
            results[channel] = {"ok": result.ok, "destination": destination, "error": result.error}
        audit(self.db, actor_id, "BROADCAST_TEST_SENT", "BROADCAST", data.get("broadcast_id"),
              {"channels": channels, "results": {c: r["ok"] for c, r in results.items()}})
        self.db.commit()
        return {"results": results}

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
        ids = [b.broadcast_id for b, _, _ in rows]
        counts, engagement = message_counts_for(self.db, ids), engagement_for(self.db, ids)
        items = []
        for b, a, p in rows:
            row = self._row(b, a, p)
            row["stats"] = {**row["stats"], "channels": counts.get(b.broadcast_id, {}),
                            "engagement": engagement.get(b.broadcast_id, {})}
            items.append(row)
        return paged(items, total, page, limit)

    def get(self, broadcast_id) -> dict:
        b = self._load(broadcast_id)
        out = self._row(b, self.db.get(User, b.created_by) if b.created_by else None,
                        self.db.get(User, b.approved_by) if b.approved_by else None)
        out["content"] = b.content
        out["stats"] = {**(b.stats or {}), "channels": message_counts(self.db, b.broadcast_id),
                        "engagement": engagement_for(self.db, [b.broadcast_id]).get(b.broadcast_id, {})}
        if (b.audience or {}).get("type") == "selected_users":
            # Names for the people picker when a draft is reopened
            ids = [as_uuid(u) for u in b.audience.get("user_ids") or []]
            out["audience_people"] = [{
                "user_id": str(u.user_id), "name": _name(u), "email": u.email, "phone_number": u.phone_number,
                "role": u.role, "marketing_consent": bool(u.marketing_consent), "is_active": bool(u.is_active),
            } for u in self.db.query(User).filter(User.user_id.in_(ids)).limit(1000)] if ids else []
        return out

    def _messages_query(self, broadcast_id=None, channel: Optional[str] = None, status: Optional[str] = None,
                        q: Optional[str] = None, since: Optional[datetime.datetime] = None,
                        until: Optional[datetime.datetime] = None, kind: Optional[str] = None):
        query = (self.db.query(CommMessage, User, CommBroadcast.title)
                 .outerjoin(User, CommMessage.user_id == User.user_id)
                 .outerjoin(CommBroadcast, CommMessage.broadcast_id == CommBroadcast.broadcast_id))
        if kind == "broadcast":
            query = query.filter(CommMessage.broadcast_id.isnot(None))
        elif kind == "transactional":
            query = query.filter(CommMessage.broadcast_id.is_(None))
        elif kind:
            raise CommError("kind must be broadcast or transactional")
        if broadcast_id:
            query = query.filter(CommMessage.broadcast_id == self._load(broadcast_id).broadcast_id)
        if channel:
            if channel not in CHANNELS:
                raise CommError(f"channel must be one of {', '.join(CHANNELS)}")
            query = query.filter(CommMessage.channel == channel)
        if status:
            if status == "opened":
                query = query.filter(CommMessage.opened_at.isnot(None))
            elif status == "clicked":
                query = query.filter(CommMessage.clicked_at.isnot(None))
            elif status not in MESSAGE_STATUSES:
                raise CommError(f"status must be one of {', '.join(MESSAGE_STATUSES)}, opened or clicked")
            else:
                query = query.filter(CommMessage.status == status)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(or_(CommMessage.destination.ilike(like), User.first_name.ilike(like),
                                     User.last_name.ilike(like), CommMessage.subject.ilike(like)))
        if since:
            query = query.filter(CommMessage.created_at >= since)
        if until:
            query = query.filter(CommMessage.created_at < until)
        return query.order_by(CommMessage.created_at.desc())

    @staticmethod
    def _message_row(m: CommMessage, u: Optional[User], title: Optional[str]) -> dict:
        return {
            "id": str(m.message_id),
            "broadcast_id": str(m.broadcast_id) if m.broadcast_id else None,
            "broadcast_title": title,
            "recipient": _name(u) or "Former user",
            "user_id": str(m.user_id) if m.user_id else None,
            "channel": m.channel,
            "destination": m.destination,
            "category": m.category,
            # What sort of transactional message (payment_receipt, verification_code...); None for broadcasts
            "kind": (m.context or {}).get("kind") if not m.broadcast_id else None,
            "subject": m.subject,
            "status": m.status,
            "attempts": m.attempts,
            "error": m.error,
            "next_attempt_at": iso(m.next_attempt_at),
            "sent_at": iso(m.sent_at),
            "delivered_at": iso(m.delivered_at),
            "opened_at": iso(m.opened_at),
            "clicked_at": iso(m.clicked_at),
            "created_at": iso(m.created_at),
        }

    def messages(self, broadcast_id=None, page: int = 1, limit: int = 50, channel: Optional[str] = None,
                 status: Optional[str] = None, q: Optional[str] = None, kind: Optional[str] = None) -> dict:
        """The delivery log: every message, or one broadcast's."""
        page, limit, offset = page_bounds(page, limit)
        query = self._messages_query(broadcast_id, channel, status, q, kind=kind)
        total = query.count()
        rows = query.offset(offset).limit(limit).all()
        return paged([self._message_row(m, u, t) for m, u, t in rows], total, page, limit)

    EXPORT_LIMIT = 100_000

    def export_messages(self, broadcast_id=None, channel=None, status=None, q=None, since=None, until=None,
                        kind=None):
        """Delivery log rows for a CSV download, newest first, capped at EXPORT_LIMIT."""
        query = self._messages_query(broadcast_id, channel, status, q, since, until, kind)
        for m, u, t in query.limit(self.EXPORT_LIMIT).yield_per(1000):
            yield self._message_row(m, u, t)

    def message_events(self, message_id) -> dict:
        """One message and everything providers reported about it, oldest first."""
        message = self.db.get(CommMessage, as_uuid(message_id))
        if not message:
            raise CommError("Message not found", 404)
        events = (self.db.query(CommMessageEvent).filter(CommMessageEvent.message_id == message.message_id)
                  .order_by(CommMessageEvent.occurred_at).all())
        user = self.db.get(User, message.user_id) if message.user_id else None
        broadcast = self.db.get(CommBroadcast, message.broadcast_id) if message.broadcast_id else None
        return {
            "message": self._message_row(message, user, broadcast.title if broadcast else None),
            "events": [{"event": e.event, "provider": e.provider, "detail": e.detail,
                        "occurred_at": iso(e.occurred_at)} for e in events],
        }

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
            **self.deliverability(days),
        }

    def deliverability(self, days: int = 30) -> dict:
        """
        Per channel over the period: messages handed to a provider, and how many were delivered, opened (or read),
        clicked, bounced, complained about or failed; plus a day-by-day series in Nairobi time.
        Opens are an upper bound: some mail apps (Apple Mail Privacy Protection) open every message.
        """
        since = now() - datetime.timedelta(days=days)
        attempted_statuses = ("sent", "delivered", "failed", "bounced", "complained")
        rates: dict = {}
        for channel, status, total, delivered, opened, clicked in (
            self.db.query(CommMessage.channel, CommMessage.status, func.count(), func.count(CommMessage.delivered_at),
                          func.count(CommMessage.opened_at), func.count(CommMessage.clicked_at))
            .filter(CommMessage.created_at >= since, CommMessage.status.in_(attempted_statuses),
                    CommMessage.channel != "in_app")
            .group_by(CommMessage.channel, CommMessage.status)
        ):
            r = rates.setdefault(channel, {"attempted": 0, "delivered": 0, "opened": 0, "clicked": 0, "bounced": 0,
                                           "complained": 0, "failed": 0})
            r["attempted"] += total
            r["delivered"] += delivered
            r["opened"] += opened
            r["clicked"] += clicked
            if status in ("bounced", "complained", "failed"):
                r[status] += total

        # Daily buckets in East Africa Time, zero-filled
        eat = datetime.timedelta(hours=3)
        first_day = (since + eat).date()
        series = {first_day + datetime.timedelta(days=i): {"attempted": 0, "delivered": 0, "failed": 0}
                  for i in range(days + 1)}
        for created_at, status, delivered_at in (
            self.db.query(CommMessage.created_at, CommMessage.status, CommMessage.delivered_at)
            .filter(CommMessage.created_at >= since, CommMessage.status.in_(attempted_statuses),
                    CommMessage.channel != "in_app")
            .yield_per(5000)
        ):
            day = series.get((created_at + eat).date())
            if day is None:
                continue
            day["attempted"] += 1
            day["delivered"] += 1 if delivered_at else 0
            day["failed"] += 1 if status in ("failed", "bounced") else 0

        tracked = {p for (p,) in self.db.query(CommMessageEvent.provider).filter(
            CommMessageEvent.occurred_at >= since).distinct()}
        return {
            "deliverability": rates,
            "daily": [{"date": d.isoformat(), **v} for d, v in sorted(series.items())],
            "tracking": {"email": "resend" in tracked, "whatsapp": "meta_whatsapp" in tracked},
        }
