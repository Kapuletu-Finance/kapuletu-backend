"""
Finance metrics, computed from what was actually paid rather than from plan list prices.

- MRR at a moment = for every paid invoice whose period covers that moment, its subtotal (before tax, net of
  any refund) divided by the months it pays for (1 or 12). ARR = MRR x 12.
- A paying customer is a user with such an invoice. Churn over a window = paying at its start, not at its end.
- Revenue and cash come from the billing ledger; trials and grants from subscription events.

Every window metric is returned with the same-length window just before it, so changes are real.
"""
import datetime
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.billing import Invoice, InvoiceLine, LedgerEntry, Refund, SubscriptionEvent
from models.subscription import Plan, SubscriptionPayment

from .common import FinanceError

ZERO = Decimal("0")
CYCLE_MONTHS = {"monthly": 1, "annual": 12}


@dataclass
class PaidPeriod:
    user_id: object
    start: datetime.datetime
    end: datetime.datetime
    paid_at: datetime.datetime
    monthly_value: Decimal


def add_months(dt: datetime.datetime, months: int) -> datetime.datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return dt.replace(year=year, month=month, day=1)


def _pct_change(current, previous) -> Optional[float]:
    if previous in (None, 0):
        return None
    return round((float(current) - float(previous)) / abs(float(previous)) * 100, 1)


def _num(value) -> float:
    return round(float(value), 2) if isinstance(value, Decimal) else value


