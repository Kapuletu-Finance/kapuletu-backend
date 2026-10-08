"""
Turns an audience definition into the people and destinations a broadcast may reach.

Audience types:
  all_users       every active account (customers and staff)
  customers       treasurers
  staff           internal employees
  subscription    customers whose subscription is in one of `states` (paid, trial, comp, lapsed, free),
                  classified the same way as the finance dashboard
  selected_users  `user_ids`; only registered users, so we never mail addresses that gave us no consent

Marketing email and WhatsApp need marketing consent; in-app messages are shown inside the product and don't.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from common.enums import UserRole
from models.subscription import Plan, Subscription
from models.users import User
from services.admin.finance.subscriptions import STATES as SUBSCRIPTION_STATES
from services.admin.finance.subscriptions import _state_filter

from .common import AUDIENCE_TYPES, CHANNELS, CommError, as_uuid, normalize_destination, now
from .consent import suppressed_destinations

SKIP_REASONS = ("no_destination", "no_consent", "suppressed")


@dataclass
class Recipient:
    user_id: object
    first_name: str
    last_name: str
    email: str
    channel: str
    destination: str


@dataclass
class Resolution:
    recipients: List[Recipient] = field(default_factory=list)
    audience_size: int = 0
    skipped: Dict[str, Dict[str, int]] = field(default_factory=dict)  # channel -> reason -> count

    @property
    def people(self) -> int:
        return len({r.user_id for r in self.recipients})

    def summary(self) -> dict:
        per_channel = {}
        for r in self.recipients:
            per_channel[r.channel] = per_channel.get(r.channel, 0) + 1
        return {
            "audience_size": self.audience_size,
            "reachable_people": self.people,
            "channels": {
                channel: {"deliverable": per_channel.get(channel, 0), **self.skipped.get(channel, {})}
                for channel in self.skipped
            },
        }


def validate_audience(audience: dict) -> dict:
    kind = (audience or {}).get("type")
    if kind not in AUDIENCE_TYPES:
        raise CommError(f"audience.type must be one of {', '.join(AUDIENCE_TYPES)}")
    if kind == "subscription":
        states = audience.get("states") or []
        if not states or any(s not in SUBSCRIPTION_STATES for s in states):
            raise CommError(f"audience.states must be a non-empty list of {', '.join(SUBSCRIPTION_STATES)}")
        return {"type": kind, "states": sorted(set(states))}
    if kind == "selected_users":
        user_ids = audience.get("user_ids") or []
        if not user_ids:
            raise CommError("audience.user_ids must list at least one user")
        return {"type": kind, "user_ids": sorted({str(as_uuid(u)) for u in user_ids})}
    return {"type": kind}


def _users_query(db: Session, audience: dict):
    query = db.query(User.user_id, User.first_name, User.last_name, User.email, User.phone_number,
                     User.marketing_consent).filter(
        User.is_active.is_(True), User.deleted_at.is_(None), User.is_waitlisted.isnot(True),
    )
    kind = audience["type"]
    if kind == "customers":
        query = query.filter(User.role == UserRole.TREASURER.value)
    elif kind == "staff":
        query = query.filter(User.role != UserRole.TREASURER.value)
    elif kind == "subscription":
        at = now()
        subscribed = (
            db.query(Subscription.user_id)
            .join(Plan, Subscription.plan_id == Plan.plan_id)
            .filter(or_(*[_state_filter(s, at) for s in audience["states"]]))
        )
        query = query.filter(User.role == UserRole.TREASURER.value, User.user_id.in_(subscribed))
    elif kind == "selected_users":
        query = query.filter(User.user_id.in_([as_uuid(u) for u in audience["user_ids"]]))
    return query


def resolve(db: Session, audience: dict, channels: List[str], category: str) -> Resolution:
    audience = validate_audience(audience)
    users = _users_query(db, audience).all()
    result = Resolution(audience_size=len(users))

    for channel in channels:
        if channel not in CHANNELS:
            raise CommError(f"Unknown channel {channel}")
        skipped = {reason: 0 for reason in SKIP_REASONS}
        candidates = []
        for u in users:
            if channel == "in_app":
                destination = str(u.user_id)
            else:
                destination = normalize_destination(channel, u.email if channel == "email" else u.phone_number)
            if not destination:
                skipped["no_destination"] += 1
            elif category == "marketing" and channel != "in_app" and not u.marketing_consent:
                skipped["no_consent"] += 1
            else:
                candidates.append((u, destination))

        blocked = set()
        if channel != "in_app":
            blocked = suppressed_destinations(db, channel, category, [d for _, d in candidates])
        seen = set()
        for u, destination in candidates:
            if destination in blocked:
                skipped["suppressed"] += 1
            elif destination not in seen:  # two accounts sharing an address get one message
                seen.add(destination)
                result.recipients.append(Recipient(u.user_id, u.first_name or "", u.last_name or "", u.email or "",
                                                   channel, destination))
        result.skipped[channel] = skipped
    return result
