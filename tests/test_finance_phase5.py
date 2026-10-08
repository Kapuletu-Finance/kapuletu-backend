"""
Phase 5: reconciliation against provider records, finance reports and their schedules, contribution volume
and ledger integrity, and the treasurer's own invoices.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from finance_support import make_world, paid_invoice

from models.campaign import Campaign
from models.finance_ops import ReconciliationItem, ReportSchedule
from models.group import Group
from models.subscription import SubscriptionPayment
from models.transaction import Transaction

NOW = datetime.datetime(2026, 10, 1, 12, 0)


def mpesa_csv(rows):
    """An org-portal statement: preamble lines, then the header, then rows (times are Nairobi time)."""
    lines = [
        "Organization Name:,KAPULETU LTD",
        "Time Period:,01-09-2026 - 30-09-2026",
        "",
        "Receipt No.,Completion Time,Initiation Time,Details,Transaction Status,Paid In,Withdrawn,Balance,Other Party Info",
    ]
    for receipt, at, amount, status in rows:
        lines.append(f'{receipt},{at},{at},Pay Bill Online,{status},"{amount}",,"10,000.00",2547****123 - ANN')
    return "\n".join(lines).encode()


def mpesa_payment(db, user, sub, amount, created_at, receipt=None):
    p = SubscriptionPayment(user_id=user.user_id, subscription_id=sub.subscription_id, amount=amount, currency="KES",
                            status="success", payment_method="mpesa", provider_reference=f"ws_CO_{uuid.uuid4().hex[:8]}",
                            created_at=created_at, payment_metadata={"receipt_number": receipt} if receipt else {})
    db.add(p)
    db.commit()
    return p


# --- reconciliation ---

def test_mpesa_statement_reconciliation(db):
    from services.admin.finance.reconciliation import ReconciliationService
    user, basic, silver, sub = make_world(db)
    by_receipt = mpesa_payment(db, user, sub, 1000, datetime.datetime(2026, 9, 5, 7, 0), receipt="RCP111")
    by_time = mpesa_payment(db, user, sub, 500, datetime.datetime(2026, 9, 10, 9, 0))  # polled: no receipt
    wrong_amount = mpesa_payment(db, user, sub, 1500, datetime.datetime(2026, 9, 12, 9, 0), receipt="RCP333")
    not_in_statement = mpesa_payment(db, user, sub, 2000, datetime.datetime(2026, 9, 20, 9, 0), receipt="RCP999")

    statement = mpesa_csv([
        ("RCP111", "05-09-2026 10:01:00", "1,000.00", "Completed"),
        ("RCP222", "10-09-2026 12:04:00", "500.00", "Completed"),  # 09:04 UTC, 4 minutes after checkout
        ("RCP333", "12-09-2026 12:01:00", "1,000.00", "Completed"),
        ("RCP444", "15-09-2026 08:00:00", "750.00", "Completed"),  # money we never recorded
        ("RCP555", "16-09-2026 08:00:00", "300.00", "Failed"),  # not completed: skipped
        ("RCP666", "25-09-2026 08:00:00", "100.00", "Completed"),  # keeps the period open past the 20th
    ])
    run = ReconciliationService(db).import_mpesa(statement, "sept.csv", actor_id=str(uuid.uuid4()))
    assert run["lines"] == 5

    items = {i.ref_key: i for i in db.query(ReconciliationItem)}
    assert items["RCP111"].status == "matched" and items["RCP111"].match_method == "receipt"
    assert items["RCP222"].status == "matched" and items["RCP222"].match_method == "amount_time"
    db.refresh(by_time)
    assert by_time.payment_metadata["receipt_number"] == "RCP222"  # gap filled from the statement
    assert items["RCP333"].status == "amount_mismatch" and items["RCP333"].payment_id == wrong_amount.payment_id
    assert items["RCP444"].status == "missing_in_ledger"
    assert items[f"payment:{not_in_statement.payment_id}"].status == "missing_in_statement"
    assert by_receipt.payment_id == items["RCP111"].payment_id

    service = ReconciliationService(db)
    assert service.open_counts() == {"amount_mismatch": 1, "missing_in_ledger": 2, "missing_in_statement": 1}

    # Importing the same statement again updates items instead of duplicating them.
    service.import_mpesa(statement, "sept.csv", actor_id=None)
    assert db.query(ReconciliationItem).count() == len(items)

    service.resolve(str(items["RCP444"].item_id), "resolved", "Manual paybill payment, extended by 30 days",
                    actor_id=str(uuid.uuid4()))
    assert service.open_counts()["missing_in_ledger"] == 1


def test_not_a_statement_is_refused(db):
    from services.admin.finance import FinanceError
    from services.admin.finance.reconciliation import ReconciliationService
    with pytest.raises(FinanceError):
        ReconciliationService(db).import_mpesa(b"name,amount\nann,100", "x.csv", actor_id=None)


def test_flutterwave_reconciliation_matches_by_checkout_reference(db, monkeypatch):
    import services.admin.finance.reconciliation as rec
    user, basic, silver, sub = make_world(db)
    ours = SubscriptionPayment(user_id=user.user_id, subscription_id=sub.subscription_id, amount=1000, currency="KES",
                               status="success", payment_method="flutterwave", provider_reference="kp-abc",
                               created_at=datetime.datetime(2026, 9, 30, 10, 0))
    db.add(ours)
    db.commit()
    monkeypatch.setattr(rec, "fetch_flutterwave_transactions", lambda start, end: [
        {"ref": "9001", "key": "kp-abc", "amount": Decimal("1000.00"), "currency": "KES",
         "at": datetime.datetime(2026, 9, 30, 10, 1), "counterparty": "ann@x.ke", "raw": {}},
        {"ref": "9002", "key": "kp-zzz", "amount": Decimal("500.00"), "currency": "USD",
         "at": datetime.datetime(2026, 9, 30, 11, 0), "counterparty": "bob@x.ke", "raw": {}},
    ])
    run = rec.ReconciliationService(db).pull_flutterwave(datetime.date(2026, 9, 30), datetime.date(2026, 9, 30))
    assert (run["matched"], run["mismatched"]) == (1, 1)
    assert db.query(ReconciliationItem).filter_by(ref_key="kp-zzz").one().status == "missing_in_ledger"


# --- reports ---

def test_revenue_and_tax_reports_render_in_every_format(db):
    from services.admin.finance.reports import ReportService
    user, basic, silver, sub = make_world(db)
    paid_invoice(db, user, sub, silver, datetime.datetime(2026, 8, 10))
    paid_invoice(db, user, sub, silver, datetime.datetime(2026, 9, 10), cycle="annual")

    service = ReportService(db)
    report = service.build("revenue", datetime.datetime(2026, 8, 1), datetime.datetime(2026, 10, 1))
    by_month = report.tables[0].rows
    assert by_month[0][:2] == ["Aug 2026", 1000.0] and by_month[1][:2] == ["Sep 2026", 11000.0]
    assert by_month[-1][0] == "Total" and by_month[-1][3] == 12000.0  # net revenue
    assert report.tables[1].rows == [["Silver", 12000.0]]

    tax = service.build("tax", datetime.datetime(2026, 8, 1), datetime.datetime(2026, 10, 1))
    assert tax.tables[0].rows[-1] == ["Total", 2, 12000.0, 0.0]

    for fmt, magic in (("csv", b"\xef\xbb\xbfRevenue"), ("excel", b"PK"), ("pdf", b"%PDF")):
        content, _, filename = service.render(report, fmt, prepared_by="Test")
        assert content.startswith(magic), fmt
        assert filename


def test_payment_method_and_receivables_reports(db):
    from services.admin.finance.reports import ReportService
    from services.finance import billing
    user, basic, silver, sub = make_world(db)
    paid_invoice(db, user, sub, silver, datetime.datetime(2026, 9, 3))
    db.add(SubscriptionPayment(user_id=user.user_id, subscription_id=sub.subscription_id, amount=1000, status="failed",
                               payment_method="mpesa", created_at=datetime.datetime(2026, 9, 4)))
    billing.create_invoice(db, user.user_id, sub.subscription_id, billing.build_quote(db, silver),
                           issued_at=datetime.datetime(2026, 9, 1))  # left open
    db.commit()

    service = ReportService(db)
    methods = service.build("payment_methods", datetime.datetime(2026, 9, 1), datetime.datetime(2026, 10, 1))
    assert methods.tables[0].rows == [["mpesa", 2, 1, 1, 50.0, 1000.0]]
    aged = service.build("receivables", datetime.datetime(2026, 9, 1), datetime.datetime(2026, 10, 1))
    assert [row[4] for row in aged.tables[0].rows] == ["8–30 days"]


def test_schedule_periods_and_sending_once(db, monkeypatch):
    import services.notifications.tasks as tasks
    from services.admin.finance.schedules import ScheduleService, last_complete_period

    # Thursday 1 Oct 2026, 12:00 UTC → last full week Mon 21 – Sun 27 Sep, last full month September (Nairobi days).
    assert last_complete_period("weekly", NOW) == (datetime.datetime(2026, 9, 20, 21), datetime.datetime(2026, 9, 27, 21))
    assert last_complete_period("monthly", NOW) == (datetime.datetime(2026, 8, 31, 21), datetime.datetime(2026, 9, 30, 21))

    sent = []
    monkeypatch.setattr(tasks, "send_email_task", lambda log_id, to, subject, body, attachments=None:
                        sent.append((to, subject, attachments[0]["filename"])))
    service = ScheduleService(db)
    service.create({"report_type": "revenue", "frequency": "monthly", "format": "csv",
                    "recipients": ["CFO@kapuletu.co.ke", "ops@kapuletu.co.ke"]}, actor_id=str(uuid.uuid4()))

    assert service.send_due(NOW) == 1
    assert [s[0] for s in sent] == ["cfo@kapuletu.co.ke", "ops@kapuletu.co.ke"]
    assert sent[0][2].endswith(".csv") and "Sep 2026" in sent[0][1]
    assert service.send_due(NOW + datetime.timedelta(days=3)) == 0  # September already went out
    assert db.query(ReportSchedule).one().last_period_end == datetime.datetime(2026, 9, 30, 21)


# --- contribution volume & integrity ---

def test_volume_and_integrity(db):
    from services.admin.finance.volume import VolumeService
    from services.finance.ledger_service import LedgerService
    user, basic, silver, sub = make_world(db)
    group = Group(owner_id=user.user_id, group_name="Harambee Youth")
    db.add(group)
    db.flush()
    sealer = LedgerService(db)
    txns = []
    for i, (amount, method) in enumerate([(500, "M-Pesa"), (1500, "M-Pesa"), (1000, "Cash")]):
        t = Transaction(owner_id=user.user_id, group_id=group.group_id, transaction_code=f"T{i}", amount=amount,
                        status="approved", payment_method=method, created_at=datetime.datetime(2026, 9, 10 + i))
        db.add(t)
        db.flush()
        t.ledger_hash = sealer._recalculate_hash(t)
        txns.append(t)
    db.commit()

    volume = VolumeService(db).summary(datetime.datetime(2026, 9, 1), datetime.datetime(2026, 10, 1))
    assert volume["totals"] == {"contributions": 3, "amount": 3000.0, "active_groups": 1, "active_treasurers": 1,
                                "average_contribution": 1000.0}
    assert volume["by_method"][0] == {"method": "M-Pesa", "contributions": 2, "amount": 2000.0}
    assert volume["top_groups"][0]["group_name"] == "Harambee Youth"

    txns[1].amount = Decimal("15000")  # tampered after sealing
    db.commit()
    check = VolumeService(db).integrity(datetime.datetime(2026, 9, 1), datetime.datetime(2026, 10, 1))
    assert (check["checked"], check["intact"], check["unsealed"]) == (3, 2, 0)
    assert [t["transaction_code"] for t in check["tampered"]] == ["T1"]


def test_contribution_register_filters_paginates_and_exports(db):
    from services.admin.finance.volume import VolumeService

    user, basic, silver, sub = make_world(db)
    group = Group(owner_id=user.user_id, group_name="Harambee Youth")
    db.add(group)
    db.flush()
    campaign = Campaign(campaign_id=uuid.uuid4(), group_id=group.group_id, title="School Fees")
    db.add(campaign)
    db.flush()
    first = Transaction(
        owner_id=user.user_id, group_id=group.group_id, campaign_id=campaign.campaign_id,
        transaction_code="RCP001", amount=500, sender_name="Mary Wanjiku", sender_phone="254700000001",
        payment_method="M-Pesa", status="approved", created_at=datetime.datetime(2026, 9, 10),
    )
    second = Transaction(
        owner_id=user.user_id, group_id=group.group_id, transaction_code="RCP002", amount=300,
        sender_name='=HYPERLINK("https://example.invalid")', payment_method="Cash", status="approved",
        created_at=datetime.datetime(2026, 9, 11),
    )
    pending = Transaction(
        owner_id=user.user_id, group_id=group.group_id, transaction_code="RCP003", amount=200,
        sender_name="Not Approved", payment_method="Cash", status="pending",
        created_at=datetime.datetime(2026, 9, 12),
    )
    db.add_all([first, second, pending])
    db.commit()

    service = VolumeService(db)
    start, end = datetime.datetime(2026, 9, 1), datetime.datetime(2026, 10, 1)
    result = service.list_contributions(start, end, contributor="Mary", method="M-Pesa")
    assert result["total"] == 1 and result["total_amount"] == 500
    assert result["items"][0]["group_name"] == "Harambee Youth"
    assert result["items"][0]["campaign_name"] == "School Fees"
    assert result["items"][0]["treasurer_name"] == "Ann Treasurer"

    all_rows = service.list_contributions(start, end, page=1, limit=1)
    assert all_rows["total"] == 2 and len(all_rows["items"]) == 1
    assert all_rows["total_amount"] == 800

    csv_bytes, _, csv_name = service.export_statement(start, end, "csv", contributor="Mary")
    assert b"Mary Wanjiku" in csv_bytes and csv_name.endswith(".csv")
    all_csv, _, _ = service.export_statement(start, end, "csv")
    assert b"'=HYPERLINK" in all_csv
    excel_bytes, _, excel_name = service.export_statement(start, end, "excel", contributor="Mary")
    assert excel_bytes.startswith(b"PK") and excel_name.endswith(".xlsx")
    pdf_bytes, _, pdf_name = service.export_statement(start, end, "pdf", contributor="Mary")
    assert pdf_bytes.startswith(b"%PDF") and pdf_name.endswith(".pdf")


def test_admin_contribution_statement_routes(Session, db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from common.database import get_db
    from services.admin.finance import router as finance_router

    user, basic, silver, sub = make_world(db)
    group = Group(owner_id=user.user_id, group_name="Harambee Youth")
    db.add(group)
    db.flush()
    db.add(Transaction(
        owner_id=user.user_id, group_id=group.group_id, transaction_code="RCP100", amount=125,
        sender_name="Mary Wanjiku", sender_phone="254700000001", payment_method="M-Pesa",
        status="approved", created_at=datetime.datetime(2026, 9, 10),
    ))
    db.commit()

    app = FastAPI()
    app.include_router(finance_router.router)

    def session_override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[finance_router.finance_officer] = lambda: {"user_id": str(uuid.uuid4())}
    http = TestClient(app)
    params = {"from": "2026-09-01T00:00:00", "to": "2026-10-01T00:00:00", "contributor": "Mary"}

    listing = http.get("/admin/finance/contributions", params=params)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["transaction_code"] == "RCP100"

    statement = http.get("/admin/finance/contributions/export", params={**params, "format": "csv"})
    assert statement.status_code == 200
    assert b"Mary Wanjiku" in statement.content
    assert statement.headers["content-disposition"].endswith(".csv\"")


# --- treasurer invoices ---

def test_treasurer_sees_own_invoices_and_downloads_pdf(Session, db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from common.auth_dependencies import get_verified_user
    from common.database import get_db
    from services.finance import checkout_router

    user, basic, silver, sub = make_world(db)
    invoice, _ = paid_invoice(db, user, sub, silver, NOW)

    app = FastAPI()
    app.include_router(checkout_router.router, prefix="/finance")

    def session_override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_verified_user] = lambda: {"sub": str(user.user_id)}
    http = TestClient(app)

    invoices = http.get("/finance/invoices").json()
    assert [i["number"] for i in invoices] == [invoice.number] and invoices[0]["lines"][0]["amount"] == 1000.0
    pdf = http.get(f"/finance/invoices/{invoice.invoice_id}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    usage = http.get("/finance/my-subscription").json()["usage"]
    assert usage["transactions"] == "0/100"

    app.dependency_overrides[get_verified_user] = lambda: {"sub": str(uuid.uuid4())}
    assert http.get(f"/finance/invoices/{invoice.invoice_id}/pdf").status_code == 404  # not theirs


def test_finance_officer_can_download_treasurer_invoice_pdf(Session, db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from common.database import get_db
    from services.admin.finance import router as finance_router

    user, basic, silver, sub = make_world(db)
    invoice, _ = paid_invoice(db, user, sub, silver, NOW)

    app = FastAPI()
    app.include_router(finance_router.router)

    def session_override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[finance_router.finance_officer] = lambda: {"user_id": str(uuid.uuid4())}
    response = TestClient(app).get(f"/admin/finance/invoices/{invoice.invoice_id}/pdf")

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert invoice.number in response.headers["content-disposition"]
