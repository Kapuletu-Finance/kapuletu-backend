"""
Phase 3 finance API: refunds need a second approver (from the finance screen or the approvals queue),
metrics come from paid invoices and the ledger with prior-period values, and the list / action / account
endpoints behave.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from finance_support import make_world, paid_invoice, pending_checkout

from models.billing import LedgerEntry, Refund, SubscriptionEvent
from models.employees import ApprovalRequest
from models.subscription import Plan, Subscription, SubscriptionPayment
from models.users import User
from services.finance import billing

NOW = datetime.datetime(2026, 10, 1, 12, 0)


def another_user(db, plan, name="Ben"):
    user = User(first_name=name, last_name="Treasurer", email=f"{uuid.uuid4().hex}@x.ke",
                phone_number=uuid.uuid4().hex[:12], slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}")
    db.add(user)
    db.flush()
    sub = Subscription(user_id=user.user_id, plan_id=plan.plan_id, status="active")
    db.add(sub)
    db.commit()
    return user, sub


# --- refunds: maker-checker ---

def test_requester_cannot_approve_their_own_refund(db):
    from services.admin.finance import FinanceError, RefundService
    user, basic, silver, sub = make_world(db)
    _, payment = paid_invoice(db, user, sub, silver, NOW)
    maker = str(uuid.uuid4())

    refund = RefundService(db).request(str(payment.payment_id), "Charged twice", actor_id=maker)
    assert refund["status"] == "requested"
    assert db.query(LedgerEntry).filter_by(account="refunds").count() == 0  # nothing moves yet

    with pytest.raises(FinanceError) as err:
        RefundService(db).decide(refund["refund_id"], True, actor_id=maker)
    assert err.value.status_code == 403
    db.rollback()

    decided = RefundService(db).decide(refund["refund_id"], False, actor_id=str(uuid.uuid4()), note="Not a duplicate")
    assert decided["status"] == "rejected"
    assert db.query(LedgerEntry).filter_by(account="refunds").count() == 0
    assert db.query(ApprovalRequest).one().status == "rejected"

    # A rejected request doesn't block a new one.
    assert RefundService(db).request(str(payment.payment_id), "Second look", actor_id=maker)["status"] == "requested"


def test_partial_refund_reduces_ledger_and_mrr(db):
    from services.admin.finance import FinanceMetricsService, RefundService
    user, basic, silver, sub = make_world(db)
    _, payment = paid_invoice(db, user, sub, silver, NOW - datetime.timedelta(days=5))

    refund = RefundService(db).request(str(payment.payment_id), "Outage week", actor_id=str(uuid.uuid4()),
                                       reason_code="service_issue", amount=Decimal("250"))
    RefundService(db).decide(refund["refund_id"], True, actor_id=str(uuid.uuid4()))

    assert billing.money(db.query(Refund).one().amount) == Decimal("250.00")
    refunds_posted = sum(Decimal(str(e.debit)) for e in db.query(LedgerEntry).filter_by(account="refunds"))
    assert refunds_posted == Decimal("250.00")
    assert FinanceMetricsService(db, now=NOW).mrr_at(NOW) == Decimal("750.00")


@pytest.fixture
def api(Session, db):
    """The finance and approvals routers, with the signed-in user switchable through `as_user`."""
    from common.database import get_db
    from services.admin import approvals_router
    from services.admin.finance import router as finance_router

    current = {"user_id": str(uuid.uuid4())}
    app = FastAPI()
    app.include_router(finance_router.router)
    app.include_router(approvals_router.router, prefix="/admin")

    def session_override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[finance_router.finance_officer] = lambda: dict(current)
    app.dependency_overrides[approvals_router.approver] = lambda: dict(current)
    app.dependency_overrides[approvals_router.submitter] = lambda: dict(current)

    def as_user(user_id: str):
        current["user_id"] = user_id

    return TestClient(app), as_user


def test_filtered_payment_and_invoice_register_exports(api, db):
    from services.admin.finance.invoices import InvoiceService

    http, _ = api
    user, basic, silver, sub = make_world(db)
    user.first_name = "=HYPERLINK(\"https://example.invalid\")"
    invoice, _ = paid_invoice(db, user, sub, silver, NOW)
    pending_checkout(db, user, sub, silver, ref="pending-checkout")
    service = InvoiceService(db)

    payments_csv = http.get(
        "/admin/finance/payments/export",
        params={"format": "csv", "status": "success", "type": "payment"},
    )
    assert payments_csv.status_code == 200, payments_csv.text
    assert "Kapuletu Payments Register" in payments_csv.text
    assert "'=HYPERLINK" in payments_csv.text
    assert "pending-checkout" not in payments_csv.text
    assert "attachment; filename=" in payments_csv.headers["content-disposition"]

    invoices_csv = http.get(
        "/admin/finance/invoices/export",
        params={"format": "csv", "status": "paid", "q": invoice.number},
    )
    assert invoices_csv.status_code == 200, invoices_csv.text
    assert invoice.number in invoices_csv.text
    assert "'=HYPERLINK" in invoices_csv.text

    for export in (
        service.export_payments,
        service.export_invoices,
    ):
        for fmt, magic in (("excel", b"PK"), ("pdf", b"%PDF")):
            content, _, filename = export(fmt)
            assert content.startswith(magic), fmt
            assert filename


def test_refund_approved_from_the_approvals_queue(api, db):
    http, as_user = api
    user, basic, silver, sub = make_world(db)
    _, payment = paid_invoice(db, user, sub, silver, NOW)
    maker, checker = str(uuid.uuid4()), str(uuid.uuid4())

    as_user(maker)
    res = http.post(f"/admin/finance/payments/{payment.payment_id}/refund", json={"reason": "Charged twice"})
    assert res.status_code == 200, res.text
    # A hand-made ISSUE_REFUND would have nothing to execute, so the generic queue refuses it.
    assert http.post("/admin/approvals", json={"action_type": "ISSUE_REFUND", "payload": {}}).status_code == 400

    queue = http.get("/admin/approvals?status=pending").json()
    assert [q["action_type"] for q in queue] == ["ISSUE_REFUND"]
    request_id = queue[0]["id"]
    assert http.post(f"/admin/approvals/{request_id}/resolve", json={"action": "approve"}).status_code == 400  # own

    as_user(checker)
    assert http.post(f"/admin/approvals/{request_id}/resolve", json={"action": "approve"}).json()["status"] == "approved"

    refunds = http.get("/admin/finance/refunds").json()["items"]
    assert refunds[0]["status"] == "approved" and refunds[0]["approved_by"] == checker
    db.expire_all()
    assert db.query(SubscriptionPayment).filter_by(transaction_type="refund").count() == 1


# --- metrics ---

def test_overview_metrics_and_previous_period(db):
    from services.admin.finance import FinanceMetricsService
    user_a, basic, silver, sub_a = make_world(db)
    user_b, sub_b = another_user(db, basic, "Ben")
    user_c, sub_c = another_user(db, basic, "Cate")

    # Previous window (Aug 2 - Sep 1): A and B pay. Current window (Sep 1 - Oct 1): A renews, C pays annually.
    paid_invoice(db, user_a, sub_a, silver, datetime.datetime(2026, 8, 5))
    paid_invoice(db, user_b, sub_b, silver, datetime.datetime(2026, 8, 10))
    paid_invoice(db, user_a, sub_a, silver, datetime.datetime(2026, 9, 4))
    paid_invoice(db, user_c, sub_c, silver, datetime.datetime(2026, 9, 20), cycle="annual")  # 11,000 / 12 per month

    out = FinanceMetricsService(db, now=NOW).overview(datetime.datetime(2026, 9, 1), NOW)
    m = {k: v["current"] for k, v in out["metrics"].items()}
    prev = {k: v["previous"] for k, v in out["metrics"].items()}

    assert m["mrr"] == pytest.approx(1000 + 11000 / 12, abs=0.01)
    assert m["arr"] == pytest.approx(m["mrr"] * 12, abs=0.1)
    assert m["paying_customers"] == 2  # A and C; B's month ran out on Sep 9
    assert m["new_paying_customers"] == 1  # C
    assert m["churned_customers"] == 1 and m["churn_rate_percent"] == 50.0  # B of {A, B}
    assert m["net_revenue"] == 12000.0  # 1,000 + 11,000 recognised from the ledger
    assert prev["mrr"] == 2000.0 and prev["paying_customers"] == 2 and prev["net_revenue"] == 2000.0
    assert out["metrics"]["net_revenue"]["change_pct"] == 500.0


def test_cohorts_and_revenue_flow(db):
    from services.admin.finance import FinanceMetricsService
    user_a, basic, silver, sub_a = make_world(db)
    user_b, sub_b = another_user(db, basic)
    paid_invoice(db, user_a, sub_a, silver, datetime.datetime(2026, 7, 3))
    paid_invoice(db, user_b, sub_b, silver, datetime.datetime(2026, 7, 8))
    paid_invoice(db, user_a, sub_a, silver, datetime.datetime(2026, 8, 2))  # only A renews

    metrics = FinanceMetricsService(db, now=NOW)
    july = next(c for c in metrics.cohort_retention() if c["cohort"] == "2026-07")
    assert july["users"] == 2 and july["retention"][:2] == [100, 50]

    flow = {row["period"]: row for row in metrics.revenue_flow("month", datetime.datetime(2026, 7, 1))}
    assert flow["2026-07"]["Silver"] == 2000.0 and flow["2026-08"]["Silver"] == 1000.0


# --- subscriptions, lists, accounts ---

def test_subscription_states_and_actions(db):
    from services.admin.finance import SubscriptionService
    user, basic, silver, sub = make_world(db)
    other, other_sub = another_user(db, basic)
    service = SubscriptionService(db)
    actor = str(uuid.uuid4())

    service.grant(user.slug, str(silver.plan_id), 10, actor_id=actor, reason="VIP")
    assert service.state_counts()["comp"] == 1 and service.state_counts()["free"] == 1
    assert service.list(state="comp")["items"][0]["user_id"] == str(user.user_id)
    assert service.list(q="Ben")["total"] == 1

    extended = service.extend(str(sub.subscription_id), 5, "Outage", actor)
    assert extended["days_remaining"] >= 14

    pro = Plan(code="gold", name="Gold", price=1500)
    db.add(pro)
    db.commit()
    assert service.change_plan(str(sub.subscription_id), str(pro.plan_id), "Upsell", actor)["plan_name"] == "Gold"
    canceled = service.cancel(str(sub.subscription_id), "Asked to stop", actor)
    assert canceled["state"] == "free" and canceled["end_date"] is None

    types = [e.type for e in db.query(SubscriptionEvent).filter_by(subscription_id=sub.subscription_id)
             .order_by(SubscriptionEvent.created_at)]
    assert types == ["comped", "extended", "plan_changed", "canceled"]


def test_payment_and_invoice_lists_filter(db):
    from services.admin.finance import InvoiceService
    user, basic, silver, sub = make_world(db)
    invoice, payment = paid_invoice(db, user, sub, silver, NOW, ref="ws_CO_find_me")
    db.add(SubscriptionPayment(user_id=user.user_id, subscription_id=sub.subscription_id, amount=1000,
                               status="failed", payment_method="mpesa", provider_reference="ws_CO_failed"))
    db.commit()
    service = InvoiceService(db)

    assert service.list_payments(status="failed")["total"] == 1
    assert service.list_payments(q="find_me")["items"][0]["invoice_number"] == invoice.number
    assert service.list_payments(type_="payment")["total"] == 2
    assert service.list_invoices(status="paid", q=invoice.number)["total"] == 1
    detail = service.get_invoice(str(invoice.invoice_id))
    assert detail["lines"][0]["kind"] == "plan" and detail["payments"][0]["payment_id"] == str(payment.payment_id)


def test_account_profile(db):
    from services.admin.finance import AccountService, RefundService
    user, basic, silver, sub = make_world(db)
    _, payment = paid_invoice(db, user, sub, silver, NOW)
    paid_invoice(db, user, sub, silver, NOW + datetime.timedelta(days=30))
    refund = RefundService(db).request(str(payment.payment_id), "Goodwill", actor_id=str(uuid.uuid4()),
                                       reason_code="goodwill", amount=Decimal("100"))
    RefundService(db).decide(refund["refund_id"], True, actor_id=str(uuid.uuid4()))

    profile = AccountService(db).profile(user.slug)
    assert profile["balance"] == {"lifetime_paid": 2000.0, "lifetime_refunded": 100.0, "lifetime_value": 1900.0,
                                  "currency": "KES"}
    assert len(profile["invoices"]) == 2 and len(profile["refunds"]) == 1
    assert profile["usage"]["groups"] == {"used": 0, "limit": 1, "percent": 0}
