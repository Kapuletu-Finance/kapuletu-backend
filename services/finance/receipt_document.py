"""Subscription payment receipt as an official Kapuletu document."""
import datetime
import re

from sqlalchemy.orm import Session

from common.utils import NAIROBI_TZ
from models.subscription import Plan, SubscriptionPayment
from models.users import User
from services.documents.official import OfficialDocument, make_reference


def render_subscription_receipt(db: Session, payment: SubscriptionPayment, plan: Plan, user: User) -> tuple[bytes, str]:
    """Returns (pdf_bytes, filename). The reference is derived from the payment, so re-downloads match."""
    paid_at = (payment.created_at or datetime.datetime.utcnow()).replace(tzinfo=datetime.timezone.utc).astimezone(NAIROBI_TZ)
    natural_id = re.sub(r"[^A-Za-z0-9]", "", payment.provider_reference or "")[:12] or str(payment.payment_id)[:8]
    customer = f"{user.first_name} {user.last_name}".strip() if user else "KapuLetu User"
    amount = float(payment.amount or 0)
    currency = payment.currency or "KES"

    doc = OfficialDocument(
        db,
        title="Payment Receipt",
        subtitle=f"KapuLetu {plan.name} subscription",
        department="FIN",
        doc_type="RCT",
        reference=make_reference("FIN", "RCT", paid_at, suffix=natural_id.upper()),
        classification="Official receipt",
    )

    doc.section("Receipt details")
    doc.table(
        ["Detail", "Information"],
        [
            ["Billed to", customer],
            ["Email", user.email if user else "—"],
            ["Payment date", f"{paid_at:%d %B %Y, %H:%M} EAT"],
            ["Payment method", (payment.payment_method or "—").upper()],
            ["Receipt number", (payment.payment_metadata or {}).get("receipt_number") or payment.provider_reference or "—"],
            ["Invoice", (payment.payment_metadata or {}).get("invoice_number") or "—"],
            ["Status", "Paid"],
        ],
        col_widths=[0.3, 0.7],
    )

    doc.section("Items")
    doc.table(
        ["Description", f"Amount ({currency})"],
        [
            [f"KapuLetu {plan.name} subscription", f"{amount:,.2f}"],
            ["Total paid", f"{amount:,.2f}"],
        ],
        col_widths=[0.7, 0.3],
        numeric_cols={1},
    )

    doc.spacer(6)
    doc.paragraph("Thank you for your business. This receipt was generated electronically and is valid without a signature.", muted=True)
    # Receipts are reproducible from the payment record, so re-downloads are not logged as new documents.
    return doc.build(audit=False), f"{doc.filename_stem}.pdf"


def render_invoice(db: Session, invoice, lines, user: User, credit_notes=()) -> tuple[bytes, str]:
    """An invoice (marked paid when it is) as an official document. Re-downloads give the same reference."""
    issued = invoice.issued_at.replace(tzinfo=datetime.timezone.utc).astimezone(NAIROBI_TZ)
    customer = f"{user.first_name} {user.last_name}".strip() if user else "KapuLetu User"
    currency = invoice.currency or "KES"
    status = {"paid": "Paid", "open": "Awaiting payment", "void": "Void", "draft": "Draft"}.get(invoice.status, invoice.status)

    doc = OfficialDocument(
        db,
        title="Tax Invoice" if float(invoice.tax or 0) > 0 else "Invoice",
        subtitle=f"{invoice.number} · {status}",
        department="FIN",
        doc_type="INV",
        reference=invoice.number,
        classification="Official invoice",
        issued_at=issued,
    )
    period = (f"{invoice.period_start:%d %b %Y} to {invoice.period_end:%d %b %Y}"
              if invoice.period_start and invoice.period_end else "Starts when paid")
    paid = invoice.paid_at.replace(tzinfo=datetime.timezone.utc).astimezone(NAIROBI_TZ) if invoice.paid_at else None
    doc.section("Invoice details")
    doc.table(
        ["Detail", "Information"],
        [
            ["Invoice number", invoice.number],
            ["Billed to", customer],
            ["Email", user.email if user else "—"],
            ["Issued", f"{issued:%d %B %Y}"],
            ["Service period", period],
            ["Status", f"{status}" + (f" on {paid:%d %B %Y}" if paid else "")],
        ],
        col_widths=[0.3, 0.7],
    )
    doc.section("Items")
    doc.table(
        ["Description", "Qty", f"Amount ({currency})"],
        [[line.description, line.quantity, f"{float(line.amount):,.2f}"] for line in lines]
        + [["Total", "", f"{float(invoice.total or 0):,.2f}"]],
        col_widths=[0.65, 0.1, 0.25],
        numeric_cols={1, 2},
    )
    if credit_notes:
        doc.section("Credit notes")
        doc.table(
            ["Credit note", "Date", f"Amount ({currency})"],
            [[c.number, f"{c.issued_at:%d %b %Y}", f"-{float(c.amount):,.2f}"] for c in credit_notes],
            col_widths=[0.45, 0.25, 0.3],
            numeric_cols={2},
        )
    doc.spacer(6)
    doc.paragraph("Generated electronically from Kapuletu's billing records; valid without a signature.", muted=True)
    return doc.build(audit=False), f"{invoice.number}.pdf"
