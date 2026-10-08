"""
The outbox dispatcher. Each pass:
  1. puts back messages whose sender died mid-send (claimed long ago, never finished);
  2. expands due broadcasts into one comm_messages row per recipient and channel;
  3. claims due messages (FOR UPDATE SKIP LOCKED, so several workers never take the same row) and sends them,
     in priority order, retrying rate limits and provider outages with backoff;
  4. refreshes broadcast statistics and completes broadcasts with nothing left to send.

Runs in a daemon thread in every API process (start_comm_dispatcher); passes are safe to run concurrently.
"""
import datetime
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from typing import Callable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from common.config import get_config
from models.communications import CommBroadcast, CommMessage
from models.notification import Notification

from . import rendering
from .audience import resolve
from .common import PRIORITY_BULK, now
from .consent import unsubscribe_token, unsubscribe_url
from .providers import EmailEnvelope, ResendEmailProvider, SendResult, WhatsAppProvider
from .providers.resend import MAX_BATCH

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_DELAYS = (30, 120, 600, 3600)  # seconds to wait after attempt 1, 2, 3, 4
STALE_CLAIM_SECONDS = 15 * 60
EMAIL_BATCH_INTERVAL = float(os.getenv("COMM_EMAIL_BATCH_INTERVAL", "0.6"))  # Resend allows ~2 requests/s


def _locking(query, db: Session):
    """Row locks that skip rows another worker holds; SQLite (tests) has neither and runs one worker."""
    if db.bind.dialect.name == "postgresql":
        return query.with_for_update(skip_locked=True)
    return query


