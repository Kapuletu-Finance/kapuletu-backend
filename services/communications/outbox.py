"""
Transactional sending through the outbox: receipts, invites, reminders, reports, support replies, staff alerts.

    queue_email(db, to, subject, body_html, kind="payment_receipt", user_id=...)

writes a priority-0 comm_messages row (ahead of any broadcast) and wakes the dispatcher when the caller's
transaction commits, so mail goes out within a second or two, is retried on provider errors, survives restarts,
gets delivery tracking from webhooks, and shows in the delivery log.

Category decides suppression: "service" mail is not sent to suppressed addresses (hard bounces, manual blocks);
"security" mail (password changes, sign-in codes) always goes out.

Sign-in codes are sent synchronously by the auth service (they need to arrive now and fall back to SMS);
record_sent() puts those sends in the same log, without the code.
"""
import logging
from typing import List, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from models.communications import CommMessage

from .common import PRIORITY_TRANSACTIONAL, CommError, as_uuid, normalize_destination, now
from .consent import suppressed_destinations
from .providers.base import SendResult

logger = logging.getLogger(__name__)

TRANSACTIONAL_CATEGORIES = ("service", "security")


def _wake_dispatcher_after_commit(db: Session) -> None:
    from .dispatcher import wake
    if not db.info.get("comm_wake_registered"):
        db.info["comm_wake_registered"] = True

        def after_commit(session):
            session.info.pop("comm_wake_registered", None)
            wake()

        event.listen(db, "after_commit", after_commit, once=True)


def queue_email(db: Session, to: str, subject: str, body_html: str, *, kind: str, user_id=None,
                category: str = "service", attachments: Optional[List[dict]] = None,
                layout: bool = True) -> CommMessage:
    """
    Queues one email. `body_html` is wrapped in the branded layout unless layout=False. `attachments` are
    Resend attachments ({"filename", "content": base64}). The caller commits; nothing is sent before that.
    """
    if category not in TRANSACTIONAL_CATEGORIES:
        raise CommError(f"category must be one of {', '.join(TRANSACTIONAL_CATEGORIES)}")
    destination = normalize_destination("email", to)
    if not destination or "@" not in destination:
        raise CommError("A valid email address is required")

    status, error = "queued", None
    if category != "security" and suppressed_destinations(db, "email", "service", [destination]):
        status, error = "suppressed", "Address is suppressed (bounced or blocked); not sent"
        logger.info(f"Not sending {kind} email to suppressed address {destination}")

    message = CommMessage(
        broadcast_id=None, user_id=as_uuid(user_id), channel="email", destination=destination, category=category,
        priority=PRIORITY_TRANSACTIONAL, subject=subject[:255], status=status, error=error, attempts=0,
        context={"kind": kind, "html": body_html, "layout": layout, "attachments": attachments or []},
    )
    db.add(message)
    db.flush()
    if status == "queued":
        _wake_dispatcher_after_commit(db)
    return message


def record_sent(db: Session, *, channel: str, destination: str, kind: str, result: SendResult,
                subject: Optional[str] = None, user_id=None, category: str = "security") -> CommMessage:
    """Logs a message that was sent synchronously elsewhere. Never put secrets (codes) in subject."""
    at = now()
    message = CommMessage(
        broadcast_id=None, user_id=as_uuid(user_id), channel=channel,
        destination=normalize_destination(channel, destination) or destination, category=category,
        priority=PRIORITY_TRANSACTIONAL, subject=(subject or "")[:255] or None,
        status="sent" if result.ok else "failed", error=result.error, attempts=1,
        provider=result.provider, provider_message_id=result.provider_message_id,
        sent_at=at if result.ok else None, context={"kind": kind},
    )
    db.add(message)
    db.flush()
    return message
