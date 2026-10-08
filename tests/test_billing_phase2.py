"""
Phase 2 billing foundation: prices come from versioned plan prices and billing settings, checkout issues
an invoice, a verified payment settles it and posts a balanced ledger journal, refunds post credit notes,
and the backfill turns legacy payments into the same records.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from finance_support import make_world, pending_checkout
from sqlalchemy import func

from models.billing import (
    CreditNote,
    Invoice,
    InvoiceLine,
    LedgerEntry,
    ProviderEvent,
    Refund,
    SubscriptionEvent,
)
from models.subscription import Plan, Subscription, SubscriptionPayment
from services.finance import billing


def ledger_balance(db, account):
    debit, credit = db.query(func.sum(LedgerEntry.debit), func.sum(LedgerEntry.credit)).filter(
        LedgerEntry.account == account
    ).one()
    return Decimal(str(debit or 0)) - Decimal(str(credit or 0))


def assert_journals_balance(db):
    for journal_id, debit, credit in db.query(
        LedgerEntry.journal_id, func.sum(LedgerEntry.debit), func.sum(LedgerEntry.credit)
    ).group_by(LedgerEntry.journal_id):
        assert Decimal(str(debit)) == Decimal(str(credit)), journal_id


# --- quotes ---

def test_quote_uses_versioned_prices_and_settings(db):
    user, basic, silver, sub = make_world(db)

    assert billing.build_quote(db, silver, "monthly").total == Decimal("1000.00")
    assert billing.build_quote(db, silver, "annual").total == Decimal("11000.00")  # 11 months charged

    with_addon = billing.build_quote(db, silver, "annual", has_addons=True)
    assert [l.kind for l in with_addon.lines] == ["plan", "addon"]
    assert with_addon.total == Decimal("13200.00")  # 11000 + 200 x 11

    settings = billing.get_settings(db)
    settings.tax_rate_percent = Decimal("16")
    settings.addon_monthly_price = Decimal("199.99")
    taxed = billing.build_quote(db, silver, "monthly", has_addons=True)
    assert taxed.subtotal == Decimal("1199.99")
    assert taxed.tax == Decimal("192.00")  # 191.9984 rounded to whole shillings for M-Pesa
    assert taxed.total == Decimal("1391.99")


def test_archived_plan_cannot_be_bought(db):
    user, basic, silver, sub = make_world(db)
    silver.archived_at = datetime.datetime.utcnow()
    with pytest.raises(billing.BillingError) as err:
        billing.build_quote(db, silver, "monthly")
    assert err.value.status_code == 404


def test_price_change_leaves_issued_invoices_alone(db):
    user, basic, silver, sub = make_world(db)
    invoice = billing.create_invoice(db, user.user_id, sub.subscription_id, billing.build_quote(db, silver))
    billing.set_plan_prices(db, silver, monthly=1500)
    db.commit()

    assert billing.build_quote(db, silver).total == Decimal("1500.00")
    assert Decimal(str(invoice.total)) == Decimal("1000.00")
    line = db.query(InvoiceLine).filter_by(invoice_id=invoice.invoice_id).one()
    assert Decimal(str(line.amount)) == Decimal("1000.00")


# --- checkout through the real router ---

@pytest.fixture
def client(Session, db, monkeypatch):
    from common.auth_dependencies import get_verified_user
    from common.database import get_db
    from services.finance import checkout_router
    from services.finance.providers.mpesa import MpesaProvider

    user, basic, silver, sub = make_world(db)
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "s3cret")
    monkeypatch.setattr(MpesaProvider, "initiate_checkout",
                        lambda self, *a, **k: {"correlation_id": "ws_CO_9", "status": "initiated"})
    monkeypatch.setattr(MpesaProvider, "stk_push_query", lambda self, cid: {"success": True, "status": "success"})

    app = FastAPI()
    app.include_router(checkout_router.router, prefix="/finance")

    def session_override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_verified_user] = lambda: {"sub": str(user.user_id), "user_id": str(user.user_id)}
    return TestClient(app), user, silver


def mpesa_callback(result_code=0, amount=1000, ref="ws_CO_9"):
    return {"Body": {"stkCallback": {
        "CheckoutRequestID": ref, "ResultCode": result_code, "ResultDesc": "ok" if result_code == 0 else "Cancelled",
        "CallbackMetadata": {"Item": [{"Name": "Amount", "Value": amount}, {"Name": "MpesaReceiptNumber", "Value": "RCPT9"}]},
    }}}


def test_checkout_invoice_payment_and_ledger(client, db):
    http, user, silver = client

    quote = http.post("/finance/quote", json={"plan_id": str(silver.plan_id), "billing_cycle": "monthly"}).json()
    assert quote["total"] == 1000.0

    res = http.post("/finance/checkout", json={
        "plan_id": str(silver.plan_id), "provider": "mpesa", "phone_number": "254700000000",
        "email": None, "name": None, "billing_cycle": "monthly",
    })
    assert res.status_code == 200, res.text

    invoice = db.query(Invoice).one()
    payment = db.query(SubscriptionPayment).one()
    assert invoice.status == "open" and payment.invoice_id == invoice.invoice_id
    assert Decimal(str(payment.amount)) == Decimal("1000.00")

    # Unsigned callback is rejected; the right token is accepted.
    assert http.post("/finance/webhooks/mpesa", json=mpesa_callback()).status_code == 401
    assert http.post("/finance/webhooks/mpesa?token=s3cret", json=mpesa_callback()).json() == {"received": True}

    db.expire_all()
    assert invoice.status == "paid" and invoice.period_end is not None
    sub = db.query(Subscription).filter_by(user_id=user.user_id).one()
    assert sub.plan_id == silver.plan_id and not sub.is_trial
    assert ledger_balance(db, "cash") == Decimal("1000.00")
    assert ledger_balance(db, "revenue") == Decimal("-1000.00")
    assert db.query(SubscriptionEvent).filter_by(type="upgraded").count() == 1
    assert db.query(ProviderEvent).one().outcome == "fulfilled"

    # Safaricom repeats the callback: nothing is posted twice.
    assert http.post("/finance/webhooks/mpesa?token=s3cret", json=mpesa_callback()).json()["duplicate"] is True
    assert db.query(LedgerEntry).count() == 2
    assert_journals_balance(db)


def test_cancelled_payment_voids_invoice(client, db):
    http, user, silver = client
    http.post("/finance/checkout", json={
        "plan_id": str(silver.plan_id), "provider": "mpesa", "phone_number": "254700000000",
        "email": None, "name": None, "billing_cycle": "monthly",
    })
    http.post("/finance/webhooks/mpesa?token=s3cret", json=mpesa_callback(result_code=1032))
    db.expire_all()
    assert db.query(Invoice).one().status == "void"
    assert db.query(SubscriptionPayment).one().status == "failed"
    assert db.query(LedgerEntry).count() == 0


def test_trial_uses_settings_and_ends_when_user_pays(client, db):
    http, user, silver = client
    billing.get_settings(db).trial_days = 10
    db.add(Plan(code="professional", name="Professional", price=2000))
    db.commit()

    assert http.post("/finance/activate-trial").status_code == 200
    db.expire_all()
    sub = db.query(Subscription).filter_by(user_id=user.user_id).one()
    assert sub.is_trial and 9 <= (sub.end_date - datetime.datetime.utcnow()).days <= 10
    assert http.get("/finance/my-subscription").json()["is_on_trial"] is True

    http.post("/finance/checkout", json={
        "plan_id": str(silver.plan_id), "provider": "mpesa", "phone_number": "254700000000",
        "email": None, "name": None, "billing_cycle": "monthly",
    })
    http.post("/finance/webhooks/mpesa?token=s3cret", json=mpesa_callback())
    db.expire_all()
    sub = db.query(Subscription).filter_by(user_id=user.user_id).one()
    # Paid period starts now; the remaining trial days are not added on top.
    assert not sub.is_trial and 29 <= (sub.end_date - datetime.datetime.utcnow()).days <= 30


# --- refunds ---

def test_refund_posts_credit_note_and_reverses_cash(db):
    from services.admin.finance import RefundService
    user, basic, silver, sub = make_world(db)
    invoice = billing.create_invoice(db, user.user_id, sub.subscription_id, billing.build_quote(db, silver))
    payment = pending_checkout(db, user, sub, silver, invoice_id=invoice.invoice_id)
    payment.status = "success"
    billing.post_payment(db, payment, invoice)
    db.commit()

    requested = RefundService(db).request(str(payment.payment_id), "Charged twice", actor_id=str(uuid.uuid4()),
                                          reason_code="duplicate")
    RefundService(db).decide(requested["refund_id"], True, actor_id=str(uuid.uuid4()))

    refund = db.query(Refund).one()
    assert refund.status == "approved" and refund.reason_code == "duplicate"
    assert db.query(CreditNote).one().invoice_id == invoice.invoice_id
    assert ledger_balance(db, "cash") == Decimal("0.00")
    assert ledger_balance(db, "refunds") == Decimal("1000.00")
    assert_journals_balance(db)


# --- backfill ---

def test_backfill_turns_legacy_payments_into_invoices_and_ledger(db):
    from scripts.backfill_billing import _totals, backfill
    user, basic, silver, sub = make_world(db)
    paid = SubscriptionPayment(user_id=user.user_id, subscription_id=sub.subscription_id, amount=1000,
                               status="success", payment_method="mpesa", provider_reference="OLD1",
                               payment_metadata={"plan_id": str(silver.plan_id), "billing_cycle": "monthly"},
                               created_at=datetime.datetime(2026, 3, 1))
    grant = SubscriptionPayment(user_id=user.user_id, subscription_id=sub.subscription_id, amount=0,
                                status="success", payment_method="admin_override", created_at=datetime.datetime(2026, 3, 2))
    db.add_all([paid, grant])
    db.flush()
    refund = SubscriptionPayment(user_id=user.user_id, subscription_id=sub.subscription_id, amount=-1000,
                                 status="success", payment_method="admin_refund", transaction_type="refund",
                                 payment_metadata={"original_payment_id": str(paid.payment_id), "reason": "dup"},
                                 created_at=datetime.datetime(2026, 3, 5))
    db.add(refund)
    db.commit()

    counts = backfill(db)
    assert (counts["invoices"], counts["comps"], counts["refunds"]) == (1, 1, 1)
    totals = _totals(db)
    assert totals["ledger_cash_net"] == totals["payments_received"] - totals["payments_refunded"] == Decimal("0.00")
    assert totals["ledger_revenue"] == Decimal("1000.00") and totals["ledger_refunds"] == Decimal("1000.00")
    assert db.query(LedgerEntry).filter_by(source_type="payment").first().effective_at == datetime.datetime(2026, 3, 1)
    assert grant.transaction_type == "comp"
    assert_journals_balance(db)

    # Running it again changes nothing.
    again = backfill(db)
    assert (again["invoices"], again["comps"], again["refunds"], again["events"]) == (0, 0, 0, 0)
    assert db.query(LedgerEntry).count() == 4
