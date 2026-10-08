"""
Phase 1 finance hardening: payments are only fulfilled against our own checkout at the right amount,
refunds happen once, admin changes are audited, and lapsed subscriptions get a grace period.
Runs on in-memory SQLite with just the tables these flows touch.
"""
import datetime
import uuid

import pytest
from finance_support import make_world, pending_checkout

from models.audit_log import AuditLog
from models.subscription import SubscriptionPayment
from models.system_config import SystemConfig

# --- fulfilment ---

def test_unknown_checkout_is_not_fulfilled(db):
    from services.finance.fulfillment import FulfillmentService
    make_world(db)
    assert FulfillmentService(db).process_success("forged-id", "RCPT", 1000, "KES") is False


def test_underpayment_is_refused_and_audited(db):
    from services.finance.fulfillment import FulfillmentService
    user, basic, silver, sub = make_world(db)
    payment = pending_checkout(db, user, sub, silver)

    assert FulfillmentService(db).process_success("ws_CO_1", "RCPT", 1, "KES") is False

    db.refresh(payment), db.refresh(sub)
    assert payment.status == "failed"
    assert payment.payment_metadata["failure_reason"] == "amount_mismatch"
    assert sub.plan_id == basic.plan_id
    assert db.query(AuditLog).filter_by(action="PAYMENT_AMOUNT_MISMATCH").count() == 1


def test_wrong_currency_is_refused(db):
    from services.finance.fulfillment import FulfillmentService
    user, basic, silver, sub = make_world(db)
    pending_checkout(db, user, sub, silver)
    assert FulfillmentService(db).process_success("ws_CO_1", "RCPT", 1000, "USD") is False


def test_full_payment_upgrades_once(db):
    from services.finance.fulfillment import FulfillmentService
    user, basic, silver, sub = make_world(db)
    payment = pending_checkout(db, user, sub, silver)

    assert FulfillmentService(db).process_success("ws_CO_1", "RCPT", 1000, "KES") is True
    db.refresh(sub)
    first_end = sub.end_date
    assert sub.plan_id == silver.plan_id
    assert 29 <= (first_end - datetime.datetime.utcnow()).days <= 30

    # The webhook and the status poller both report success: the period must not be extended twice.
    assert FulfillmentService(db).process_success("ws_CO_1", "RCPT", 1000, "KES") is True
    db.refresh(sub), db.refresh(payment)
    assert sub.end_date == first_end
    assert payment.status == "success"
    assert payment.payment_metadata["receipt_number"] == "RCPT"


def test_provider_failure_marks_checkout_failed(db):
    from services.finance.fulfillment import FulfillmentService
    user, basic, silver, sub = make_world(db)
    payment = pending_checkout(db, user, sub, silver)
    assert FulfillmentService(db).process_failure("ws_CO_1", "Request cancelled by user") is True
    db.refresh(payment)
    assert payment.status == "failed"


# --- M-Pesa callback token ---

def test_mpesa_callback_requires_token(monkeypatch):
    from services.finance.providers.mpesa import MpesaProvider
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "s3cret")
    monkeypatch.setenv("MPESA_CALLBACK_URL", "https://api.example/finance/webhooks/mpesa")
    provider = MpesaProvider()
    assert provider.verify_webhook("{}", {}, {"token": "s3cret"}) is True
    assert provider.verify_webhook("{}", {}, {"token": "nope"}) is False
    assert provider.verify_webhook("{}", {}, {}) is False
    assert provider._callback_url_with_token() == "https://api.example/finance/webhooks/mpesa?token=s3cret"


# --- refunds ---

