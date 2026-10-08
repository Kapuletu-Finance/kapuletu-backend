"""
Finance reports: built once as data, then rendered as JSON (for the screen), CSV, Excel or an official PDF.
"""
import csv
import datetime
import io
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.billing import Invoice, InvoiceLine, LedgerEntry, Refund
from models.subscription import Plan, SubscriptionPayment
from models.users import User

from .common import FinanceError, user_name

ZERO = Decimal("0")
EAT_OFFSET = datetime.timedelta(hours=3)


@dataclass
class ReportTable:
    title: str
    columns: List[str]
    rows: List[list]
    numeric_cols: Sequence[int] = ()


@dataclass
class Report:
    key: str
    title: str
    description: str
    start: datetime.datetime
    end: datetime.datetime
    figures: List[Tuple[str, str]] = field(default_factory=list)
    tables: List[ReportTable] = field(default_factory=list)

    # Bounds are UTC; people read Nairobi calendar days.
    @property
    def local_start(self) -> datetime.datetime:
        return self.start + EAT_OFFSET

    @property
    def local_last_day(self) -> datetime.datetime:
        return self.end + EAT_OFFSET - datetime.timedelta(seconds=1)

    @property
    def period_label(self) -> str:
        return f"{self.local_start:%d %b %Y} – {self.local_last_day:%d %b %Y}"

    def as_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "description": self.description,
            "period": {"from": self.start.isoformat(), "to": self.end.isoformat(), "label": self.period_label},
            "figures": [{"label": label, "value": value} for label, value in self.figures],
            "tables": [{"title": t.title, "columns": t.columns, "rows": t.rows, "numeric_cols": list(t.numeric_cols)}
                       for t in self.tables],
        }


def kes(value) -> str:
    return f"KES {Decimal(str(value or 0)):,.2f}"


def amt(value) -> float:
    return round(float(value or 0), 2)


