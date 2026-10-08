"""Plan catalogue and billing rules."""
import datetime
import re

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.utils import parse_uuid
from models.subscription import Plan, Subscription
from services.finance import billing
from services.finance.plans import FREE_PLAN_CODE

from .common import FinanceError, audit, get_plan

# Plan columns an admin may change directly, keyed by the API field name. Prices go through plan_prices.
PLAN_FIELDS = {
    "name": "name",
    "max_groups": "max_groups",
    "max_campaigns": "max_campaigns",
    "max_transactions": "max_transactions_per_month",
    "allowed_features": "allowed_features",
    "is_public": "is_public",
}


class PlanService:
    def __init__(self, db: Session):
        self.db = db

    def _out(self, p: Plan, subscribers: int = None) -> dict:
        prices = billing.plan_prices_out(self.db, p)
        if subscribers is None:
            subscribers = self.db.query(func.count(Subscription.subscription_id)).filter(
                Subscription.plan_id == p.plan_id, Subscription.status == "active"
            ).scalar() or 0
        return {
            "plan_id": str(p.plan_id),
            "code": p.code,
            "name": p.name,
            "price": prices["monthly_price"],
            "monthly_price": prices["monthly_price"],
            "annual_price": prices["annual_price"],
            "max_groups": p.max_groups,
            "max_campaigns": p.max_campaigns,
            "max_transactions": p.max_transactions_per_month,
            "allowed_features": p.allowed_features or {},
            "is_public": p.is_public,
            "archived_at": p.archived_at.isoformat() if p.archived_at else None,
            "active_subscribers": subscribers,
        }

    @staticmethod
    def _snapshot(p: Plan) -> dict:
        return {field: getattr(p, column) for field, column in PLAN_FIELDS.items()}

    @staticmethod
    def _code_from_name(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "plan"

    def list(self):
        """All plans, including hidden and archived ones, with how many active subscriptions each has."""
        counts = dict(self.db.query(Subscription.plan_id, func.count(Subscription.subscription_id)).filter(
            Subscription.status == "active"
        ).group_by(Subscription.plan_id).all())
        out = [self._out(p, counts.get(p.plan_id, 0)) for p in self.db.query(Plan).order_by(Plan.price.asc()).all()]
        self.db.commit()  # plan_prices_out may have created a missing price row
        return out

    def get(self, plan_id: str):
        try:
            out = self._out(get_plan(self.db, plan_id))
        except FinanceError:
            return None
        self.db.commit()
        return out

    def update(self, plan_id: str, data: dict, actor_id=None):
        """
        Updates a plan with only the fields sent. A new price closes the current price row and opens a new one,
        so invoices already issued keep what they charged.
        """
        p = get_plan(self.db, plan_id)
        before = self._snapshot(p)
        for field, column in PLAN_FIELDS.items():
            if field in data and data[field] is not None:
                setattr(p, column, data[field])
        after = self._snapshot(p)
        changes = {k: {"from": before[k], "to": after[k]} for k in PLAN_FIELDS if before[k] != after[k]}

        monthly, annual = data.get("price"), data.get("annual_price")
        if monthly is not None or annual is not None:
            for interval, (old, new) in billing.set_plan_prices(self.db, p, monthly, annual, actor_id).items():
                changes[f"{interval}_price"] = {"from": old, "to": new}

        if not changes:
            return self._out(p)
        audit(self.db, actor_id, "PLAN_UPDATED", "PLAN", p.plan_id, {"plan": before["name"], "changes": changes})
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise FinanceError("A plan with that name already exists", 409)
        return self._out(p)

    def create(self, data: dict, actor_id=None) -> str:
        code = data.get("code") or self._code_from_name(data["name"])
        if self.db.query(Plan).filter((Plan.code == code) | (Plan.name == data["name"])).first():
            raise FinanceError("A plan with that name or code already exists", 409)
        plan = Plan(
            code=code,
            name=data["name"],
            price=billing.money(data["price"]),
            max_groups=data.get("max_groups", 1),
            max_campaigns=data.get("max_campaigns", 5),
            max_transactions_per_month=data.get("max_transactions", 100),
            allowed_features=data.get("allowed_features") or {},
            is_public=data.get("is_public", True),
        )
        self.db.add(plan)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise FinanceError("A plan with that name or code already exists", 409)
        billing.set_plan_prices(self.db, plan, data["price"], data.get("annual_price"), actor_id)
        audit(self.db, actor_id, "PLAN_CREATED", "PLAN", plan.plan_id, {
            "plan": {**self._snapshot(plan), "code": code},
            "prices": billing.plan_prices_out(self.db, plan),
        })
        self.db.commit()
        return str(plan.plan_id)

    def set_archived(self, plan_id: str, archived: bool, actor_id=None):
        """Archived plans can't be bought; existing subscribers keep them until their period ends."""
        p = get_plan(self.db, plan_id)
        if archived and p.code == FREE_PLAN_CODE:
            raise FinanceError("The free tier can't be archived")
        p.archived_at = datetime.datetime.utcnow() if archived else None
        audit(self.db, actor_id, "PLAN_ARCHIVED" if archived else "PLAN_RESTORED", "PLAN", p.plan_id, {"plan": p.name})
        self.db.commit()
        return self._out(p)

    # --- billing rules ---

    def get_settings(self):
        out = billing.settings_out(billing.get_settings(self.db))
        self.db.commit()
        return out

    def update_settings(self, data: dict, actor_id=None):
        s = billing.get_settings(self.db)
        before = billing.settings_out(s)
        for field in billing.SETTINGS_FIELDS:
            if field in data and data[field] is not None:
                setattr(s, field, data[field])
        s.updated_by = parse_uuid(actor_id) if actor_id else None
        s.updated_at = datetime.datetime.utcnow()
        self.db.flush()
        after = billing.settings_out(s)
        changes = {k: {"from": before[k], "to": after[k]} for k in billing.SETTINGS_FIELDS if before[k] != after[k]}
        if changes:
            audit(self.db, actor_id, "BILLING_SETTINGS_UPDATED", "BILLING_SETTINGS", 1, {"changes": changes})
        self.db.commit()
        return after
