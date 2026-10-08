"""
/admin/finance: everything the finance officer works with. Every route requires the manage_finance permission;
refunds additionally need a second person to approve them.
"""
import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from common.auth_dependencies import require_permissions
from common.database import get_db
from services.admin.analytics_engine import FinancialAnalyticsEngine
from services.admin.finance_schemas import (
    BillingSettingsIn,
    FlutterwavePullIn,
    PlanCreateIn,
    PlanUpdateIn,
    ReconciliationResolveIn,
    RefundDecisionIn,
    RefundIn,
    RefundRequestIn,
    ReportScheduleIn,
    ReportScheduleUpdateIn,
    SubscriptionActionIn,
    SubscriptionOverrideForUserIn,
)

from . import (
    AccountService,
    FinanceError,
    FinanceMetricsService,
    InvoiceService,
    PlanService,
    RefundService,
    SubscriptionService,
)
from .reconciliation import ReconciliationService
from .reports import ReportService
from .schedules import ScheduleService, last_complete_period
from .volume import VolumeService

router = APIRouter(prefix="/admin/finance", tags=["11b. Admin Finance"])

finance_officer = require_permissions(["manage_finance"])
User = Dict[str, Any]


def _http(e: FinanceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


def _actor(user: User) -> Optional[str]:
    return user.get("user_id") or user.get("sub")


# --- overview & analytics ---

@router.get("/overview", summary="Finance KPIs for a period, with the previous period")
async def get_overview(
    date_from: Optional[datetime.datetime] = Query(None, alias="from"),
    date_to: Optional[datetime.datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    try:
        out = FinanceMetricsService(db).overview(date_from, date_to)
    except FinanceError as e:
        raise _http(e)
    out["subscriptions"] = SubscriptionService(db).state_counts()
    return out


@router.get("/analytics/health-metrics", summary="Headline KPIs (last 30 days)")
async def get_health_metrics(db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    """Kept for the current dashboard; /overview has the full set with prior-period values."""
    metrics = FinanceMetricsService(db).overview()["metrics"]
    states = SubscriptionService(db).state_counts()
    return {
        "mrr": metrics["mrr"]["current"],
        "active_subscribers": metrics["paying_customers"]["current"],
        "trial_subscribers": states["trial"],
        "churn_rate_percent": metrics["churn_rate_percent"]["current"],
        "generated_at": datetime.datetime.utcnow().isoformat(),
    }


@router.get("/analytics/revenue-flow", summary="Invoiced revenue by plan per month or week")
async def get_revenue_flow(
    interval: str = Query("month", description="week or month"),
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    try:
        return FinanceMetricsService(db).revenue_flow(interval=interval)
    except FinanceError as e:
        raise _http(e)


@router.get("/analytics/mrr-series", summary="MRR and paying customers at the start of each month")
async def get_mrr_series(
    months: int = Query(12, ge=1, le=36), db: Session = Depends(get_db), _: User = Depends(finance_officer),
):
    return FinanceMetricsService(db).mrr_series(months)


@router.get("/analytics/cohorts", summary="Retention by month of first payment")
async def get_cohort_retention(db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    return FinanceMetricsService(db).cohort_retention()


@router.get("/analytics/export", summary="Export Financial Data")
async def export_financial_data(
    format: str = Query("csv", description="Export format (csv, excel, pdf)"),
    start_date: str = Query(None, description="Start date in ISO format"),
    end_date: str = Query(None, description="End date in ISO format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(finance_officer),
):
    engine = FinancialAnalyticsEngine(db)
    file_data, mime_type = engine.generate_export(
        start_date=datetime.datetime.fromisoformat(start_date) if start_date else None,
        end_date=datetime.datetime.fromisoformat(end_date) if end_date else None,
        format=format,
        prepared_by=f"{current_user.get('given_name') or ''} {current_user.get('family_name') or ''}".strip(),
        actor_id=_actor(current_user),
    )
    extension = {"excel": "xlsx", "pdf": "pdf"}.get(format, "csv")
    response = StreamingResponse(iter([file_data]), media_type=mime_type)
    response.headers["Content-Disposition"] = (
        f"attachment; filename=financial_export_{datetime.datetime.utcnow().strftime('%Y%m%d')}.{extension}"
    )
    return response


# --- plans & billing rules ---

@router.get("/plans", summary="List Subscription Plans")
async def list_plans(db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    return PlanService(db).list()


@router.get("/plans/{plan_id}", summary="Get Subscription Plan Details")
async def get_plan(plan_id: str, db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    plan = PlanService(db).get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/plans", summary="Create Subscription Plan")
async def create_plan(payload: PlanCreateIn, db: Session = Depends(get_db), current_user: User = Depends(finance_officer)):
    try:
        plan_id = PlanService(db).create(payload.model_dump(), actor_id=_actor(current_user))
    except FinanceError as e:
        raise _http(e)
    return {"message": "Plan created", "id": plan_id}


@router.patch("/plans/{plan_id}", summary="Update Subscription Plan")
async def update_plan(plan_id: str, payload: PlanUpdateIn, db: Session = Depends(get_db),
                      current_user: User = Depends(finance_officer)):
    try:
        plan = PlanService(db).update(plan_id, payload.model_dump(exclude_unset=True), actor_id=_actor(current_user))
    except FinanceError as e:
        raise _http(e)
    return {"message": "Plan updated successfully", "plan": plan}


@router.post("/plans/{plan_id}/archive", summary="Archive Subscription Plan")
async def archive_plan(plan_id: str, db: Session = Depends(get_db), current_user: User = Depends(finance_officer)):
    try:
        return PlanService(db).set_archived(plan_id, True, actor_id=_actor(current_user))
    except FinanceError as e:
        raise _http(e)


@router.post("/plans/{plan_id}/restore", summary="Restore Archived Plan")
async def restore_plan(plan_id: str, db: Session = Depends(get_db), current_user: User = Depends(finance_officer)):
    try:
        return PlanService(db).set_archived(plan_id, False, actor_id=_actor(current_user))
    except FinanceError as e:
        raise _http(e)


@router.get("/settings", summary="Get Billing Rules")
async def get_billing_settings(db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    return PlanService(db).get_settings()


@router.put("/settings", summary="Update Billing Rules")
async def update_billing_settings(payload: BillingSettingsIn, db: Session = Depends(get_db),
                                  current_user: User = Depends(finance_officer)):
    return PlanService(db).update_settings(payload.model_dump(exclude_unset=True), actor_id=_actor(current_user))


# --- subscriptions ---

@router.get("/subscriptions", summary="List subscriptions")
async def list_subscriptions(
    state: Optional[str] = Query(None, description="paid, trial, comp, lapsed or free"),
    plan_id: Optional[str] = None,
    renews_before: Optional[datetime.datetime] = None,
    q: Optional[str] = Query(None, description="Name, email, phone or slug"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    try:
        return SubscriptionService(db).list(state, plan_id, renews_before, q, page, limit)
    except FinanceError as e:
        raise _http(e)


@router.get("/subscriptions/summary", summary="Subscriptions per state")
async def subscription_summary(db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    return SubscriptionService(db).state_counts()


@router.post("/subscriptions/{subscription_id}/actions", summary="Extend, change plan or cancel a subscription")
async def subscription_action(subscription_id: str, payload: SubscriptionActionIn, db: Session = Depends(get_db),
                              current_user: User = Depends(finance_officer)):
    service, actor = SubscriptionService(db), _actor(current_user)
    try:
        if payload.action == "extend":
            if not payload.days:
                raise FinanceError("days is required to extend")
            return service.extend(subscription_id, payload.days, payload.reason, actor)
        if payload.action == "change_plan":
            if not payload.plan_id:
                raise FinanceError("plan_id is required to change plan")
            return service.change_plan(subscription_id, payload.plan_id, payload.reason, actor)
        return service.cancel(subscription_id, payload.reason, actor)
    except FinanceError as e:
        raise _http(e)


@router.post("/payments/override", summary="Grant a plan without payment")
async def override_subscription(payload: SubscriptionOverrideForUserIn, db: Session = Depends(get_db),
                                current_user: User = Depends(finance_officer)):
    try:
        SubscriptionService(db).grant(payload.user_id, payload.plan_id, payload.duration, payload.is_trial,
                                      actor_id=_actor(current_user), reason=payload.reason)
    except FinanceError as e:
        raise _http(e)
    return {"message": "Override applied"}


# --- invoices & payments ---

@router.get("/invoices", summary="List invoices")
async def list_invoices(
    status: Optional[str] = None,
    q: Optional[str] = Query(None, description="Invoice number, or customer name, email, phone"),
    date_from: Optional[datetime.datetime] = Query(None, alias="from"),
    date_to: Optional[datetime.datetime] = Query(None, alias="to"),
    user_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    try:
        return InvoiceService(db).list_invoices(status, q, date_from, date_to, user_id, page, limit)
    except FinanceError as e:
        raise _http(e)


@router.get("/invoices/{invoice_id}/pdf", summary="Download an official invoice PDF")
async def download_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    try:
        content, filename = InvoiceService(db).invoice_pdf(invoice_id)
    except (FinanceError, ValueError) as e:
        raise _http(e if isinstance(e, FinanceError) else FinanceError("Invoice not found", 404))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/invoices/{invoice_id}", summary="Invoice with lines, payments and credit notes")
async def get_invoice(invoice_id: str, db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    try:
        return InvoiceService(db).get_invoice(invoice_id)
    except (FinanceError, ValueError) as e:
        raise _http(e if isinstance(e, FinanceError) else FinanceError("Invoice not found", 404))


@router.get("/payments", summary="List payments")
async def list_payments(
    status: Optional[str] = None,
    provider: Optional[str] = Query(None, description="mpesa, flutterwave, admin_override, admin_refund"),
    type: Optional[str] = Query(None, description="payment, refund or comp"),
    q: Optional[str] = Query(None, description="Receipt / checkout reference, invoice number, or customer"),
    date_from: Optional[datetime.datetime] = Query(None, alias="from"),
    date_to: Optional[datetime.datetime] = Query(None, alias="to"),
    user_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    try:
        return InvoiceService(db).list_payments(status, provider, type, q, date_from, date_to, user_id, page, limit)
    except FinanceError as e:
        raise _http(e)


@router.get("/payments/{payment_id}", summary="Payment with its invoice, refund and raw provider callbacks")
async def get_payment(payment_id: str, db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    try:
        return InvoiceService(db).get_payment(payment_id)
    except (FinanceError, ValueError) as e:
        raise _http(e if isinstance(e, FinanceError) else FinanceError("Payment not found", 404))


# --- refunds (maker-checker) ---

@router.get("/refunds", summary="List refunds")
async def list_refunds(
    status: Optional[str] = Query(None, description="requested, approved, rejected"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    try:
        return RefundService(db).list(status, page=page, limit=limit)
    except FinanceError as e:
        raise _http(e)


@router.post("/refunds", summary="Request a refund (needs a second approver)")
async def request_refund(payload: RefundRequestIn, db: Session = Depends(get_db),
                         current_user: User = Depends(finance_officer)):
    try:
        return RefundService(db).request(payload.payment_id, payload.reason, _actor(current_user),
                                         payload.reason_code, payload.amount)
    except FinanceError as e:
        raise _http(e)


@router.post("/payments/{payment_id}/refund", summary="Request a full refund for a payment")
async def request_payment_refund(payment_id: str, payload: RefundIn, db: Session = Depends(get_db),
                                 current_user: User = Depends(finance_officer)):
    try:
        refund = RefundService(db).request(payment_id, payload.reason, _actor(current_user), payload.reason_code)
    except FinanceError as e:
        raise _http(e)
    return {"message": "Refund requested; a second finance approver must approve it", "refund": refund}


@router.post("/refunds/{refund_id}/approve", summary="Approve a refund requested by someone else")
async def approve_refund(refund_id: str, payload: RefundDecisionIn, db: Session = Depends(get_db),
                         current_user: User = Depends(finance_officer)):
    try:
        return RefundService(db).decide(refund_id, True, _actor(current_user), payload.note)
    except FinanceError as e:
        db.rollback()
        raise _http(e)


@router.post("/refunds/{refund_id}/reject", summary="Reject a refund requested by someone else")
async def reject_refund(refund_id: str, payload: RefundDecisionIn, db: Session = Depends(get_db),
                        current_user: User = Depends(finance_officer)):
    try:
        return RefundService(db).decide(refund_id, False, _actor(current_user), payload.note)
    except FinanceError as e:
        db.rollback()
        raise _http(e)


# --- treasurer financial profile ---

@router.get("/accounts/{identifier}", summary="A treasurer's billing account and plan usage")
async def get_account(identifier: str, db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    try:
        return AccountService(db).profile(identifier)
    except FinanceError as e:
        raise _http(e)


# --- reports ---

MAX_STATEMENT_BYTES = 10 * 1024 * 1024


@router.get("/reports", summary="Available finance reports")
async def list_reports(_: User = Depends(finance_officer)):
    return ReportService.catalogue()


@router.get("/reports/schedules", summary="Scheduled report emails")
async def list_report_schedules(db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    return ScheduleService(db).list()


@router.post("/reports/schedules", summary="Email a report every week or month")
async def create_report_schedule(payload: ReportScheduleIn, db: Session = Depends(get_db),
                                 current_user: User = Depends(finance_officer)):
    try:
        return ScheduleService(db).create(payload.model_dump(), _actor(current_user))
    except FinanceError as e:
        raise _http(e)


@router.patch("/reports/schedules/{schedule_id}", summary="Change a report schedule")
async def update_report_schedule(schedule_id: str, payload: ReportScheduleUpdateIn, db: Session = Depends(get_db),
                                 current_user: User = Depends(finance_officer)):
    try:
        return ScheduleService(db).update(schedule_id, payload.model_dump(exclude_unset=True), _actor(current_user))
    except FinanceError as e:
        raise _http(e)


@router.delete("/reports/schedules/{schedule_id}", summary="Stop a report schedule")
async def delete_report_schedule(schedule_id: str, db: Session = Depends(get_db),
                                 current_user: User = Depends(finance_officer)):
    try:
        ScheduleService(db).delete(schedule_id, _actor(current_user))
    except FinanceError as e:
        raise _http(e)
    return {"message": "Schedule removed"}


@router.post("/reports/schedules/{schedule_id}/send", summary="Send a scheduled report now (last full period)")
async def send_report_schedule(schedule_id: str, db: Session = Depends(get_db),
                               current_user: User = Depends(finance_officer)):
    try:
        return ScheduleService(db).send_now(schedule_id, _actor(current_user))
    except FinanceError as e:
        raise _http(e)


@router.get("/reports/{key}", summary="Build a report (JSON for screen, or csv / excel / pdf download)")
async def get_report(
    key: str,
    date_from: Optional[datetime.datetime] = Query(None, alias="from"),
    date_to: Optional[datetime.datetime] = Query(None, alias="to"),
    format: str = Query("json", description="json, csv, excel or pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(finance_officer),
):
    if not date_from or not date_to:
        default_start, default_end = last_complete_period("monthly", datetime.datetime.utcnow())
        date_from, date_to = date_from or default_start, date_to or default_end
    service = ReportService(db)
    try:
        report = service.build(key, date_from, date_to)
        if format == "json":
            return report.as_dict()
        prepared_by = f"{current_user.get('given_name') or ''} {current_user.get('family_name') or ''}".strip()
        content, mime, filename = service.render(report, format, prepared_by or None, _actor(current_user))
    except FinanceError as e:
        raise _http(e)
    return Response(content=content, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# --- reconciliation ---

@router.get("/reconciliation/summary", summary="Open mismatches by kind")
async def reconciliation_summary(db: Session = Depends(get_db), _: User = Depends(finance_officer)):
    return ReconciliationService(db).open_counts()


@router.post("/reconciliation/mpesa", summary="Reconcile an M-Pesa org-portal statement (CSV)")
async def reconcile_mpesa(file: UploadFile = File(...), db: Session = Depends(get_db),
                          current_user: User = Depends(finance_officer)):
    content = await file.read(MAX_STATEMENT_BYTES + 1)
    if len(content) > MAX_STATEMENT_BYTES:
        raise HTTPException(status_code=413, detail="Statement is larger than 10 MB; export a shorter period")
    try:
        return ReconciliationService(db).import_mpesa(content, file.filename or "statement.csv", _actor(current_user))
    except FinanceError as e:
        db.rollback()
        raise _http(e)


@router.post("/reconciliation/flutterwave", summary="Reconcile Flutterwave transactions for a date range")
async def reconcile_flutterwave(payload: FlutterwavePullIn, db: Session = Depends(get_db),
                                current_user: User = Depends(finance_officer)):
    if payload.date_from > payload.date_to or (payload.date_to - payload.date_from).days > 92:
        raise HTTPException(status_code=400, detail="Pick a range of at most 3 months, 'from' before 'to'")
    try:
        return ReconciliationService(db).pull_flutterwave(payload.date_from, payload.date_to, _actor(current_user))
    except FinanceError as e:
        db.rollback()
        raise _http(e)


@router.get("/reconciliation/runs", summary="Reconciliation runs, newest first")
async def reconciliation_runs(page: int = Query(1, ge=1), db: Session = Depends(get_db),
                              _: User = Depends(finance_officer)):
    return ReconciliationService(db).list_runs(page)


@router.get("/reconciliation/items", summary="Mismatch queue (open by default)")
async def reconciliation_items(
    status: Optional[str] = None,
    provider: Optional[str] = None,
    open_only: bool = True,
    run_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    try:
        return ReconciliationService(db).list_items(status, provider, open_only, run_id, page, limit)
    except FinanceError as e:
        raise _http(e)


@router.post("/reconciliation/items/{item_id}/resolve", summary="Close a mismatch with a note")
async def resolve_reconciliation_item(item_id: str, payload: ReconciliationResolveIn, db: Session = Depends(get_db),
                                      current_user: User = Depends(finance_officer)):
    try:
        return ReconciliationService(db).resolve(item_id, payload.resolution, payload.note, _actor(current_user))
    except FinanceError as e:
        raise _http(e)


# --- contribution volume & ledger integrity (read-only) ---

def _window(date_from, date_to, days: int):
    end = date_to or datetime.datetime.utcnow()
    start = date_from or end - datetime.timedelta(days=days)
    if start >= end:
        raise HTTPException(status_code=400, detail="'from' must be before 'to'")
    return start, end


@router.get("/volume", summary="Contributions processed on the platform (treasurers' money)")
async def contribution_volume(
    date_from: Optional[datetime.datetime] = Query(None, alias="from"),
    date_to: Optional[datetime.datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    _: User = Depends(finance_officer),
):
    return VolumeService(db).summary(*_window(date_from, date_to, 30))


@router.post("/integrity", summary="Re-check the seals on approved contributions")
async def ledger_integrity(
    date_from: Optional[datetime.datetime] = Query(None, alias="from"),
    date_to: Optional[datetime.datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(finance_officer),
):
    return VolumeService(db).integrity(*_window(date_from, date_to, 30), actor_id=_actor(current_user))
