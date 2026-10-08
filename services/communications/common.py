"""Constants and helpers shared by the communications services."""
import datetime
import re
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from common.utils import parse_uuid
from models.audit_log import AuditLog

CHANNELS = ("email", "in_app", "whatsapp")
CATEGORIES = ("service", "marketing")
AUDIENCE_TYPES = ("all_users", "customers", "staff", "subscription", "selected_users")

BROADCAST_STATUSES = ("draft", "awaiting_approval", "queued", "sending", "completed", "cancelled", "rejected")
MESSAGE_STATUSES = ("queued", "sending", "sent", "delivered", "failed", "bounced", "complained", "suppressed",
                    "cancelled")
# Statuses after which a message will never be attempted again
FINAL_MESSAGE_STATUSES = ("sent", "delivered", "failed", "bounced", "complained", "suppressed", "cancelled")

PRIORITY_TRANSACTIONAL = 0
PRIORITY_BULK = 5

APPROVAL_THRESHOLD_KEY = "comm_marketing_approval_threshold"
DEFAULT_APPROVAL_THRESHOLD = 500


class CommError(Exception):
    """A communications action was refused; `status_code` is the HTTP status the router should return."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def as_uuid(value) -> Optional[uuid.UUID]:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return parse_uuid(value)
    except ValueError:
        raise CommError("Invalid id", 404)


def normalize_destination(channel: str, destination: str) -> str:
    """Email addresses compare case-insensitively; phone numbers as digits only (the form Meta expects)."""
    destination = (destination or "").strip()
    if channel == "email":
        return destination.lower()
    if channel == "whatsapp":
        return re.sub(r"\D", "", destination)
    return destination


def audit(db: Session, actor_id, action: str, entity_type: str, entity_id, details: dict):
    db.add(AuditLog(
        actor_id=as_uuid(actor_id),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        details=details,
    ))


def page_bounds(page: int, limit: int) -> tuple:
    page = max(1, page)
    limit = min(max(1, limit), 200)
    return page, limit, (page - 1) * limit


def paged(items, total: int, page: int, limit: int) -> dict:
    return {"items": items, "total": total, "page": page, "limit": limit}


def iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None
