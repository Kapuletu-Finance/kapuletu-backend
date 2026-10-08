"""Invoices and payments: filtered lists and detail views."""
import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.billing import CreditNote, Invoice, InvoiceLine, ProviderEvent, Refund
from models.subscription import Plan, Subscription, SubscriptionPayment
from models.users import User

from .common import FinanceError, as_uuid, iso, page_params, paged, user_name

INVOICE_STATUSES = ("draft", "open", "paid", "void")
PAYMENT_STATUSES = ("pending", "initiated", "success", "failed")
PAYMENT_TYPES = ("payment", "refund", "comp")


def _user_search(q: str):
    like = f"%{q.strip()}%"
    return or_(User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like),
               User.phone_number.ilike(like), User.slug.ilike(like))


def money_out(value) -> float:
    return float(value or 0)


class InvoiceService:
    def __init__(self, db: Session):
        self.db = db

    # --- invoices ---

    @staticmethod
    def _invoice_row(inv: Invoice, user: Optional[User]) -> dict:
        return {
            "invoice_id": str(inv.invoice_id),
            "number": inv.number,
            "user_id": str(inv.user_id),
            "user_name": user_name(user),
            "status": inv.status,
            "currency": inv.currency,
            "subtotal": money_out(inv.subtotal),
            "tax": money_out(inv.tax),
            "total": money_out(inv.total),
            "billing_cycle": inv.billing_cycle,
            "period_start": iso(inv.period_start),
            "period_end": iso(inv.period_end),
            "issued_at": iso(inv.issued_at),
            "paid_at": iso(inv.paid_at),
        }

    def list_invoices(self, status: Optional[str] = None, q: Optional[str] = None,
                      date_from: Optional[datetime.datetime] = None, date_to: Optional[datetime.datetime] = None,
                      user_id: Optional[str] = None, page: int = 1, limit: int = 50) -> dict:
        query = self.db.query(Invoice, User).join(User, Invoice.user_id == User.user_id)
        if status:
            if status not in INVOICE_STATUSES:
                raise FinanceError(f"status must be one of {', '.join(INVOICE_STATUSES)}")
            query = query.filter(Invoice.status == status)
        if user_id:
            query = query.filter(Invoice.user_id == as_uuid(user_id))
        if date_from:
            query = query.filter(Invoice.issued_at >= date_from)
        if date_to:
            query = query.filter(Invoice.issued_at < date_to)
        if q:
            query = query.filter(or_(_user_search(q), Invoice.number.ilike(f"%{q.strip()}%")))
        total = query.count()
        offset, limit = page_params(page, limit)
        rows = query.order_by(Invoice.issued_at.desc()).offset(offset).limit(limit).all()
        return paged([self._invoice_row(i, u) for i, u in rows], total, page, limit)

    def get_invoice(self, invoice_id: str) -> dict:
        inv = self.db.get(Invoice, as_uuid(invoice_id))
        if not inv:
            raise FinanceError("Invoice not found", 404)
        out = self._invoice_row(inv, self.db.get(User, inv.user_id))
        out["notes"] = inv.notes
        out["lines"] = [{
            "kind": l.kind, "description": l.description, "quantity": l.quantity,
            "unit_amount": money_out(l.unit_amount), "amount": money_out(l.amount),
        } for l in self.db.query(InvoiceLine).filter(InvoiceLine.invoice_id == inv.invoice_id).all()]
        out["payments"] = [self._payment_row(p, None, None, inv.number) for p in self.db.query(SubscriptionPayment).filter(
            SubscriptionPayment.invoice_id == inv.invoice_id).order_by(SubscriptionPayment.created_at).all()]
        out["credit_notes"] = [{
            "number": c.number, "amount": money_out(c.amount), "reason": c.reason, "issued_at": iso(c.issued_at),
        } for c in self.db.query(CreditNote).filter(CreditNote.invoice_id == inv.invoice_id).all()]
        return out

    # --- payments ---

    @staticmethod
    def _payment_row(p: SubscriptionPayment, user: Optional[User], plan: Optional[Plan], invoice_number) -> dict:
        meta = p.payment_metadata or {}
        return {
            "payment_id": str(p.payment_id),
            "user_id": str(p.user_id),
            "user_name": user_name(user) if user is not None else None,
            "plan_name": plan.name if plan else None,
            "amount": money_out(p.amount),
            "currency": p.currency,
            "status": p.status,
            "method": p.payment_method,
            "transaction_type": p.transaction_type or "payment",
            "invoice_number": invoice_number,
            "receipt_number": meta.get("receipt_number"),
            "provider_reference": p.provider_reference,
            "failure_reason": meta.get("failure_reason"),
            "refunded": bool(meta.get("refund_payment_id")),
            "refund_id": meta.get("refund_id"),
            "created_at": iso(p.created_at),
        }

    def list_payments(self, status: Optional[str] = None, provider: Optional[str] = None, type_: Optional[str] = None,
                      q: Optional[str] = None, date_from: Optional[datetime.datetime] = None,
                      date_to: Optional[datetime.datetime] = None, user_id: Optional[str] = None,
                      page: int = 1, limit: int = 50) -> dict:
        query = self.db.query(SubscriptionPayment, User, Plan, Invoice.number).join(
            User, SubscriptionPayment.user_id == User.user_id
        ).outerjoin(Subscription, SubscriptionPayment.subscription_id == Subscription.subscription_id).outerjoin(
            Plan, Subscription.plan_id == Plan.plan_id
        ).outerjoin(Invoice, SubscriptionPayment.invoice_id == Invoice.invoice_id)
        if status:
            if status not in PAYMENT_STATUSES:
                raise FinanceError(f"status must be one of {', '.join(PAYMENT_STATUSES)}")
            query = query.filter(SubscriptionPayment.status == status)
        if provider:
            query = query.filter(SubscriptionPayment.payment_method == provider)
        if type_:
            if type_ not in PAYMENT_TYPES:
                raise FinanceError(f"type must be one of {', '.join(PAYMENT_TYPES)}")
            if type_ == "payment":
                query = query.filter(or_(SubscriptionPayment.transaction_type.is_(None),
                                         SubscriptionPayment.transaction_type == "payment"))
            else:
                query = query.filter(SubscriptionPayment.transaction_type == type_)
        if user_id:
            query = query.filter(SubscriptionPayment.user_id == as_uuid(user_id))
        if date_from:
            query = query.filter(SubscriptionPayment.created_at >= date_from)
        if date_to:
            query = query.filter(SubscriptionPayment.created_at < date_to)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(or_(_user_search(q), SubscriptionPayment.provider_reference.ilike(like),
                                     Invoice.number.ilike(like)))
        total = query.count()
        offset, limit = page_params(page, limit)
        rows = query.order_by(SubscriptionPayment.created_at.desc()).offset(offset).limit(limit).all()
        return paged([self._payment_row(p, u, pl, n) for p, u, pl, n in rows], total, page, limit)

    def get_payment(self, payment_id: str) -> dict:
        p = self.db.get(SubscriptionPayment, as_uuid(payment_id))
        if not p:
            raise FinanceError("Payment not found", 404)
        sub = self.db.get(Subscription, p.subscription_id) if p.subscription_id else None
        invoice = self.db.get(Invoice, p.invoice_id) if p.invoice_id else None
        out = self._payment_row(p, self.db.get(User, p.user_id), self.db.get(Plan, sub.plan_id) if sub else None,
                                invoice.number if invoice else None)
        out["invoice_id"] = str(invoice.invoice_id) if invoice else None
        out["metadata"] = {k: v for k, v in (p.payment_metadata or {}).items() if k not in ("phone_number", "email")}
        refund = self.db.query(Refund).filter(Refund.payment_id == p.payment_id).order_by(Refund.requested_at.desc()).first()
        out["refund"] = {"refund_id": str(refund.refund_id), "status": refund.status, "amount": money_out(refund.amount)} if refund else None
        out["provider_events"] = [{
            "provider": e.provider, "outcome": e.outcome, "received_at": iso(e.received_at),
            "processed_at": iso(e.processed_at), "payload": e.payload,
        } for e in self.db.query(ProviderEvent).filter(
            ProviderEvent.correlation_id == p.provider_reference).order_by(ProviderEvent.received_at).all()
        ] if p.provider_reference else []
        return out
