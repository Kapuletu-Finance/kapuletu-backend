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
            ["Provider reference", payment.provider_reference or "—"],
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
