"""
Who may be messaged: marketing consent, the suppression list and signed unsubscribe links.

Marketing needs users.marketing_consent and no marketing or global suppression of the destination.
Service messages only respect global ("all") suppressions, e.g. hard bounces and manual blocks.
"""
import base64
import hashlib
import hmac
import json
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from common.config import get_config
from models.communications import CommSuppression
from models.users import User
from models.whatsapp_blocklist import WhatsAppBlocklist

from .common import CHANNELS, CommError, as_uuid, audit, normalize_destination

SUPPRESSION_REASONS = ("unsubscribed", "hard_bounce", "complaint", "manual")
_TOKEN_PURPOSE = b"kapuletu-unsubscribe-v1"


# --- unsubscribe tokens ---

def _signature(payload: bytes) -> str:
    key = hashlib.sha256(_TOKEN_PURPOSE + get_config().JWT_SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(hmac.new(key, payload, hashlib.sha256).digest()[:18]).decode().rstrip("=")


def unsubscribe_token(user_id, category: str = "marketing") -> str:
    """A link token that never expires: an old email's unsubscribe link must keep working."""
    payload = json.dumps({"u": str(user_id), "c": category}, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{body}.{_signature(payload)}"


def read_unsubscribe_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if not hmac.compare_digest(signature, _signature(payload)):
            raise ValueError
        data = json.loads(payload)
        return {"user_id": data["u"], "category": data["c"]}
    except (ValueError, KeyError, TypeError):
        raise CommError("This unsubscribe link is invalid", 400)


def unsubscribe_url(user_id, category: str = "marketing") -> str:
    return f"{get_config().FRONTEND_URL.rstrip('/')}/unsubscribe?token={unsubscribe_token(user_id, category)}"


# --- suppression list ---

def suppressed_destinations(db: Session, channel: str, category: str, destinations: Iterable[str]) -> set:
    """The subset of `destinations` (already normalised) that must not receive a `category` message."""
    destinations = list(set(destinations))
    if not destinations:
        return set()
    categories = ["all", "marketing"] if category == "marketing" else ["all"]
    blocked = set()
    for start in range(0, len(destinations), 1000):
        chunk = destinations[start:start + 1000]
        blocked.update(d for (d,) in db.query(CommSuppression.destination).filter(
            CommSuppression.channel == channel,
            CommSuppression.category.in_(categories),
            CommSuppression.destination.in_(chunk),
        ))
    if channel == "whatsapp":
        # Numbers blocked for abusing the inbound WhatsApp bot
        wanted = set(destinations)
        blocked.update(p for p in (
            normalize_destination("whatsapp", p)
            for (p,) in db.query(WhatsAppBlocklist.phone_number).filter(WhatsAppBlocklist.is_blocked.is_(True))
        ) if p in wanted)
    return blocked


def add_suppression(db: Session, channel: str, destination: str, reason: str, category: str = "all",
                    note: Optional[str] = None, user_id=None, actor_id=None) -> CommSuppression:
    if channel not in CHANNELS or channel == "in_app":
        raise CommError("channel must be email or whatsapp")
    if reason not in SUPPRESSION_REASONS:
        raise CommError(f"reason must be one of {', '.join(SUPPRESSION_REASONS)}")
    if category not in ("all", "marketing"):
        raise CommError("category must be all or marketing")
    destination = normalize_destination(channel, destination)
    if not destination:
        raise CommError("destination is required")
    existing = db.query(CommSuppression).filter_by(channel=channel, destination=destination, category=category).first()
    if existing:
        return existing
    row = CommSuppression(channel=channel, destination=destination, category=category, reason=reason, note=note,
                          user_id=as_uuid(user_id), created_by=as_uuid(actor_id))
    db.add(row)
    db.flush()
    return row


def unsubscribe(db: Session, token: str) -> dict:
    """One-click unsubscribe from marketing: clears consent and suppresses the user's email and WhatsApp."""
    data = read_unsubscribe_token(token)
    user = db.get(User, as_uuid(data["user_id"]))
    if not user:
        raise CommError("This unsubscribe link is invalid", 400)
    already = not user.marketing_consent
    user.marketing_consent = False
    if user.email:
        add_suppression(db, "email", user.email, "unsubscribed", category="marketing", user_id=user.user_id)
    if user.phone_number:
        add_suppression(db, "whatsapp", user.phone_number, "unsubscribed", category="marketing", user_id=user.user_id)
    if not already:
        audit(db, user.user_id, "MARKETING_UNSUBSCRIBED", "USER", user.user_id, {"via": "unsubscribe_link"})
    db.commit()
    return {"status": "unsubscribed", "email": mask_email(user.email)}


def mask_email(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return f"{local[:2]}{'*' * max(1, len(local) - 2)}@{domain}"


def list_suppressions(db: Session, page: int = 1, limit: int = 50, channel: Optional[str] = None,
                      q: Optional[str] = None) -> dict:
    from .common import iso, page_bounds, paged
    page, limit, offset = page_bounds(page, limit)
    query = db.query(CommSuppression)
    if channel:
        query = query.filter(CommSuppression.channel == channel)
    if q:
        query = query.filter(CommSuppression.destination.ilike(f"%{q.strip().lower()}%"))
    total = query.count()
    rows = query.order_by(CommSuppression.created_at.desc()).offset(offset).limit(limit).all()
    return paged([{
        "id": str(s.suppression_id), "channel": s.channel, "destination": s.destination, "category": s.category,
        "reason": s.reason, "note": s.note, "created_at": iso(s.created_at),
    } for s in rows], total, page, limit)


def remove_suppression(db: Session, suppression_id, actor_id) -> None:
    row = db.get(CommSuppression, as_uuid(suppression_id))
    if not row:
        raise CommError("Suppression not found", 404)
    if row.reason in ("unsubscribed", "complaint"):
        # The person asked us to stop; only they can opt back in (account settings / sign-up consent)
        raise CommError("Unsubscribes and spam complaints can only be reversed by the person themselves", 409)
    audit(db, actor_id, "SUPPRESSION_REMOVED", "SUPPRESSION", row.suppression_id,
          {"channel": row.channel, "destination": row.destination, "reason": row.reason})
    db.delete(row)
    db.commit()