class Dispatcher:
    def __init__(self, db: Session, email_provider=None, whatsapp_provider=None,
                 clock: Callable = now, sleep: Callable = time.sleep):
        self.db = db
        self.email = email_provider or ResendEmailProvider()
        self.whatsapp = whatsapp_provider or WhatsAppProvider()
        self.clock = clock
        self.sleep = sleep

    def run_once(self, message_limit: int = 500) -> dict:
        return {
            "reclaimed": self.reclaim_stale(),
            "broadcasts_started": self.start_due_broadcasts(),
            "messages_processed": self.send_due_messages(message_limit),
            "broadcasts_completed": self.refresh_broadcasts(),
        }

    # --- 1. crash recovery ---

    def reclaim_stale(self) -> int:
        cutoff = self.clock() - datetime.timedelta(seconds=STALE_CLAIM_SECONDS)
        count = (self.db.query(CommMessage)
                 .filter(CommMessage.status == "sending", CommMessage.claimed_at < cutoff)
                 .update({"status": "queued", "claimed_at": None, "next_attempt_at": None}, synchronize_session=False))
        self.db.commit()
        if count:
            logger.warning(f"Re-queued {count} messages left in 'sending' by a stopped worker")
        return count

    # --- 2. broadcast expansion ---

    def start_due_broadcasts(self, limit: int = 5) -> int:
        at = self.clock()
        due = _locking(self.db.query(CommBroadcast).filter(
            CommBroadcast.status == "queued",
            or_(CommBroadcast.scheduled_for.is_(None), CommBroadcast.scheduled_for <= at),
        ).order_by(CommBroadcast.created_at).limit(limit), self.db).all()
        for broadcast in due:
            self._expand(broadcast, at)
            self.db.commit()
        return len(due)

    def _expand(self, broadcast: CommBroadcast, at):
        resolution = resolve(self.db, broadcast.audience, broadcast.channels, broadcast.category)
        marketing = broadcast.category == "marketing"
        rows = []
        for r in resolution.recipients:
            context = rendering.recipient_context(r.first_name, r.last_name, r.email)
            if marketing and r.channel == "email":
                context["unsubscribe_url"] = unsubscribe_url(r.user_id)
                context["unsubscribe_token"] = unsubscribe_token(r.user_id)
            rows.append({
                "broadcast_id": broadcast.broadcast_id, "user_id": r.user_id, "channel": r.channel,
                "destination": r.destination, "category": broadcast.category, "priority": PRIORITY_BULK,
                "subject": (broadcast.content.get("email") or {}).get("subject") if r.channel == "email" else None,
                "context": context, "status": "queued", "attempts": 0, "created_at": at, "updated_at": at,
            })
        for start in range(0, len(rows), 1000):
            self.db.bulk_insert_mappings(CommMessage, rows[start:start + 1000])
        broadcast.status = "sending" if rows else "completed"
        broadcast.started_at = at
        broadcast.completed_at = None if rows else at
        broadcast.recipients_count = resolution.people
        broadcast.stats = {"audience": resolution.summary(), "channels": {}}
        logger.info(f"Broadcast {broadcast.broadcast_id}: {len(rows)} messages to {resolution.people} people")

    # --- 3. sending ---

    def _claim(self, limit: int) -> list:
        at = self.clock()
        messages = _locking(self.db.query(CommMessage).filter(
            CommMessage.status == "queued",
            or_(CommMessage.next_attempt_at.is_(None), CommMessage.next_attempt_at <= at),
        ).order_by(CommMessage.priority, CommMessage.created_at).limit(limit), self.db).all()
        for m in messages:
            m.status, m.claimed_at, m.attempts = "sending", at, (m.attempts or 0) + 1
        self.db.commit()
        return messages

    def send_due_messages(self, limit: int = 500) -> int:
        messages = self._claim(limit)
        if not messages:
            return 0
        broadcast_ids = {m.broadcast_id for m in messages if m.broadcast_id}
        broadcasts = {b.broadcast_id: b for b in self.db.query(CommBroadcast).filter(
            CommBroadcast.broadcast_id.in_(broadcast_ids))} if broadcast_ids else {}

        by_channel = defaultdict(list)
        for m in messages:
            broadcast = broadcasts.get(m.broadcast_id)
            if broadcast is None:
                self._finish(m, SendResult(ok=False, provider="none", error="Message has no content to send"))
            elif broadcast.status == "cancelled":
                m.status, m.claimed_at = "cancelled", None
            else:
                by_channel[m.channel].append((m, broadcast))
        self.db.commit()

        self._send_in_app(by_channel.pop("in_app", []))
        self._send_email(by_channel.pop("email", []))
        self._send_whatsapp(by_channel.pop("whatsapp", []))
        return len(messages)

    def _finish(self, message: CommMessage, result: SendResult):
        at = self.clock()
        message.provider = result.provider
        message.claimed_at = None
        if result.ok:
            message.status, message.sent_at, message.error = "sent", at, None
            message.provider_message_id = result.provider_message_id
        elif result.retryable and message.attempts < MAX_ATTEMPTS:
            delay = RETRY_DELAYS[min(message.attempts, len(RETRY_DELAYS)) - 1]
            message.status, message.error = "queued", result.error
            message.next_attempt_at = at + datetime.timedelta(seconds=delay)
        else:
            message.status, message.error = "failed", result.error

    def _send_in_app(self, items: list):
        for m, broadcast in items:
            content = broadcast.content.get("in_app") or rendering.default_in_app(broadcast.content.get("email"))
            title, body = rendering.render_in_app(content, m.context or {})
            notification_id = str(uuid.uuid4())
            self.db.add(Notification(notification_id=notification_id, user_id=m.user_id, title=title, message=body,
                                     type="admin_broadcast", related_entity_id=str(broadcast.broadcast_id),
                                     is_read=False))
            self._finish(m, SendResult(ok=True, provider="in_app", provider_message_id=notification_id))
        self.db.commit()

    def _send_email(self, items: list):
        api_url = get_config().PUBLIC_API_URL.rstrip("/")
        for start in range(0, len(items), MAX_BATCH):
            chunk = items[start:start + MAX_BATCH]
            envelopes = []
            for m, broadcast in chunk:
                context = m.context or {}
                subject, page = rendering.render_email(broadcast.content["email"], context)
                headers = {}
                if context.get("unsubscribe_token") and api_url:
                    # RFC 8058 one-click: mail providers POST here directly
                    headers = {
                        "List-Unsubscribe": f"<{api_url}/communications/unsubscribe?token={context['unsubscribe_token']}>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    }
                text = rendering.html_to_text(rendering.personalize(broadcast.content["email"]["html"], context, False))
                envelopes.append(EmailEnvelope(message_id=str(m.message_id), to=m.destination, subject=subject,
                                               html=page, text=text, headers=headers))
            for (m, _), result in zip(chunk, self.email.send_batch(envelopes)):
                self._finish(m, result)
            self._heartbeat(items[start + MAX_BATCH:])
            self.db.commit()
            if start + MAX_BATCH < len(items):
                self.sleep(EMAIL_BATCH_INTERVAL)

    def _send_whatsapp(self, items: list):
        for i, (m, broadcast) in enumerate(items):
            content = broadcast.content["whatsapp"]
            params = rendering.render_whatsapp_params(content, m.context or {})
            self._finish(m, self.whatsapp.send_template(m.destination, content["template"], content["language"], params))
            if i % 20 == 19:
                self._heartbeat(items[i + 1:])
            self.db.commit()

    def _heartbeat(self, remaining: list):
        """Renews the claim on messages still waiting in this pass, so a slow provider isn't mistaken for a dead worker."""
        at = self.clock()
        for m, _ in remaining:
            if m.status == "sending":
                m.claimed_at = at

    # --- 4. progress ---

    def refresh_broadcasts(self) -> int:
        """Recounts message statuses for broadcasts in flight; completes those with nothing queued or sending."""
        completed = 0
        for broadcast in self.db.query(CommBroadcast).filter(CommBroadcast.status.in_(("sending", "cancelled"))).all():
            counts = message_counts(self.db, broadcast.broadcast_id)
            stats = dict(broadcast.stats or {})
            stats["channels"] = counts
            broadcast.stats = stats
            pending = sum(c.get("queued", 0) + c.get("sending", 0) for c in counts.values())
            if broadcast.status == "sending" and not pending:
                broadcast.status, broadcast.completed_at = "completed", self.clock()
                completed += 1
        self.db.commit()
        return completed


def message_counts(db: Session, broadcast_id) -> dict:
    """{channel: {status: count}} for one broadcast."""
    return message_counts_for(db, [broadcast_id]).get(broadcast_id, {})


def message_counts_for(db: Session, broadcast_ids: list) -> dict:
    """{broadcast_id: {channel: {status: count}}} in one query."""
    counts: dict = {}
    if not broadcast_ids:
        return counts
    for broadcast_id, channel, status, n in (
        db.query(CommMessage.broadcast_id, CommMessage.channel, CommMessage.status, func.count())
        .filter(CommMessage.broadcast_id.in_(broadcast_ids))
        .group_by(CommMessage.broadcast_id, CommMessage.channel, CommMessage.status)
    ):
        counts.setdefault(broadcast_id, {}).setdefault(channel, {})[status] = n
    return counts


# --- background worker ---

_started = False


def _loop(interval: float):
    from common.database import SessionLocal
    while True:
        db = SessionLocal()
        try:
            result = Dispatcher(db).run_once()
            busy = result["messages_processed"] or result["broadcasts_started"]
        except Exception as e:
            db.rollback()
            logger.error(f"Communications dispatcher error: {e}", exc_info=True)
            busy = False
        finally:
            db.close()
        if not busy:  # keep draining while there is work, otherwise poll
            time.sleep(interval)


def start_comm_dispatcher(interval: Optional[float] = None):
    global _started
    if _started or os.getenv("COMM_DISPATCHER_ENABLED", "true").lower() != "true":
        return
    _started = True
    interval = interval or float(os.getenv("COMM_DISPATCH_INTERVAL", "5"))
    threading.Thread(target=_loop, args=(interval,), daemon=True, name="comm-dispatcher").start()
    logger.info("Communications dispatcher started.")
