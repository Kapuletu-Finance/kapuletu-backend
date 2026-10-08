"""Subscriptions: filtered list and the lifecycle actions finance can take on one."""
import datetime
import logging
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from models.subscription import Plan, Subscription, SubscriptionPayment
from models.users import User
from services.finance import billing
from services.finance.plans import FREE_PLAN_CODE, get_free_plan

from .common import FinanceError, as_uuid, audit, get_plan, iso, page_params, paged, resolve_user, user_name

logger = logging.getLogger(__name__)

# What a subscription is right now, derived from its columns.
STATES = ("paid", "trial", "comp", "lapsed", "free")


def subscription_state(sub: Subscription, plan: Optional[Plan], now: datetime.datetime) -> str:
    if plan is not None and plan.code == FREE_PLAN_CODE:
        return "free"
    if sub.end_date is not None and sub.end_date < now:
        return "lapsed"  # past its end date, inside the grace period until the daily sweep downgrades it
    if sub.is_trial:
        return "trial"
    if sub.price_id is not None:
        return "paid"
    return "comp"


def _state_filter(state: str, now: datetime.datetime):
    not_free = Plan.code != FREE_PLAN_CODE
    current = or_(Subscription.end_date.is_(None), Subscription.end_date >= now)
    return {
        "free": Plan.code == FREE_PLAN_CODE,
        "lapsed": and_(not_free, Subscription.end_date < now),
        "trial": and_(not_free, current, Subscription.is_trial.is_(True)),
        "paid": and_(not_free, current, Subscription.is_trial.is_(False), Subscription.price_id.isnot(None)),
        "comp": and_(not_free, current, Subscription.is_trial.is_(False), Subscription.price_id.is_(None)),
    }[state]


