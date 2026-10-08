"""
Delivery events from provider webhooks: verification, normalisation, and their effect on messages.

Each provider event is stored once (provider + event id), so a redelivered webhook changes nothing.
Message status only moves forward (sent -> delivered -> bounced / complained / failed), whatever order the
events arrive in; opens, clicks and WhatsApp reads are recorded as first-seen times.

Side effects, applied by address even for mail sent outside the outbox:
  hard bounce                      -> suppress email for everything
  spam complaint                   -> suppress marketing email
  WhatsApp 131050 (opted out)      -> suppress marketing WhatsApp
"""
import base64
import datetime
import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.communications import CommMessage, CommMessageEvent

from .common import CommError, normalize_destination
from .consent import add_suppression

logger = logging.getLogger(__name__)

# How far each event moves a message along; it never moves back
STATUS_FOR_EVENT = {"sent": "sent", "delivered": "delivered", "opened": "delivered", "clicked": "delivered",
                    "failed": "failed", "bounced": "bounced", "complained": "complained"}
STATUS_RANK = {"queued": 0, "sending": 0, "sent": 1, "delivered": 2, "failed": 3, "bounced": 3, "complained": 4}

WHATSAPP_MARKETING_OPT_OUT = 131050
SIGNATURE_TOLERANCE_SECONDS = 5 * 60


@dataclass
class DeliveryEvent:
    provider: str
    provider_event_id: str
    provider_message_id: Optional[str]
    event: str
    destination: Optional[str]
    occurred_at: datetime.datetime
    detail: Optional[str] = None
    payload: Optional[dict] = None
    suppress: Optional[tuple] = None  # (channel, category, reason) to add for the destination


# --- applying events ---

