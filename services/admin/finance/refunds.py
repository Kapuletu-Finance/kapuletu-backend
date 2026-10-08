"""
Refunds go through maker-checker: one finance user requests, a different one approves or rejects.
Each request is also an ISSUE_REFUND item in the general approvals queue, so either screen can decide it.
"""
import datetime
import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from common.enums import ApprovalStatus
from models.billing import Refund
from models.employees import ApprovalRequest
from models.subscription import SubscriptionPayment
from models.users import User
from services.admin.approval_service import ApprovalService
from services.finance import billing

from .common import FinanceError, as_uuid, audit, iso, page_params, paged, user_name

logger = logging.getLogger(__name__)

APPROVAL_ACTION = "ISSUE_REFUND"
REFUND_STATUSES = ("requested", "approved", "rejected", "paid")


class RefundService:
    def __init__(self, db: Session):
        self.db = db

    def _out(self, r: Refund, user: Optional[User] = None, requester: Optional[User] = None,
             approver: Optional[User] = None) -> dict:
        return {
            "refund_id": str(r.refund_id),
            "payment_id": str(r.payment_id),
            "invoice_id": str(r.invoice_id) if r.invoice_id else None,
            "user_id": str(r.user_id),
            "user_name": user_name(user) if user is not None else None,
            "amount": float(r.amount or 0),
            "currency": r.currency,
            "reason_code": r.reason_code,
            "reason": r.reason,
            "status": r.status,
            "requested_by": str(r.requested_by) if r.requested_by else None,
            "requested_by_name": user_name(requester) if requester is not None else None,
            "approved_by": str(r.approved_by) if r.approved_by else None,
            "approved_by_name": user_name(approver) if approver is not None else None,
            "requested_at": iso(r.requested_at),
            "decided_at": iso(r.decided_at),
        }

    def _full_out(self, r: Refund) -> dict:
        get = lambda uid: self.db.get(User, uid) if uid else None  # noqa: E731
        return self._out(r, get(r.user_id), get(r.requested_by), get(r.approved_by))

    @staticmethod
    def _legacy_refund_id(db: Session, payment: SubscriptionPayment) -> Optional[str]:
        """A refund recorded before the refunds table existed (a negative payment pointing at this one)."""
        refund_id = (payment.payment_metadata or {}).get("refund_payment_id")
        if refund_id:
            return refund_id
        for candidate in db.query(SubscriptionPayment).filter(
            SubscriptionPayment.user_id == payment.user_id, SubscriptionPayment.transaction_type == "refund",
        ).all():
            if (candidate.payment_metadata or {}).get("original_payment_id") == str(payment.payment_id):
                return str(candidate.payment_id)
        return None

    # --- request ---

    def request(self, payment_id: str, reason: str, actor_id, reason_code: str = "other",
                amount: Optional[Decimal] = None) -> dict:
        """Opens a refund request for a successful payment. Nothing moves until someone else approves it."""
        if not actor_id:
            raise FinanceError("A refund request needs a requester", 400)
        try:
            payment = self.db.query(SubscriptionPayment).filter(
                SubscriptionPayment.payment_id == as_uuid(payment_id)
            ).with_for_update().first()
        except ValueError:
            payment = None
        if not payment:
            raise FinanceError("Payment not found", 404)
        if payment.status != "success":
            raise FinanceError(f"Only successful payments can be refunded (this one is '{payment.status}')")
        if (payment.transaction_type or "payment") != "payment" or (payment.amount or 0) <= 0:
            raise FinanceError("This record is not a refundable payment")

        existing = billing.active_refund(self.db, payment)
        existing_id = str(existing.refund_id) if existing else self._legacy_refund_id(self.db, payment)
        if existing_id:
            state = existing.status if existing else "approved"
            raise FinanceError(f"This payment already has a refund ({state}, {existing_id})", 409)

        paid = billing.money(payment.amount)
        amount = billing.money(amount) if amount is not None else paid
        if amount <= 0 or amount > paid:
            raise FinanceError(f"Refund amount must be more than 0 and at most {paid}")

        now = datetime.datetime.utcnow()
        refund = Refund(payment_id=payment.payment_id, invoice_id=payment.invoice_id, user_id=payment.user_id,
                        amount=amount, currency=payment.currency or "KES", reason_code=reason_code, reason=reason,
                        status="requested", requested_by=as_uuid(actor_id), requested_at=now)
        self.db.add(refund)
        self.db.flush()

        customer = self.db.get(User, payment.user_id)
        ApprovalService(self.db).create_request(
            requested_by=actor_id,
            action_type=APPROVAL_ACTION,
            payload={
                "refund_id": str(refund.refund_id), "payment_id": str(payment.payment_id),
                "user_id": str(payment.user_id), "user_name": user_name(customer),
                "amount": str(amount), "currency": refund.currency, "reason_code": reason_code,
            },
            justification=reason,
            commit=False,
        )
        audit(self.db, actor_id, "REFUND_REQUESTED", "REFUND", refund.refund_id, {
            "payment_id": str(payment.payment_id), "user_id": str(payment.user_id), "amount": amount,
            "reason_code": reason_code, "reason": reason,
        })
        self.db.commit()
        self._notify(f"Refund awaiting approval: {user_name(customer)}",
                     f"A refund of {refund.currency} {amount:,.2f} for <b>{user_name(customer)}</b> was requested "
                     f"and needs a second finance approver.<br>Reason: {reason}")
        return self._full_out(refund)

    # --- decision ---

    def _approval_for(self, refund: Refund) -> Optional[ApprovalRequest]:
        for req in self.db.query(ApprovalRequest).filter(
            ApprovalRequest.action_type == APPROVAL_ACTION, ApprovalRequest.status == ApprovalStatus.PENDING.value,
        ).all():
            if (req.payload or {}).get("refund_id") == str(refund.refund_id):
                return req
        return None

    def decide(self, refund_id: str, approve: bool, actor_id, note: Optional[str] = None,
               approval_already_resolved: bool = False) -> dict:
        """
        Approves (executes) or rejects a requested refund. The requester can't decide their own request.
        `approval_already_resolved` is set when the call comes from the approvals queue, which has already
        marked its own item.
        """
        try:
            refund = self.db.query(Refund).filter(Refund.refund_id == as_uuid(refund_id)).with_for_update().first()
        except ValueError:
            refund = None
        if not refund:
            raise FinanceError("Refund not found", 404)
        if refund.status != "requested":
            raise FinanceError(f"This refund is already {refund.status}", 409)
        if refund.requested_by and str(refund.requested_by) == str(actor_id):
            raise FinanceError("You can't approve or reject a refund you requested", 403)

        if not approval_already_resolved:
            req = self._approval_for(refund)
            if req is not None:
                try:
                    ApprovalService(self.db).resolve_request(req.id, actor_id, "approve" if approve else "reject",
                                                             commit=False)
                except ValueError as e:
                    raise FinanceError(str(e), 403)

        now = datetime.datetime.utcnow()
        if approve:
            payment = self.db.query(SubscriptionPayment).filter(
                SubscriptionPayment.payment_id == refund.payment_id
            ).with_for_update().first()
            billing.execute_refund(self.db, refund, payment, approved_by=actor_id, at=now)
            action = "REFUND_APPROVED"
        else:
            refund.status = "rejected"
            refund.approved_by = as_uuid(actor_id)
            refund.decided_at = now
            action = "REFUND_REJECTED"

        audit(self.db, actor_id, action, "REFUND", refund.refund_id, {
            "payment_id": str(refund.payment_id), "user_id": str(refund.user_id), "amount": refund.amount,
            "requested_by": str(refund.requested_by) if refund.requested_by else None, "note": note,
        })
        self.db.commit()
        return self._full_out(refund)

    # --- list ---

    def list(self, status: Optional[str] = None, user_id: Optional[str] = None, page: int = 1,
             limit: int = 50) -> dict:
        query = self.db.query(Refund)
        if user_id:
            query = query.filter(Refund.user_id == as_uuid(user_id))
        if status:
            if status not in REFUND_STATUSES:
                raise FinanceError(f"status must be one of {', '.join(REFUND_STATUSES)}")
            query = query.filter(Refund.status == status)
        total = query.count()
        offset, limit = page_params(page, limit)
        refunds = query.order_by(Refund.requested_at.desc()).offset(offset).limit(limit).all()
        return paged([self._full_out(r) for r in refunds], total, page, limit)

    @staticmethod
    def _notify(subject: str, html: str):
        try:
            from services.notifications.admin_dispatcher import notify_admins_async
            notify_admins_async(subject, html, category="finance")
        except Exception as e:
            logger.error(f"Failed to notify finance admins: {e}")
