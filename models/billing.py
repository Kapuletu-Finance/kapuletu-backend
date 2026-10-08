import datetime
import uuid

from sqlalchemy import (
    JSON, UUID, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint,
    text,
)

from .base import Base

# Money is always Numeric(12, 2) with an explicit currency.
Money = Numeric(12, 2)


class BillingSettings(Base):
    """
    BillingSettings: The single row (id = 1) of platform-wide billing rules that used to be hardcoded.
    Edited by the finance officer; read by checkout, trials and the expiry sweep.
    """
    __tablename__ = "billing_settings"

    id = Column(Integer, primary_key=True, default=1)
    currency = Column(String(3), nullable=False, default="KES")
    trial_days = Column(Integer, nullable=False, default=21)
    grace_period_days = Column(Integer, nullable=False, default=7)
    # An annual plan charges this many months (11 = one month free). Used when an annual price is not set explicitly.
    annual_months_charged = Column(Integer, nullable=False, default=11)
    # The "extra campaign" add-on, charged per month of the billing period.
    addon_monthly_price = Column(Money, nullable=False, default=200)
    # VAT or other tax added on top of the subtotal; 0 until the business registers for it.
    tax_rate_percent = Column(Numeric(5, 2), nullable=False, default=0)
    invoice_prefix = Column(String(10), nullable=False, default="KPL")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (CheckConstraint("id = 1", name="billing_settings_single_row"),)


class PlanPrice(Base):
    """
    PlanPrice: A versioned price for one plan and billing interval. The current price has valid_to = NULL;
    a price change closes the old row and opens a new one, so past invoices keep pointing at what was charged.
    """
    __tablename__ = "plan_prices"

    price_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.plan_id"), nullable=False, index=True)
    interval = Column(String(10), nullable=False)  # month | year
    amount = Column(Money, nullable=False)
    currency = Column(String(3), nullable=False, default="KES")
    valid_from = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    valid_to = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("interval in ('month', 'year')", name="plan_prices_interval"),
        # One open price per plan and interval
        Index("uq_plan_prices_open", "plan_id", "interval", unique=True,
              postgresql_where=text("valid_to IS NULL"), sqlite_where=text("valid_to IS NULL")),
    )


class ProviderEvent(Base):
    """
    ProviderEvent: Every raw payment-gateway callback, stored before it is processed.
    (provider, event_key) is unique, so a replayed callback is recognised and not processed twice.
    """
    __tablename__ = "provider_events"

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(20), nullable=False)
    event_key = Column(String, nullable=False)
    correlation_id = Column(String, nullable=True, index=True)
    payload = Column(JSON, nullable=False)
    verified = Column(Boolean, nullable=False, default=False)
    outcome = Column(String(30), nullable=True)  # fulfilled, failed, refused, unconfirmed, ignored, error
    received_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("provider", "event_key", name="uix_provider_event"),)


class Invoice(Base):
    """
    Invoice: What a treasurer owes for one billing period. Draft -> open (awaiting payment) -> paid, or void.
    """
    __tablename__ = "invoices"

    invoice_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number = Column(String, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.subscription_id"), nullable=True)
    status = Column(String(10), nullable=False, default="open")  # draft | open | paid | void
    currency = Column(String(3), nullable=False, default="KES")
    subtotal = Column(Money, nullable=False, default=0)
    tax = Column(Money, nullable=False, default=0)
    total = Column(Money, nullable=False, default=0)
    billing_cycle = Column(String(10), nullable=True)  # monthly | annual
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    issued_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    due_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)

    __table_args__ = (CheckConstraint("status in ('draft', 'open', 'paid', 'void')", name="invoices_status"),)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    line_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # plan | addon | tax | adjustment
    description = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_amount = Column(Money, nullable=False)
    amount = Column(Money, nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.plan_id"), nullable=True)
    price_id = Column(UUID(as_uuid=True), ForeignKey("plan_prices.price_id"), nullable=True)


class SubscriptionEvent(Base):
    """
    SubscriptionEvent: Every lifecycle change to a subscription (paid upgrade, trial, admin grant, expiry, cancel).
    The subscriptions row holds the current state; this table is its history, used for churn and retention.
    """
    __tablename__ = "subscription_events"

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.subscription_id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True)
    type = Column(String(30), nullable=False)  # created, trial_started, renewed, upgraded, downgraded, comped, expired, cancel_requested
    from_plan_id = Column(UUID(as_uuid=True), nullable=True)
    to_plan_id = Column(UUID(as_uuid=True), nullable=True)
    period_end = Column(DateTime, nullable=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.invoice_id"), nullable=True)
    actor_id = Column(UUID(as_uuid=True), nullable=True)  # None = the system
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)


class Refund(Base):
    """
    Refund: Money going back to a treasurer for a payment. Record-only today: the payout itself is made
    through M-Pesa or the card provider outside the platform.
    """
    __tablename__ = "refunds"

    refund_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("subscription_payments.payment_id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.invoice_id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    amount = Column(Money, nullable=False)
    currency = Column(String(3), nullable=False, default="KES")
    reason_code = Column(String(30), nullable=False, default="other")
    reason = Column(String, nullable=True)
    status = Column(String(10), nullable=False, default="requested")  # requested | approved | rejected | paid
    requested_by = Column(UUID(as_uuid=True), nullable=True)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    requested_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)
    refund_payment_id = Column(UUID(as_uuid=True), ForeignKey("subscription_payments.payment_id"), nullable=True)

    __table_args__ = (
        CheckConstraint("status in ('requested', 'approved', 'rejected', 'paid')", name="refunds_status"),
        CheckConstraint("amount > 0", name="refunds_positive"),
        # At most one refund in flight or done per payment (rejected ones don't count)
        Index("uq_refunds_active_payment", "payment_id", unique=True,
              postgresql_where=text("status <> 'rejected'"), sqlite_where=text("status <> 'rejected'")),
    )


class CreditNote(Base):
    """
    CreditNote: Reduces what an invoice is worth after it was issued (refund, goodwill, billing error).
    """
    __tablename__ = "credit_notes"

    credit_note_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number = Column(String, unique=True, nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.invoice_id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    refund_id = Column(UUID(as_uuid=True), ForeignKey("refunds.refund_id"), nullable=True)
    amount = Column(Money, nullable=False)
    currency = Column(String(3), nullable=False, default="KES")
    reason = Column(String, nullable=True)
    issued_by = Column(UUID(as_uuid=True), nullable=True)
    issued_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)


class LedgerEntry(Base):
    """
    LedgerEntry: One line of an append-only, double-entry billing journal. Lines sharing a journal_id
    balance (total debits = total credits). The database refuses UPDATE and DELETE on this table.

    Accounts: cash (money held at M-Pesa / Flutterwave), revenue, tax_payable, refunds (contra-revenue).
    """
    __tablename__ = "billing_ledger"

    entry_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    account = Column(String(20), nullable=False)
    debit = Column(Money, nullable=False, default=0)
    credit = Column(Money, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="KES")
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    source_type = Column(String(20), nullable=False)  # payment | refund
    source_id = Column(UUID(as_uuid=True), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), nullable=True)
    memo = Column(String, nullable=True)
    effective_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0 AND (debit = 0 OR credit = 0)", name="billing_ledger_one_side"),
        CheckConstraint("account in ('cash', 'revenue', 'tax_payable', 'refunds')", name="billing_ledger_account"),
        # A source (payment, refund) is posted once per account
        Index("uq_billing_ledger_source_account", "source_type", "source_id", "account", unique=True),
    )