def apply_event(db: Session, e: DeliveryEvent) -> bool:
    """Records the event and updates its message; False when this event was already processed."""
    message = None
    if e.provider_message_id:
        message = db.query(CommMessage).filter(CommMessage.provider_message_id == e.provider_message_id).first()
    row = CommMessageEvent(
        message_id=message.message_id if message else None, provider=e.provider,
        provider_event_id=e.provider_event_id, provider_message_id=e.provider_message_id, event=e.event,
        destination=e.destination, detail=(e.detail or None) and e.detail[:2000], payload=e.payload,
        occurred_at=e.occurred_at,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return False  # duplicate delivery of the same event

    if message:
        _update_message(message, e)
    if e.suppress and e.destination:
        channel, category, reason = e.suppress
        add_suppression(db, channel, e.destination, reason, category=category,
                        note=f"Automatic: {e.event} reported by {e.provider}"
                             + (f" ({e.detail[:200]})" if e.detail else ""),
                        user_id=message.user_id if message else None)
    return True


def _update_message(message: CommMessage, e: DeliveryEvent) -> None:
    new_status = STATUS_FOR_EVENT.get(e.event)
    if new_status and STATUS_RANK.get(new_status, 0) > STATUS_RANK.get(message.status, 0):
        message.status = new_status
        if new_status in ("failed", "bounced"):
            message.error = e.detail or e.event
    # Events can arrive out of order; keep the earliest time for each milestone. An open or click implies delivery.
    if e.event in ("delivered", "opened", "clicked"):
        message.delivered_at = _earliest(message.delivered_at, e.occurred_at)
    if e.event in ("opened", "clicked"):
        message.opened_at = _earliest(message.opened_at, e.occurred_at)
    if e.event == "clicked":
        message.clicked_at = _earliest(message.clicked_at, e.occurred_at)


def _earliest(current: Optional[datetime.datetime], new: datetime.datetime) -> datetime.datetime:
    return min(current, new) if current else new


def apply_events(db: Session, events: List[DeliveryEvent]) -> int:
    applied = sum(apply_event(db, e) for e in events)
    db.commit()
    return applied


# --- Resend (signed with Svix) ---

def verify_resend_signature(body: bytes, headers: dict, secret: Optional[str] = None,
                            now: Optional[datetime.datetime] = None) -> None:
    """Raises CommError unless the request carries a valid, recent Svix signature for RESEND_WEBHOOK_SECRET."""
    secret = secret or os.environ.get("RESEND_WEBHOOK_SECRET")
    if not secret:
        raise CommError("Resend webhooks are not configured (RESEND_WEBHOOK_SECRET)", 503)
    headers = {k.lower(): v for k, v in headers.items()}
    msg_id, timestamp, signatures = headers.get("svix-id"), headers.get("svix-timestamp"), headers.get("svix-signature")
    if not (msg_id and timestamp and signatures):
        raise CommError("Missing webhook signature", 401)
    try:
        sent_at = int(timestamp)
    except ValueError:
        raise CommError("Invalid webhook timestamp", 401)
    current = (now or datetime.datetime.now(datetime.timezone.utc)).timestamp()
    if abs(current - sent_at) > SIGNATURE_TOLERANCE_SECONDS:
        raise CommError("Webhook timestamp is too old or in the future", 401)
    key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    expected = base64.b64encode(
        hmac.new(key, f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()).decode()
    for candidate in signatures.split():
        version, _, value = candidate.partition(",")
        if version == "v1" and hmac.compare_digest(value, expected):
            return
    raise CommError("Invalid webhook signature", 401)


def _parse_time(value: Optional[str]) -> datetime.datetime:
    if value:
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            pass
    return datetime.datetime.utcnow()


def resend_event(payload: dict, event_id: str) -> Optional[DeliveryEvent]:
    """Normalises one Resend webhook; None for event types we don't track."""
    kind = (payload.get("type") or "").removeprefix("email.")
    data = payload.get("data") or {}
    to = data.get("to") or []
    destination = normalize_destination("email", to[0] if isinstance(to, list) and to else str(to or ""))
    event, detail, suppress = kind, None, None

    if kind == "bounced":
        bounce = data.get("bounce") or {}
        detail = " · ".join(filter(None, [bounce.get("type"), bounce.get("subType"), bounce.get("message")]))
        if (bounce.get("type") or "").lower() == "permanent":
            suppress = ("email", "all", "hard_bounce")
        else:
            event = "soft_bounced"  # temporary: mailbox full, greylisted; the message may still arrive
    elif kind == "complained":
        suppress = ("email", "marketing", "complaint")
    elif kind == "clicked":
        detail = (data.get("click") or {}).get("link")
    elif kind == "delivery_delayed":
        event = "delayed"
    elif kind == "failed":
        detail = (data.get("failed") or {}).get("reason") or data.get("reason")
    elif kind not in ("sent", "delivered", "opened"):
        return None

    return DeliveryEvent(provider="resend", provider_event_id=event_id, provider_message_id=data.get("email_id"),
                         event=event, destination=destination or None,
                         occurred_at=_parse_time(payload.get("created_at") or data.get("created_at")),
                         detail=detail, payload=payload, suppress=suppress)


# --- Meta WhatsApp (signed with the app secret) ---

def verify_meta_signature(body: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)


def whatsapp_events(payload: dict) -> List[DeliveryEvent]:
    """Every status update in a Meta webhook (they can arrive batched across entries and changes)."""
    out = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            for status in (change.get("value") or {}).get("statuses") or []:
                kind, wamid = status.get("status"), status.get("id")
                if kind not in ("sent", "delivered", "read", "failed") or not wamid:
                    continue
                errors = status.get("errors") or [{}]
                code = errors[0].get("code")
                detail = None
                if kind == "failed":
                    message = (errors[0].get("error_data") or {}).get("details") or errors[0].get("message") \
                        or errors[0].get("title")
                    detail = f"Meta error {code}: {message}" if code else message
                try:
                    occurred = datetime.datetime.utcfromtimestamp(int(status.get("timestamp")))
                except (TypeError, ValueError):
                    occurred = datetime.datetime.utcnow()
                out.append(DeliveryEvent(
                    provider="meta_whatsapp", provider_event_id=f"{wamid}:{kind}", provider_message_id=wamid,
                    event="opened" if kind == "read" else kind,
                    destination=normalize_destination("whatsapp", status.get("recipient_id") or ""),
                    occurred_at=occurred, detail=detail, payload=status,
                    suppress=("whatsapp", "marketing", "unsubscribed") if code == WHATSAPP_MARKETING_OPT_OUT else None,
                ))
    return out
