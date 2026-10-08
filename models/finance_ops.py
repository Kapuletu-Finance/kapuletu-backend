import datetime
import uuid

from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from .base import Base


class ReconciliationRun(Base):
    """
    ReconciliationRun: One comparison of a provider's record of money received (an uploaded M-Pesa
    statement, or Flutterwave's transactions API) against our payments for the same period.
    """
    __tablename__ = "reconciliation_runs"

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(20), nullable=False)  # mpesa | flutterwave
    source = Column(String(20), nullable=False)  # upload | api
    source_name = Column(String, nullable=True)  # uploaded file name
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    lines = Column(Integer, nullable=False, default=0)
    matched = Column(Integer, nullable=False, default=0)
    mismatched = Column(Integer, nullable=False, default=0)
    created_by = Column(UUID(as_uuid=True), nullable=True)  # None = the daily job
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)


class ReconciliationItem(Base):
    """
    ReconciliationItem: One provider transaction or one of our payments, and whether the two sides agree.
    Keyed by (provider, ref_key) so re-importing a statement updates items instead of duplicating them.

    status: matched | amount_mismatch | missing_in_ledger (provider has money we didn't record)
            | missing_in_statement (we recorded money the provider doesn't show)
    """
    __tablename__ = "reconciliation_items"

    item_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    ref_key = Column(String, nullable=False)
    provider_ref = Column(String, nullable=True)  # M-Pesa receipt / Flutterwave id
    provider_amount = Column(Numeric(12, 2), nullable=True)
    provider_at = Column(DateTime, nullable=True)
    counterparty = Column(String, nullable=True)  # payer as the provider shows them
    payment_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    ledger_amount = Column(Numeric(12, 2), nullable=True)
    status = Column(String(30), nullable=False, index=True)
    match_method = Column(String(20), nullable=True)  # receipt | reference | amount_time
    raw = Column(JSON, nullable=True)
    resolution = Column(String(20), nullable=True)  # resolved | ignored
    resolution_note = Column(String, nullable=True)
    resolved_by = Column(UUID(as_uuid=True), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("provider", "ref_key", name="uix_reconciliation_item_ref"),
        CheckConstraint(
            "status in ('matched', 'amount_mismatch', 'missing_in_ledger', 'missing_in_statement')",
            name="reconciliation_items_status",
        ),
    )


class ReportSchedule(Base):
    """
    ReportSchedule: A finance report emailed to a list of people every week (Mondays, covering the previous
    Monday to Sunday) or month (the 1st, covering the previous calendar month).
    """
    __tablename__ = "report_schedules"

    schedule_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_type = Column(String(30), nullable=False)
    frequency = Column(String(10), nullable=False)  # weekly | monthly
    format = Column(String(10), nullable=False, default="pdf")  # csv | excel | pdf
    recipients = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    last_period_end = Column(DateTime, nullable=True)  # end of the last period sent
    last_sent_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint("frequency in ('weekly', 'monthly')", name="report_schedules_frequency"),
        CheckConstraint("format in ('csv', 'excel', 'pdf')", name="report_schedules_format"),
    )
