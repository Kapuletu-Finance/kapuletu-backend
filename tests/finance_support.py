"""
Helpers for the finance tests (fixtures live in conftest.py).
"""
import datetime
import uuid

from models.audit_log import AuditLog
from models.billing import (
    BillingSettings,
    CreditNote,
    Invoice,
    InvoiceLine,
    LedgerEntry,
    PlanPrice,
    ProviderEvent,
    Refund,
    SubscriptionEvent,
)
from models.campaign import Campaign
from models.communication_logs import CommunicationLog
from models.communications import CommBroadcast, CommMessage, CommSuppression
from models.employees import ApprovalRequest, EmployeeAuditLog
from models.finance_ops import ReconciliationItem, ReconciliationRun, ReportSchedule
from models.group import Group
from models.subscription import Plan, Subscription, SubscriptionPayment
from models.system_config import SystemConfig
from models.transaction import Transaction
from models.users import User
from services.finance import billing

FINANCE_MODELS = (
    User, Plan, PlanPrice, BillingSettings, Subscription, Invoice, InvoiceLine, SubscriptionPayment, Refund,
    CreditNote, LedgerEntry, SubscriptionEvent, ProviderEvent, AuditLog, SystemConfig, CommunicationLog,
    Group, Campaign, Transaction, ApprovalRequest, EmployeeAuditLog, ReconciliationRun, ReconciliationItem,
    ReportSchedule, CommBroadcast, CommMessage, CommSuppression,
)


def make_world(db, sub_end=None):
    """A treasurer on the free Basic tier, plus a paid Silver plan (KES 1,000 / month)."""
    user = User(first_name="Ann", last_name="Treasurer", email=f"{uuid.uuid4().hex}@x.ke",
                phone_number=uuid.uuid4().hex[:12], slug=f"ann-{uuid.uuid4().hex[:6]}")
    basic = Plan(code="basic", name="Basic", price=0)
    silver = Plan(code="silver", name="Silver", price=1000)
    db.add_all([user, basic, silver])
    db.flush()
    sub = Subscription(user_id=user.user_id, plan_id=basic.plan_id, status="active", end_date=sub_end)
    db.add(sub)
    db.commit()
    return user, basic, silver, sub


def pending_checkout(db, user, sub, plan, amount=1000, ref="ws_CO_1", invoice_id=None):
    payment = SubscriptionPayment(
        user_id=user.user_id, subscription_id=sub.subscription_id, amount=amount, currency="KES",
        status="pending", payment_method="mpesa", provider_reference=ref, invoice_id=invoice_id,
        payment_metadata={"plan_id": str(plan.plan_id), "billing_cycle": "monthly"},
    )
    db.add(payment)
    db.commit()
    return payment


def paid_invoice(db, user, sub, plan, paid_at, cycle="monthly", ref=None):
    """A checkout that was paid at `paid_at`: invoice, payment and ledger posting, like fulfilment makes."""
    quote = billing.build_quote(db, plan, cycle)
    invoice = billing.create_invoice(db, user.user_id, sub.subscription_id, quote, issued_at=paid_at)
    days = 365 if cycle == "annual" else 30
    billing.mark_invoice_paid(invoice, paid_at, paid_at + datetime.timedelta(days=days), paid_at)
    payment = SubscriptionPayment(user_id=user.user_id, subscription_id=sub.subscription_id, invoice_id=invoice.invoice_id,
                                  amount=quote.total, currency="KES", status="success", payment_method="mpesa",
                                  provider_reference=ref or uuid.uuid4().hex, created_at=paid_at,
                                  payment_metadata={"receipt_number": "R" + uuid.uuid4().hex[:6]})
    db.add(payment)
    db.flush()
    billing.post_payment(db, payment, invoice, paid_at)
    db.commit()
    return invoice, payment
