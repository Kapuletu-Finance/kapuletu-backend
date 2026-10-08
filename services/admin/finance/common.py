"""Helpers shared by the admin finance services."""
import datetime
import uuid
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from common.utils import parse_uuid
from models.audit_log import AuditLog
from models.subscription import Plan
from models.users import User


class FinanceError(Exception):
    """A finance action was refused; `status_code` is the HTTP status the router should return."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def as_uuid(value) -> Optional[uuid.UUID]:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return parse_uuid(value)


def jsonable(value):
    """Audit details are stored as JSON; money comes out of the database as Decimal."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if hasattr(value, "quantize"):
        return str(value)
    if isinstance(value, (datetime.datetime, uuid.UUID)):
        return str(value)
    return value


def audit(db: Session, actor_id, action: str, entity_type: str, entity_id, details: dict):
    db.add(AuditLog(
        actor_id=as_uuid(actor_id),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        details=jsonable(details),
    ))


def get_plan(db: Session, plan_id) -> Plan:
    try:
        plan = db.get(Plan, as_uuid(plan_id))
    except ValueError:
        plan = None
    if not plan:
        raise FinanceError("Plan not found", 404)
    return plan


def resolve_user(db: Session, identifier: str) -> User:
    """Accepts a user UUID or slug, like the rest of the admin user endpoints."""
    try:
        user = db.get(User, parse_uuid(identifier))
    except ValueError:
        user = db.query(User).filter(User.slug == identifier).first()
    if not user:
        raise FinanceError("User not found", 404)
    return user


def user_name(user: Optional[User]) -> str:
    return f"{user.first_name} {user.last_name}".strip() if user else "Unknown user"


def page_params(page: int, limit: int) -> Tuple[int, int]:
    page = max(1, page)
    limit = min(max(1, limit), 200)
    return (page - 1) * limit, limit


def paged(items, total: int, page: int, limit: int) -> dict:
    return {"items": items, "total": total, "page": page, "limit": limit}


def iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None
