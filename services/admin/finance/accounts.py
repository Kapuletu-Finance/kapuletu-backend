"""The treasurer financial profile: one user's billing account and how much of their plan they use."""
import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.billing import LedgerEntry, SubscriptionEvent
from models.campaign import Campaign
from models.group import Group
from models.subscription import Plan, Subscription
from models.transaction import Transaction

from .common import iso, resolve_user, user_name
from .invoices import InvoiceService
from .refunds import RefundService
from .subscriptions import subscription_state


class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def _ledger(self, user_id, account: str, side: str) -> Decimal:
        col = LedgerEntry.debit if side == "debit" else LedgerEntry.credit
        value = self.db.query(func.coalesce(func.sum(col), 0)).filter(
            LedgerEntry.user_id == user_id, LedgerEntry.account == account
        ).scalar()
        return Decimal(str(value or 0))

    def profile(self, identifier: str) -> dict:
        user = resolve_user(self.db, identifier)
        now = datetime.datetime.utcnow()
        sub = self.db.query(Subscription).filter(Subscription.user_id == user.user_id).first()
        plan = self.db.get(Plan, sub.plan_id) if sub else None

        paid_in = self._ledger(user.user_id, "cash", "debit")
        refunded = self._ledger(user.user_id, "refunds", "debit")

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        groups = self.db.query(func.count(Group.group_id)).filter(Group.owner_id == user.user_id).scalar() or 0
        campaigns = self.db.query(func.count(Campaign.campaign_id)).join(Group, Campaign.group_id == Group.group_id).filter(
            Group.owner_id == user.user_id).scalar() or 0
        transactions = self.db.query(func.count(Transaction.transaction_id)).filter(
            Transaction.owner_id == user.user_id, Transaction.created_at >= month_start).scalar() or 0

        invoices = InvoiceService(self.db)
        events = self.db.query(SubscriptionEvent).filter(SubscriptionEvent.user_id == user.user_id).order_by(
            SubscriptionEvent.created_at.desc()).limit(50).all()
        plan_names = dict(self.db.query(Plan.plan_id, Plan.name).all())

        def usage(used, limit):
            return {"used": used, "limit": limit, "percent": round(used / limit * 100) if limit else None}

        return {
            "user": {
                "user_id": str(user.user_id), "name": user_name(user), "email": user.email,
                "phone_number": user.phone_number, "slug": user.slug, "joined_at": iso(user.created_at),
                "has_used_trial": bool(user.has_used_trial), "is_active": user.is_active,
            },
            "subscription": {
                "subscription_id": str(sub.subscription_id),
                "plan_id": str(plan.plan_id) if plan else None,
                "plan_name": plan.name if plan else None,
                "state": subscription_state(sub, plan, now),
                "is_trial": sub.is_trial,
                "is_auto_renew": sub.is_auto_renew,
                "start_date": iso(sub.start_date),
                "end_date": iso(sub.end_date),
            } if sub else None,
            "balance": {
                "lifetime_paid": float(paid_in),
                "lifetime_refunded": float(refunded),
                "lifetime_value": float(paid_in - refunded),
                "currency": "KES",
            },
            "usage": {
                "groups": usage(groups, plan.max_groups if plan else None),
                "campaigns": usage(campaigns, plan.max_campaigns if plan else None),
                "transactions_this_month": usage(transactions, plan.max_transactions_per_month if plan else None),
            },
            "invoices": invoices.list_invoices(user_id=str(user.user_id), limit=50)["items"],
            "payments": invoices.list_payments(user_id=str(user.user_id), limit=50)["items"],
            "refunds": RefundService(self.db).list(user_id=str(user.user_id), limit=50)["items"],
            "events": [{
                "type": e.type,
                "from_plan": plan_names.get(e.from_plan_id),
                "to_plan": plan_names.get(e.to_plan_id),
                "period_end": iso(e.period_end),
                "reason": e.reason,
                "actor_id": str(e.actor_id) if e.actor_id else None,
                "at": iso(e.created_at),
            } for e in events],
        }