class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db

    def _out(self, sub: Subscription, user: User, plan: Plan, now: datetime.datetime) -> dict:
        return {
            "subscription_id": str(sub.subscription_id),
            "user_id": str(sub.user_id),
            "user_name": user_name(user),
            "user_email": user.email if user else None,
            "user_slug": user.slug if user else None,
            "plan_id": str(plan.plan_id) if plan else None,
            "plan_code": plan.code if plan else None,
            "plan_name": plan.name if plan else None,
            "state": subscription_state(sub, plan, now),
            "status": sub.status,
            "is_trial": sub.is_trial,
            "is_auto_renew": sub.is_auto_renew,
            "start_date": iso(sub.start_date),
            "end_date": iso(sub.end_date),
            "days_remaining": max(0, (sub.end_date - now).days) if sub.end_date else None,
        }

    def list(self, state: Optional[str] = None, plan_id: Optional[str] = None,
             renews_before: Optional[datetime.datetime] = None, q: Optional[str] = None,
             page: int = 1, limit: int = 50) -> dict:
        now = datetime.datetime.utcnow()
        query = self.db.query(Subscription, User, Plan).join(User, Subscription.user_id == User.user_id).join(
            Plan, Subscription.plan_id == Plan.plan_id
        )
        if state:
            if state not in STATES:
                raise FinanceError(f"state must be one of {', '.join(STATES)}")
            query = query.filter(_state_filter(state, now))
        if plan_id:
            query = query.filter(Subscription.plan_id == as_uuid(plan_id))
        if renews_before:
            query = query.filter(Subscription.end_date.isnot(None), Subscription.end_date <= renews_before)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(or_(
                User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like),
                User.phone_number.ilike(like), User.slug.ilike(like),
            ))
        total = query.count()
        offset, limit = page_params(page, limit)
        rows = query.order_by(Subscription.end_date.asc().nullslast(), User.first_name.asc()).offset(offset).limit(limit).all()
        return paged([self._out(s, u, p, now) for s, u, p in rows], total, page, limit)

    def state_counts(self) -> dict:
        now = datetime.datetime.utcnow()
        base = self.db.query(func.count(Subscription.subscription_id)).join(Plan, Subscription.plan_id == Plan.plan_id)
        return {state: base.filter(_state_filter(state, now)).scalar() or 0 for state in STATES}

    def _load(self, subscription_id: str):
        sub = self.db.query(Subscription).filter(Subscription.subscription_id == as_uuid(subscription_id)).with_for_update().first()
        if not sub:
            raise FinanceError("Subscription not found", 404)
        return sub

    def _finish(self, sub: Subscription, actor_id, action: str, details: dict):
        audit(self.db, actor_id, action, "SUBSCRIPTION", sub.subscription_id, {"user_id": str(sub.user_id), **details})
        self.db.commit()
        now = datetime.datetime.utcnow()
        return self._out(sub, self.db.get(User, sub.user_id), self.db.get(Plan, sub.plan_id), now)

    # --- actions ---

    def extend(self, subscription_id: str, days: int, reason: str, actor_id=None):
        """Adds free days to the current plan (support goodwill, outage compensation)."""
        sub = self._load(subscription_id)
        now = datetime.datetime.utcnow()
        before = iso(sub.end_date)
        sub.end_date = max(sub.end_date or now, now) + datetime.timedelta(days=days)
        sub.status = "active"
        billing.record_event(self.db, sub, "extended", from_plan_id=sub.plan_id, to_plan_id=sub.plan_id,
                             actor_id=actor_id, reason=reason, at=now)
        return self._finish(sub, actor_id, "SUBSCRIPTION_EXTENDED",
                            {"days": days, "reason": reason, "end_date": {"from": before, "to": iso(sub.end_date)}})

    def change_plan(self, subscription_id: str, plan_id: str, reason: str, actor_id=None):
        """Moves the subscription to another plan, keeping its end date. The period no longer has a bought price."""
        sub = self._load(subscription_id)
        plan = get_plan(self.db, plan_id)
        if plan.plan_id == sub.plan_id:
            raise FinanceError("The subscription is already on that plan")
        from_plan_id = sub.plan_id
        sub.plan_id = plan.plan_id
        sub.price_id = None
        sub.status = "active"
        billing.record_event(self.db, sub, "plan_changed", from_plan_id=from_plan_id, to_plan_id=plan.plan_id,
                             actor_id=actor_id, reason=reason)
        return self._finish(sub, actor_id, "SUBSCRIPTION_PLAN_CHANGED",
                            {"from_plan_id": str(from_plan_id), "to_plan_id": str(plan.plan_id), "reason": reason})

    def cancel(self, subscription_id: str, reason: str, actor_id=None):
        """Ends the subscription now and moves the user to the free tier. Refunds are separate."""
        sub = self._load(subscription_id)
        free = get_free_plan(self.db)
        if not free:
            raise FinanceError("Free plan is not configured", 500)
        if sub.plan_id == free.plan_id:
            raise FinanceError("The subscription is already on the free tier")
        from_plan_id, before = sub.plan_id, iso(sub.end_date)
        sub.plan_id, sub.end_date, sub.is_trial, sub.price_id, sub.is_auto_renew = free.plan_id, None, False, None, False
        sub.status = "active"
        billing.record_event(self.db, sub, "canceled", from_plan_id=from_plan_id, to_plan_id=free.plan_id,
                             actor_id=actor_id, reason=reason)
        return self._finish(sub, actor_id, "SUBSCRIPTION_CANCELED",
                            {"from_plan_id": str(from_plan_id), "ended": before, "reason": reason})

    def grant(self, user_identifier: str, plan_id: str, duration_days: int = 30, is_trial: bool = False,
              actor_id=None, reason: Optional[str] = None) -> bool:
        """
        Grants or extends a plan without payment (VIPs, support resolution, sales trials).
        `user_identifier` may be the user's UUID or slug.
        """
        user = resolve_user(self.db, user_identifier)
        plan = get_plan(self.db, plan_id)
        actor_uuid = as_uuid(actor_id)
        now = datetime.datetime.utcnow()

        sub = self.db.query(Subscription).filter(Subscription.user_id == user.user_id).first()
        before, from_plan_id = None, None
        if not sub:
            sub = Subscription(user_id=user.user_id, plan_id=plan.plan_id, status="active", start_date=now,
                               end_date=now + datetime.timedelta(days=duration_days))
            self.db.add(sub)
        else:
            before = {"plan_id": str(sub.plan_id), "status": sub.status, "end_date": iso(sub.end_date),
                      "is_trial": sub.is_trial}
            from_plan_id = sub.plan_id
            sub.plan_id = plan.plan_id
            sub.status = "active"
            current_end = sub.end_date if sub.end_date and sub.end_date > now else now
            sub.end_date = current_end + datetime.timedelta(days=duration_days)
        sub.is_trial = is_trial
        sub.price_id = None  # granted time, not bought at a price
        self.db.flush()

        if not is_trial:
            # Zero-value record so the grant shows in the payments stream
            self.db.add(SubscriptionPayment(
                user_id=user.user_id, subscription_id=sub.subscription_id, amount=0,
                payment_method="admin_override", transaction_type="comp", status="success",
                provider_reference=f"ADMIN_GRANT_{now.strftime('%Y%m%d')}",
                payment_metadata={"granted_by": str(actor_id) if actor_id else None, "reason": reason},
            ))

        billing.record_event(self.db, sub, "trial_started" if is_trial else "comped", from_plan_id=from_plan_id,
                             to_plan_id=plan.plan_id, actor_id=actor_uuid, reason=reason, at=now)
        audit(self.db, actor_id, "SUBSCRIPTION_OVERRIDDEN", "SUBSCRIPTION", sub.subscription_id, {
            "user_id": str(user.user_id), "plan": plan.name, "plan_id": str(plan.plan_id),
            "duration_days": duration_days, "is_trial": is_trial, "reason": reason, "before": before,
            "after": {"plan_id": str(plan.plan_id), "status": "active", "end_date": iso(sub.end_date)},
        })
        self.db.commit()
        self._notify_grant(user, plan, duration_days, is_trial, reason)
        return True

    @staticmethod
    def _notify_grant(user: User, plan: Plan, duration_days: int, is_trial: bool, reason: Optional[str]):
        try:
            from common.config import get_config
            from services.notifications.admin_dispatcher import notify_admins_async
            config = get_config()
            admin_url = config.FRONTEND_URL.replace("app.", "admin.").rstrip('/') if "app." in config.FRONTEND_URL else "https://admin.kapuletu.co.ke"
            body = f"""
            <h3>Plan Upgrade Alert</h3>
            <p><strong>User:</strong> {user.first_name} {user.last_name} ({user.email})</p>
            <p><strong>New Plan:</strong> {plan.name}</p>
            <p><strong>Duration:</strong> {duration_days} days (Trial: {is_trial})</p>
            <p><strong>Reason:</strong> {reason or '—'}</p>
            <br>
            <a href="{admin_url}/admin/finance" style="padding: 10px 15px; background-color: #000; color: #fff; text-decoration: none; border-radius: 5px;">View Subscription Details</a>
            """
            notify_admins_async(f"Plan Upgrade Alert: {user.first_name} {user.last_name}", body, category="finance")
        except Exception as e:
            logger.error(f"Failed to dispatch admin notification for upgrade: {e}")