def test_refund_happens_once_and_is_audited(db):
    from services.admin.finance import FinanceError, RefundService
    user, basic, silver, sub = make_world(db)
    payment = pending_checkout(db, user, sub, silver)
    payment.status = "success"
    db.commit()
    maker, checker = str(uuid.uuid4()), str(uuid.uuid4())

    requested = RefundService(db).request(str(payment.payment_id), "Charged twice", actor_id=maker)
    RefundService(db).decide(requested["refund_id"], True, actor_id=checker)
    refund_row = db.query(SubscriptionPayment).filter_by(transaction_type="refund").one()
    assert refund_row.amount == -1000

    with pytest.raises(FinanceError) as again:
        RefundService(db).request(str(payment.payment_id), "Charged twice", actor_id=maker)
    assert again.value.status_code == 409

    with pytest.raises(FinanceError):
        RefundService(db).request(str(refund_row.payment_id), "Refund the refund", actor_id=maker)

    requested_log = db.query(AuditLog).filter_by(action="REFUND_REQUESTED").one()
    approved_log = db.query(AuditLog).filter_by(action="REFUND_APPROVED").one()
    assert str(requested_log.actor_id) == maker and requested_log.details["reason"] == "Charged twice"
    assert str(approved_log.actor_id) == checker


def test_refund_of_pending_payment_is_refused(db):
    from services.admin.finance import FinanceError, RefundService
    user, basic, silver, sub = make_world(db)
    payment = pending_checkout(db, user, sub, silver)
    with pytest.raises(FinanceError):
        RefundService(db).request(str(payment.payment_id), "nope", actor_id=str(uuid.uuid4()))


# --- overrides and plans ---

def test_override_accepts_slug_and_is_audited(db):
    from services.admin.finance import FinanceError, SubscriptionService
    user, basic, silver, sub = make_world(db)
    SubscriptionService(db).grant(user.slug, str(silver.plan_id), 14, actor_id=str(uuid.uuid4()), reason="VIP")
    db.refresh(sub)
    assert sub.plan_id == silver.plan_id
    log = db.query(AuditLog).filter_by(action="SUBSCRIPTION_OVERRIDDEN").one()
    assert log.details["before"]["plan_id"] == str(basic.plan_id)

    with pytest.raises(FinanceError) as missing:
        SubscriptionService(db).grant(user.slug, str(uuid.uuid4()), 14)
    assert missing.value.status_code == 404


def test_plan_price_change_is_audited(db):
    from services.admin.finance import PlanService
    user, basic, silver, sub = make_world(db)
    PlanService(db).update(str(silver.plan_id), {"price": 1200}, actor_id=str(uuid.uuid4()))
    log = db.query(AuditLog).filter_by(action="PLAN_UPDATED").one()
    # The annual price follows the monthly one (x11 by default) unless it's set explicitly.
    assert log.details["changes"] == {
        "month_price": {"from": "1000.00", "to": "1200.00"},
        "year_price": {"from": "11000.00", "to": "13200.00"},
    }


# --- expiry sweep ---

def test_lapsed_subscription_gets_grace_then_downgrades(Session, db, monkeypatch):
    import common.system_config_service as config_service
    import services.subscriptions.expiry_worker as worker

    monkeypatch.setattr(worker, "SessionLocal", Session)
    sent = []
    monkeypatch.setattr(worker, "send_real_reminder", lambda user, plan, days: sent.append(days))

    user, basic, silver, sub = make_world(db, sub_end=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    sub.plan_id = silver.plan_id
    db.commit()

    # First ever run: a long-lapsed user is told, not downgraded.
    worker.run_expiry_sweep()
    db.refresh(sub)
    assert sub.plan_id == silver.plan_id
    assert sent == [0]

    # Once the grace period (default 7 days) has passed since the first run, they move to the free tier.
    started = (datetime.datetime.utcnow() - datetime.timedelta(days=8)).isoformat()
    db.query(SystemConfig).filter_by(config_key=worker.STARTED_AT_KEY).update({"config_value": started})
    db.commit()
    config_service._CONFIG_CACHE.clear()

    worker.run_expiry_sweep()
    db.expire_all()
    assert sub.plan_id == basic.plan_id and sub.end_date is None
    assert db.query(AuditLog).filter_by(action="SUBSCRIPTION_EXPIRED").count() == 1