def month_starts(start: datetime.datetime, end: datetime.datetime) -> List[datetime.datetime]:
    cursor = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    months = []
    while cursor < end:
        months.append(cursor)
        cursor = (cursor.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return months


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    # --- catalogue ---

    REPORTS: Dict[str, Tuple[str, str]] = {
        "revenue": ("Revenue by month", "Invoiced, refunded, net and tax per month, and revenue by plan."),
        "refunds": ("Refunds", "Every refund decided in the period, who requested and who approved it."),
        "receivables": ("Unpaid invoices", "Invoices still awaiting payment, by how long they have been open."),
        "payment_methods": ("Payment methods", "Checkout attempts, success rate and money collected per method."),
        "tax": ("Tax summary", "Taxable sales and tax collected per month, for filing."),
    }

    @classmethod
    def catalogue(cls) -> List[dict]:
        return [{"key": k, "title": t, "description": d} for k, (t, d) in cls.REPORTS.items()]

    def build(self, key: str, start: datetime.datetime, end: datetime.datetime) -> Report:
        if key not in self.REPORTS:
            raise FinanceError(f"Unknown report '{key}'", 404)
        if start >= end:
            raise FinanceError("'from' must be before 'to'")
        title, description = self.REPORTS[key]
        report = Report(key, title, description, start, end)
        builder: Callable[[Report], None] = getattr(self, f"_{key}")
        builder(report)
        return report

    # --- helpers ---

    def _ledger_by_month(self, account: str, side: str, start, end) -> Dict[str, Decimal]:
        col = LedgerEntry.debit if side == "debit" else LedgerEntry.credit
        out: Dict[str, Decimal] = defaultdict(lambda: ZERO)
        for at, value in self.db.query(LedgerEntry.effective_at, col).filter(
            LedgerEntry.account == account, LedgerEntry.effective_at >= start, LedgerEntry.effective_at < end
        ):
            out[(at + EAT_OFFSET).strftime("%Y-%m")] += Decimal(str(value or 0))
        return out

    # --- reports ---

    def _revenue(self, r: Report):
        revenue = self._ledger_by_month("revenue", "credit", r.start, r.end)
        refunds = self._ledger_by_month("refunds", "debit", r.start, r.end)
        tax = self._ledger_by_month("tax_payable", "credit", r.start, r.end)
        cash = self._ledger_by_month("cash", "debit", r.start, r.end)
        rows, totals = [], [ZERO] * 5
        for m in month_starts(r.local_start, r.end + EAT_OFFSET):
            key = m.strftime("%Y-%m")
            values = [revenue[key], refunds[key], revenue[key] - refunds[key], tax[key], cash[key]]
            totals = [a + b for a, b in zip(totals, values)]
            rows.append([m.strftime("%b %Y")] + [amt(v) for v in values])
        rows.append(["Total"] + [amt(v) for v in totals])
        r.figures = [("Revenue", kes(totals[0])), ("Refunds", kes(totals[1])), ("Net revenue", kes(totals[2])),
                     ("Tax collected", kes(totals[3]))]
        r.tables.append(ReportTable("By month", ["Month", "Revenue", "Refunds", "Net revenue", "Tax", "Cash collected"],
                                    rows, numeric_cols=(1, 2, 3, 4, 5)))

        by_plan: Dict[str, Decimal] = defaultdict(lambda: ZERO)
        plan_names = dict(self.db.query(Plan.plan_id, Plan.name).all())
        for kind, plan_id, amount in self.db.query(InvoiceLine.kind, InvoiceLine.plan_id, InvoiceLine.amount).join(
            Invoice, InvoiceLine.invoice_id == Invoice.invoice_id
        ).filter(Invoice.status == "paid", Invoice.paid_at >= r.start, Invoice.paid_at < r.end,
                 InvoiceLine.kind.in_(("plan", "addon"))):
            by_plan["Add-ons" if kind == "addon" else plan_names.get(plan_id, "Other")] += Decimal(str(amount or 0))
        r.tables.append(ReportTable("Invoiced by plan (before tax and refunds)", ["Plan", "Invoiced"],
                                    [[name, amt(v)] for name, v in sorted(by_plan.items(), key=lambda x: -x[1])],
                                    numeric_cols=(1,)))

    def _refunds(self, r: Report):
        users = {}

        def name(uid):
            if uid and uid not in users:
                users[uid] = user_name(self.db.get(User, uid))
            return users.get(uid, "—")

        # A refund belongs to the period it was decided in, or requested in while still undecided.
        refunds = self.db.query(Refund).filter(
            or_(
                (Refund.decided_at >= r.start) & (Refund.decided_at < r.end),
                Refund.decided_at.is_(None) & (Refund.requested_at >= r.start) & (Refund.requested_at < r.end),
            )
        ).order_by(Refund.requested_at).all()
        approved = [x for x in refunds if x.status in ("approved", "paid")]
        r.figures = [("Refunded", kes(sum((Decimal(str(x.amount)) for x in approved), ZERO))),
                     ("Approved", str(len(approved))),
                     ("Rejected", str(sum(1 for x in refunds if x.status == "rejected"))),
                     ("Awaiting approval", str(sum(1 for x in refunds if x.status == "requested")))]
        r.tables.append(ReportTable(
            "Refunds", ["Requested", "Treasurer", "Amount", "Reason", "Status", "Requested by", "Decided by", "Decided"],
            [[x.requested_at.strftime("%Y-%m-%d"), name(x.user_id), amt(x.amount), x.reason_code + (f": {x.reason}" if x.reason else ""),
              x.status, name(x.requested_by), name(x.approved_by) if x.approved_by else "—",
              x.decided_at.strftime("%Y-%m-%d") if x.decided_at else "—"] for x in refunds],
            numeric_cols=(2,),
        ))

    def _receivables(self, r: Report):
        # Open invoices as at the end of the period, aged from their issue date.
        buckets = [("0–7 days", 0, 7), ("8–30 days", 8, 30), ("31–60 days", 31, 60), ("Over 60 days", 61, 10**6)]
        totals = {b[0]: [0, ZERO] for b in buckets}
        rows = []
        for inv, user in self.db.query(Invoice, User).join(User, Invoice.user_id == User.user_id).filter(
            Invoice.status == "open", Invoice.issued_at < r.end
        ).order_by(Invoice.issued_at):
            age = (r.end - inv.issued_at).days
            bucket = next(b[0] for b in buckets if b[1] <= age <= b[2])
            totals[bucket][0] += 1
            totals[bucket][1] += Decimal(str(inv.total or 0))
            rows.append([inv.number, user_name(user), inv.issued_at.strftime("%Y-%m-%d"), age, bucket, amt(inv.total)])
        r.figures = [(label, f"{count} · {kes(total)}") for label, (count, total) in totals.items()]
        r.tables.append(ReportTable("Unpaid invoices", ["Invoice", "Treasurer", "Issued", "Age (days)", "Bucket", "Amount"],
                                    rows, numeric_cols=(3, 5)))
        r.description += " Most are checkouts the customer started and did not finish; they are voided when payment fails."

    def _payment_methods(self, r: Report):
        stats: Dict[str, Dict[str, object]] = defaultdict(lambda: {"attempts": 0, "success": 0, "failed": 0, "amount": ZERO})
        for method, status, amount in self.db.query(
            SubscriptionPayment.payment_method, SubscriptionPayment.status, SubscriptionPayment.amount
        ).filter(
            SubscriptionPayment.created_at >= r.start, SubscriptionPayment.created_at < r.end,
            or_(SubscriptionPayment.transaction_type.is_(None), SubscriptionPayment.transaction_type == "payment"),
            SubscriptionPayment.payment_method != "admin_override",
        ):
            s = stats[method or "unknown"]
            s["attempts"] += 1
            if status == "success":
                s["success"] += 1
                s["amount"] += Decimal(str(amount or 0))
            elif status == "failed":
                s["failed"] += 1
        rows = []
        for method, s in sorted(stats.items(), key=lambda x: -x[1]["amount"]):
            settled = s["success"] + s["failed"]
            rows.append([method, s["attempts"], s["success"], s["failed"],
                         round(s["success"] / settled * 100, 1) if settled else 0.0, amt(s["amount"])])
        total = sum((s["amount"] for s in stats.values()), ZERO)
        r.figures = [("Collected", kes(total)), ("Checkouts", str(sum(s["attempts"] for s in stats.values())))]
        r.tables.append(ReportTable("By method", ["Method", "Checkouts", "Paid", "Failed", "Success rate %", "Collected"],
                                    rows, numeric_cols=(1, 2, 3, 4, 5)))

    def _tax(self, r: Report):
        rows, totals = [], [0, ZERO, ZERO]
        per_month: Dict[str, list] = defaultdict(lambda: [0, ZERO, ZERO])
        for paid_at, subtotal, tax in self.db.query(Invoice.paid_at, Invoice.subtotal, Invoice.tax).filter(
            Invoice.status == "paid", Invoice.paid_at >= r.start, Invoice.paid_at < r.end
        ):
            m = per_month[(paid_at + EAT_OFFSET).strftime("%Y-%m")]
            m[0] += 1
            m[1] += Decimal(str(subtotal or 0))
            m[2] += Decimal(str(tax or 0))
        for month in month_starts(r.local_start, r.end + EAT_OFFSET):
            count, subtotal, tax = per_month[month.strftime("%Y-%m")]
            totals = [totals[0] + count, totals[1] + subtotal, totals[2] + tax]
            rows.append([month.strftime("%b %Y"), count, amt(subtotal), amt(tax)])
        rows.append(["Total", totals[0], amt(totals[1]), amt(totals[2])])
        r.figures = [("Taxable sales", kes(totals[1])), ("Tax collected", kes(totals[2])), ("Paid invoices", str(totals[0]))]
        r.tables.append(ReportTable("By month (invoice paid date)", ["Month", "Paid invoices", "Taxable sales", "Tax"],
                                    rows, numeric_cols=(1, 2, 3)))

    # --- rendering ---

    def render(self, report: Report, fmt: str, prepared_by: Optional[str] = None, actor_id=None) -> Tuple[bytes, str, str]:
        """Returns (content, mime type, file name)."""
        stem = f"kapuletu_{report.key}_{report.local_start:%Y%m%d}_{report.local_last_day:%Y%m%d}"
        if fmt == "csv":
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow([report.title, report.period_label])
            for label, value in report.figures:
                writer.writerow([label, value])
            for table in report.tables:
                writer.writerow([])
                writer.writerow([table.title])
                writer.writerow(table.columns)
                writer.writerows(table.rows)
            return out.getvalue().encode("utf-8-sig"), "text/csv", f"{stem}.csv"

        if fmt == "excel":
            import openpyxl
            from openpyxl.styles import Font
            wb = openpyxl.Workbook()
            summary = wb.active
            summary.title = "Summary"
            summary.append([report.title])
            summary["A1"].font = Font(bold=True, size=14)
            summary.append([report.period_label])
            summary.append([])
            for label, value in report.figures:
                summary.append([label, value])
            for table in report.tables:
                ws = wb.create_sheet(title=table.title[:31])
                ws.append(table.columns)
                for cell in ws[1]:
                    cell.font = Font(bold=True)
                for row in table.rows:
                    ws.append(row)
                for idx, column in enumerate(ws.columns):
                    width = max(len(str(c.value or "")) for c in column)
                    ws.column_dimensions[column[0].column_letter].width = min(max(10, width + 2), 50)
            out = io.BytesIO()
            wb.save(out)
            return out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{stem}.xlsx"

        if fmt == "pdf":
            from services.documents.official import OfficialDocument
            doc = OfficialDocument(self.db, title=report.title, subtitle=report.period_label, department="FIN",
                                   doc_type="RPT", prepared_by=prepared_by,
                                   orientation="landscape" if any(len(t.columns) > 5 for t in report.tables) else "portrait")
            doc.paragraph(report.description, muted=True)
            if report.figures:
                doc.key_figures([(label, value, None) for label, value in report.figures])
            for table in report.tables:
                doc.section(table.title)
                doc.table(table.columns, [[f"{v:,.2f}" if isinstance(v, float) else v for v in row] for row in table.rows],
                          numeric_cols=set(table.numeric_cols))
            doc.signature_block()
            pdf = doc.build(actor_id=str(actor_id) if actor_id else None,
                            audit_details={"report": report.key, "period": report.period_label})
            return pdf, "application/pdf", f"{doc.filename_stem}.pdf"

        raise FinanceError("format must be csv, excel or pdf")
