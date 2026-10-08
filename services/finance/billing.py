"""
Billing primitives shared by checkout, fulfilment, admin finance and the backfill script.

Everything that turns a plan into money lives here: settings, versioned prices, quotes,
invoice and credit-note numbering, double-entry ledger postings, refunds and lifecycle events.
"""
import datetime
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models.billing import (
    BillingSettings, CreditNote, Invoice, InvoiceLine, LedgerEntry, PlanPrice, Refund, SubscriptionEvent,
)
from models.subscription import Plan, SubscriptionPayment

CENT = Decimal("0.01")
INTERVAL_FOR_CYCLE = {"monthly": "month", "annual": "year"}
MONTHS_IN_CYCLE = {"monthly": 1, "annual": 12}


def money(value) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _as_uuid(value) -> Optional[uuid.UUID]:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


class BillingError(Exception):
    """A billing rule refused the request; `status_code` is the HTTP status to return."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# --- settings ---

def get_settings(db: Session) -> BillingSettings:
    settings = db.get(BillingSettings, 1)
    if not settings:
        settings = BillingSettings(id=1)
        db.add(settings)
        db.flush()
    return settings


SETTINGS_FIELDS = (
    "currency", "trial_days", "grace_period_days", "annual_months_charged",
    "addon_monthly_price", "tax_rate_percent", "invoice_prefix",
)


def settings_out(s: BillingSettings) -> dict:
    return {
        "currency": s.currency,
        "trial_days": s.trial_days,
        "grace_period_days": s.grace_period_days,
        "annual_months_charged": s.annual_months_charged,
        "addon_monthly_price": float(money(s.addon_monthly_price)),
        "tax_rate_percent": float(s.tax_rate_percent or 0),
        "invoice_prefix": s.invoice_prefix,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# --- plans and prices ---

def plan_by_code(db: Session, code: str) -> Optional[Plan]:
    return db.query(Plan).filter(Plan.code == code).first()


def current_price(db: Session, plan: Plan, interval: str) -> PlanPrice:
    """The open price for a plan and interval. Creates it from the list price if a plan has none yet."""
    price = db.query(PlanPrice).filter(
        PlanPrice.plan_id == plan.plan_id, PlanPrice.interval == interval, PlanPrice.valid_to.is_(None)
    ).first()
    if price:
        return price
    settings = get_settings(db)
    monthly = money(plan.price)
    amount = monthly if interval == "month" else money(monthly * settings.annual_months_charged)
    price = PlanPrice(plan_id=plan.plan_id, interval=interval, amount=amount, currency=settings.currency)
    db.add(price)
    db.flush()
    return price


def set_plan_prices(db: Session, plan: Plan, monthly=None, annual=None, actor_id=None) -> dict:
    """
    Closes the open price rows that change and opens new ones. When only the monthly price changes,
    the annual price follows it (monthly x annual_months_charged). Returns {"month": (old, new), ...}.
    """
    settings = get_settings(db)
    actor_id = _as_uuid(actor_id)
    targets = {}
    if monthly is not None:
        targets["month"] = money(monthly)
        if annual is None:
            annual = money(monthly) * settings.annual_months_charged
    if annual is not None:
        targets["year"] = money(annual)

    now = datetime.datetime.utcnow()
    changes = {}
    for interval, amount in targets.items():
        open_price = current_price(db, plan, interval)
        if money(open_price.amount) == amount:
            continue
        open_price.valid_to = now
        db.flush()
        db.add(PlanPrice(plan_id=plan.plan_id, interval=interval, amount=amount, currency=settings.currency,
                         valid_from=now, created_by=actor_id))
        changes[interval] = (str(money(open_price.amount)), str(amount))

    if "month" in targets:
        plan.price = targets["month"]
    db.flush()
    return changes


def plan_prices_out(db: Session, plan: Plan) -> dict:
    return {
        "monthly_price": float(money(current_price(db, plan, "month").amount)),
        "annual_price": float(money(current_price(db, plan, "year").amount)),
    }


# --- quotes ---

@dataclass
class QuoteLine:
    kind: str
    description: str
    quantity: int
    unit_amount: Decimal
    amount: Decimal
    plan_id: Optional[uuid.UUID] = None
    price_id: Optional[uuid.UUID] = None


@dataclass
class Quote:
    plan: Plan
    price: PlanPrice
    billing_cycle: str
    has_addons: bool
    currency: str
    lines: List[QuoteLine] = field(default_factory=list)
    subtotal: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    tax_rate_percent: Decimal = Decimal("0")

    def as_dict(self) -> dict:
        return {
            "plan_id": str(self.plan.plan_id),
            "plan_name": self.plan.name,
            "billing_cycle": self.billing_cycle,
            "has_addons": self.has_addons,
            "currency": self.currency,
            "lines": [
                {"kind": l.kind, "description": l.description, "quantity": l.quantity,
                 "unit_amount": float(l.unit_amount), "amount": float(l.amount)}
                for l in self.lines
            ],
            "subtotal": float(self.subtotal),
            "tax_rate_percent": float(self.tax_rate_percent),
            "tax": float(self.tax),
            "total": float(self.total),
        }


def build_quote(db: Session, plan: Plan, billing_cycle: str = "monthly", has_addons: bool = False) -> Quote:
    """What a checkout for this plan costs, line by line. The only place prices are computed."""
    if billing_cycle not in INTERVAL_FOR_CYCLE:
        raise BillingError("billing_cycle must be 'monthly' or 'annual'")
    if plan.archived_at is not None or not plan.is_public:
        raise BillingError("This plan is not available for purchase", 404)

    settings = get_settings(db)
    price = current_price(db, plan, INTERVAL_FOR_CYCLE[billing_cycle])
    plan_amount = money(price.amount)
    cycle_label = "annual" if billing_cycle == "annual" else "monthly"

    quote = Quote(plan=plan, price=price, billing_cycle=billing_cycle, has_addons=has_addons,
                  currency=price.currency or settings.currency)
    quote.lines.append(QuoteLine("plan", f"{plan.name} plan ({cycle_label})", 1, plan_amount, plan_amount,
                                 plan.plan_id, price.price_id))

    if has_addons:
        # Charged per month of the period, with the same months-charged discount as the plan on annual billing.
        months = settings.annual_months_charged if billing_cycle == "annual" else 1
        unit = money(settings.addon_monthly_price)
        quote.lines.append(QuoteLine("addon", f"Extra campaign add-on ({months} month{'s' if months != 1 else ''})",
                                     months, unit, money(unit * months)))

    quote.subtotal = money(sum(l.amount for l in quote.lines))
    quote.tax_rate_percent = Decimal(str(settings.tax_rate_percent or 0))
    quote.tax = money(quote.subtotal * quote.tax_rate_percent / 100)
    if quote.currency == "KES":
        # M-Pesa only moves whole shillings, so the total must be whole too.
        quote.tax = quote.tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(CENT)
    if quote.tax:
        quote.lines.append(QuoteLine("tax", f"Tax ({quote.tax_rate_percent.normalize()}%)", 1, quote.tax, quote.tax))
    quote.total = quote.subtotal + quote.tax
    return quote


# --- numbering ---

def _next_sequence(db: Session, sequence: str, fallback_model, issued_col) -> int:
    try:
        with db.begin_nested():
            return int(db.execute(text(f"SELECT nextval('{sequence}')")).scalar())
    except Exception:
        # Not PostgreSQL (tests): count rows instead.
        return (db.query(func.count()).select_from(fallback_model).scalar() or 0) + 1


def next_invoice_number(db: Session, when: Optional[datetime.datetime] = None) -> str:
    prefix = get_settings(db).invoice_prefix
    n = _next_sequence(db, "invoice_number_seq", Invoice, Invoice.issued_at)
    return f"{prefix}-{(when or datetime.datetime.utcnow()).year}-{n:06d}"


def next_credit_note_number(db: Session, when: Optional[datetime.datetime] = None) -> str:
    prefix = get_settings(db).invoice_prefix
    n = _next_sequence(db, "credit_note_number_seq", CreditNote, CreditNote.issued_at)
    return f"{prefix}-CN-{(when or datetime.datetime.utcnow()).year}-{n:06d}"


# --- invoices ---

def create_invoice(db: Session, user_id, subscription_id, quote: Quote, status: str = "open",
                   issued_at: Optional[datetime.datetime] = None) -> Invoice:
    issued_at = issued_at or datetime.datetime.utcnow()
    invoice = Invoice(
        number=next_invoice_number(db, issued_at),
        user_id=user_id,
        subscription_id=subscription_id,
        status=status,
        currency=quote.currency,
        subtotal=quote.subtotal,
        tax=quote.tax,
        total=quote.total,
        billing_cycle=quote.billing_cycle,
        issued_at=issued_at,
        due_at=issued_at,
    )
    db.add(invoice)
    db.flush()
    for l in quote.lines:
        db.add(InvoiceLine(invoice_id=invoice.invoice_id, kind=l.kind, description=l.description, quantity=l.quantity,
                           unit_amount=l.unit_amount, amount=l.amount, plan_id=l.plan_id, price_id=l.price_id))
    db.flush()
    return invoice


def mark_invoice_paid(invoice: Invoice, period_start: datetime.datetime, period_end: datetime.datetime,
                      paid_at: Optional[datetime.datetime] = None):
    invoice.status = "paid"
    invoice.paid_at = paid_at or datetime.datetime.utcnow()
    invoice.period_start = period_start
    invoice.period_end = period_end


def void_invoice(invoice: Invoice, note: str = ""):
    if invoice.status in ("open", "draft"):
        invoice.status = "void"
        invoice.voided_at = datetime.datetime.utcnow()
        invoice.notes = note or invoice.notes


# --- ledger ---

def _post(db: Session, lines, source_type: str, source_id, user_id, invoice_id, currency, memo, effective_at):
    """Writes one balanced journal. `lines` = [(account, debit, credit), ...] with zero rows skipped."""
    lines = [(a, money(d), money(c)) for a, d, c in lines if money(d) or money(c)]
    if sum(d for _, d, _ in lines) != sum(c for _, _, c in lines):
        raise BillingError("Unbalanced ledger journal")
    journal_id = uuid.uuid4()
    for account, debit, credit in lines:
        db.add(LedgerEntry(journal_id=journal_id, account=account, debit=debit, credit=credit, currency=currency,
                           user_id=user_id, source_type=source_type, source_id=source_id, invoice_id=invoice_id,
                           memo=memo, effective_at=effective_at or datetime.datetime.utcnow()))
    db.flush()
    return journal_id


def ledger_has(db: Session, source_type: str, source_id) -> bool:
    return db.query(LedgerEntry.entry_id).filter(
        LedgerEntry.source_type == source_type, LedgerEntry.source_id == source_id
    ).first() is not None


def post_payment(db: Session, payment: SubscriptionPayment, invoice: Optional[Invoice] = None,
                 effective_at: Optional[datetime.datetime] = None):
    """Money received: debit cash; credit revenue (and tax payable when the invoice carries tax)."""
    if ledger_has(db, "payment", payment.payment_id):
        return None
    total = money(payment.amount)
    tax = money(invoice.tax) if invoice is not None and money(invoice.total) == total else Decimal("0")
    return _post(db, [("cash", total, 0), ("revenue", 0, total - tax), ("tax_payable", 0, tax)],
                 "payment", payment.payment_id, payment.user_id, invoice.invoice_id if invoice is not None else None,
                 payment.currency or "KES", f"Payment {payment.provider_reference or payment.payment_id}",
                 effective_at or payment.created_at)


def post_refund(db: Session, refund: Refund, effective_at: Optional[datetime.datetime] = None):
    """Money returned: debit refunds (contra-revenue); credit cash."""
    if ledger_has(db, "refund", refund.refund_id):
        return None
    amount = money(refund.amount)
    return _post(db, [("refunds", amount, 0), ("cash", 0, amount)], "refund", refund.refund_id, refund.user_id,
                 refund.invoice_id, refund.currency or "KES", refund.reason or "Refund", effective_at)


# --- lifecycle ---

def record_event(db: Session, sub, type_: str, from_plan_id=None, to_plan_id=None, invoice_id=None,
                 actor_id=None, reason: Optional[str] = None, at: Optional[datetime.datetime] = None):
    actor_id = _as_uuid(actor_id)
    db.add(SubscriptionEvent(
        subscription_id=sub.subscription_id, user_id=sub.user_id, type=type_,
        from_plan_id=from_plan_id, to_plan_id=to_plan_id, period_end=sub.end_date, invoice_id=invoice_id,
        actor_id=actor_id, reason=reason, created_at=at or datetime.datetime.utcnow(),
    ))


# --- refunds ---

def active_refund(db: Session, payment: SubscriptionPayment) -> Optional[Refund]:
    return db.query(Refund).filter(Refund.payment_id == payment.payment_id, Refund.status != "rejected").first()


def execute_refund(db: Session, refund: Refund, payment: SubscriptionPayment, approved_by=None,
                   at: Optional[datetime.datetime] = None) -> Refund:
    """
    Carries out an approved refund (full or partial), record-only: a negative payment row (so payment lists
    and revenue sums net out), a credit note against the invoice, and the ledger posting.
    """
    approved_by = _as_uuid(approved_by)
    at = at or datetime.datetime.utcnow()
    amount = money(refund.amount)
    refund.status = "approved"
    refund.approved_by = approved_by
    refund.decided_at = at

    refund_payment = SubscriptionPayment(
        user_id=payment.user_id, subscription_id=payment.subscription_id, amount=-amount,
        currency=payment.currency, status="success", payment_method="admin_refund", transaction_type="refund",
        provider_reference=payment.provider_reference, invoice_id=None, created_at=at,
        payment_metadata={"reason": refund.reason, "original_payment_id": str(payment.payment_id),
                          "refund_id": str(refund.refund_id),
                          "requested_by": str(refund.requested_by) if refund.requested_by else None,
                          "approved_by": str(approved_by) if approved_by else None},
    )
    db.add(refund_payment)
    db.flush()
    refund.refund_payment_id = refund_payment.payment_id

    if payment.invoice_id:
        db.add(CreditNote(number=next_credit_note_number(db, at), invoice_id=payment.invoice_id,
                          user_id=payment.user_id, refund_id=refund.refund_id, amount=amount,
                          currency=refund.currency, reason=refund.reason, issued_by=approved_by, issued_at=at))

    meta = dict(payment.payment_metadata or {})
    meta["refund_payment_id"] = str(refund_payment.payment_id)
    meta["refund_id"] = str(refund.refund_id)
    payment.payment_metadata = meta

    post_refund(db, refund, at)
    return refund


def record_refund(db: Session, payment: SubscriptionPayment, reason: str, actor_id=None,
                  reason_code: str = "other", at: Optional[datetime.datetime] = None) -> Refund:
    """A full refund requested and approved in one step (used where no second approver is involved)."""
    actor_id = _as_uuid(actor_id)
    at = at or datetime.datetime.utcnow()
    refund = Refund(payment_id=payment.payment_id, invoice_id=payment.invoice_id, user_id=payment.user_id,
                    amount=money(payment.amount), currency=payment.currency or "KES", reason_code=reason_code,
                    reason=reason, status="requested", requested_by=actor_id, requested_at=at)
    db.add(refund)
    db.flush()
    return execute_refund(db, refund, payment, actor_id, at)