class FinanceMetricsService:
    def __init__(self, db: Session, now: Optional[datetime.datetime] = None):
        self.db = db
        self.now = now or datetime.datetime.utcnow()
        self._periods: Optional[List[PaidPeriod]] = None

    # --- source data ---

    def paid_periods(self) -> List[PaidPeriod]:
        """Every paid invoice with a service period, valued per month and net of approved refunds."""
        if self._periods is not None:
            return self._periods
        refunded: Dict[object, Decimal] = defaultdict(lambda: ZERO)
        for invoice_id, amount in self.db.query(Refund.invoice_id, func.sum(Refund.amount)).filter(
            Refund.status.in_(("approved", "paid")), Refund.invoice_id.isnot(None)
        ).group_by(Refund.invoice_id):
            refunded[invoice_id] = Decimal(str(amount or 0))

        periods = []
        for inv in self.db.query(Invoice).filter(
            Invoice.status == "paid", Invoice.period_start.isnot(None), Invoice.period_end.isnot(None)
        ).all():
            subtotal, total = Decimal(str(inv.subtotal or 0)), Decimal(str(inv.total or 0))
            if total <= 0:
                continue
            net = subtotal * (1 - refunded[inv.invoice_id] / total)
            if net <= 0:
                continue
            months = CYCLE_MONTHS.get(inv.billing_cycle or "monthly", 1)
            periods.append(PaidPeriod(inv.user_id, inv.period_start, inv.period_end, inv.paid_at or inv.issued_at,
                                      net / months))
        self._periods = periods
        return periods

    def covering(self, at: datetime.datetime) -> List[PaidPeriod]:
        return [p for p in self.paid_periods() if p.start <= at < p.end]

    def mrr_at(self, at: datetime.datetime) -> Decimal:
        return sum((p.monthly_value for p in self.covering(at)), ZERO)

    def paying_users_at(self, at: datetime.datetime) -> Set[object]:
        return {p.user_id for p in self.covering(at)}

    def first_paid(self) -> Dict[object, datetime.datetime]:
        first: Dict[object, datetime.datetime] = {}
        for p in self.paid_periods():
            if p.user_id not in first or p.paid_at < first[p.user_id]:
                first[p.user_id] = p.paid_at
        return first

    def _ledger_sum(self, account: str, side: str, start, end) -> Decimal:
        col = LedgerEntry.debit if side == "debit" else LedgerEntry.credit
        value = self.db.query(func.coalesce(func.sum(col), 0)).filter(
            LedgerEntry.account == account, LedgerEntry.effective_at >= start, LedgerEntry.effective_at < end
        ).scalar()
        return Decimal(str(value or 0))

    def _events(self, type_: str, start, end) -> List[SubscriptionEvent]:
        return self.db.query(SubscriptionEvent).filter(
            SubscriptionEvent.type == type_, SubscriptionEvent.created_at >= start, SubscriptionEvent.created_at < end
        ).all()

    # --- one window ---

    def window(self, start: datetime.datetime, end: datetime.datetime) -> dict:
        end_at = min(end, self.now)
        mrr = self.mrr_at(end_at)
        paying_end = self.paying_users_at(end_at)
        paying_start = self.paying_users_at(start)
        churned = paying_start - paying_end
        new_paying = [u for u, at in self.first_paid().items() if start <= at < end]

        revenue = self._ledger_sum("revenue", "credit", start, end)
        refunds = self._ledger_sum("refunds", "debit", start, end)
        cash_in = self._ledger_sum("cash", "debit", start, end)

        attempts = self.db.query(SubscriptionPayment.status, func.count(SubscriptionPayment.payment_id)).filter(
            SubscriptionPayment.created_at >= start, SubscriptionPayment.created_at < end,
            or_(SubscriptionPayment.transaction_type.is_(None), SubscriptionPayment.transaction_type == "payment"),
            SubscriptionPayment.payment_method != "admin_override",
        ).group_by(SubscriptionPayment.status).all()
        attempts = dict(attempts)
        settled = attempts.get("success", 0) + attempts.get("failed", 0)

        trials = self._events("trial_started", start, end)
        converted = 0
        for t in trials:
            if self.db.query(SubscriptionEvent.event_id).filter(
                SubscriptionEvent.user_id == t.user_id,
                SubscriptionEvent.type.in_(("upgraded", "renewed")),
                SubscriptionEvent.created_at > t.created_at,
            ).first():
                converted += 1

        return {
            "mrr": mrr,
            "arr": mrr * 12,
            "paying_customers": len(paying_end),
            "arpu": (mrr / len(paying_end)) if paying_end else ZERO,
            "new_paying_customers": len(new_paying),
            "churned_customers": len(churned),
            "churn_rate_percent": round(len(churned) / len(paying_start) * 100, 1) if paying_start else 0.0,
            "net_revenue": revenue - refunds,
            "gross_revenue": revenue,
            "refunds": refunds,
            "cash_collected": cash_in,
            "failed_payments": attempts.get("failed", 0),
            "failed_payment_rate_percent": round(attempts.get("failed", 0) / settled * 100, 1) if settled else 0.0,
            "trials_started": len(trials),
            "trial_conversion_rate_percent": round(converted / len(trials) * 100, 1) if trials else 0.0,
            "comps_granted": len(self._events("comped", start, end)),
        }

    # --- overview ---

    def resolve_window(self, date_from: Optional[datetime.datetime],
                       date_to: Optional[datetime.datetime]) -> Tuple[datetime.datetime, datetime.datetime]:
        end = date_to or self.now
        start = date_from or (end - datetime.timedelta(days=30))
        if start >= end:
            raise FinanceError("'from' must be before 'to'")
        return start, end

    def overview(self, date_from: Optional[datetime.datetime] = None,
                 date_to: Optional[datetime.datetime] = None) -> dict:
        start, end = self.resolve_window(date_from, date_to)
        prev_start, prev_end = start - (end - start), start
        current, previous = self.window(start, end), self.window(prev_start, prev_end)
        return {
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "previous_period": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
            "metrics": {
                key: {
                    "current": _num(current[key]),
                    "previous": _num(previous[key]),
                    "change_pct": _pct_change(current[key], previous[key]),
                }
                for key in current
            },
            "generated_at": self.now.isoformat(),
        }

    # --- series ---

    def revenue_flow(self, interval: str = "month", date_from: Optional[datetime.datetime] = None) -> List[dict]:
        """Invoiced revenue (before tax and refunds) per period, split by plan; add-ons in their own series."""
        if interval not in ("month", "week"):
            raise FinanceError("interval must be 'month' or 'week'")
        start = date_from or add_months(self.now, -5)
        plan_names = dict(self.db.query(Plan.plan_id, Plan.name).all())
        rows = self.db.query(Invoice.paid_at, InvoiceLine.kind, InvoiceLine.plan_id, InvoiceLine.amount).join(
            InvoiceLine, InvoiceLine.invoice_id == Invoice.invoice_id
        ).filter(Invoice.status == "paid", Invoice.paid_at >= start, InvoiceLine.kind.in_(("plan", "addon"))).all()

        def bucket(dt: datetime.datetime) -> str:
            if interval == "month":
                return dt.strftime("%Y-%m")
            year, week, _ = dt.isocalendar()
            return f"{year}-W{week:02d}"

        flow: Dict[str, Dict[str, float]] = {}
        for paid_at, kind, plan_id, amount in rows:
            series = "Add-ons" if kind == "addon" else plan_names.get(plan_id, "Other")
            row = flow.setdefault(bucket(paid_at), {"period": bucket(paid_at)})
            row[series] = round(row.get(series, 0) + float(amount or 0), 2)
        return [flow[k] for k in sorted(flow)]

    def mrr_series(self, months: int = 12) -> List[dict]:
        """MRR at the start of each of the last `months` months, plus today."""
        first = add_months(self.now.replace(hour=0, minute=0, second=0, microsecond=0), -(months - 1))
        points = [add_months(first, i) for i in range(months)] + [self.now]
        return [{"date": p.date().isoformat(), "mrr": _num(self.mrr_at(p)),
                 "paying_customers": len(self.paying_users_at(p))} for p in points]

    def cohort_retention(self, months: int = 12) -> List[dict]:
        """Customers grouped by the month they first paid; share still paying 1, 2, ... months later."""
        cohorts: Dict[datetime.datetime, List[object]] = defaultdict(list)
        for user_id, at in self.first_paid().items():
            cohorts[at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)].append(user_id)

        results = []
        for cohort_start in sorted(cohorts, reverse=True):
            users = set(cohorts[cohort_start])
            retention = []
            for k in range(months):
                check = add_months(cohort_start, k) + datetime.timedelta(days=14)
                if check > self.now:
                    break
                still = len(users & self.paying_users_at(check)) if k else len(users)
                retention.append(int(round(still / len(users) * 100)))
            results.append({"cohort": cohort_start.strftime("%Y-%m"), "users": len(users), "retention": retention})
        return results
