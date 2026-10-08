import datetime
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

from common.utils import parse_uuid
from models.audit_log import AuditLog
from models.billing import Invoice
from models.subscription import Plan, Subscription, SubscriptionPayment
from services.finance import billing
from services.notifications.service import create_notification

logger = logging.getLogger(__name__)

# Statuses a checkout attempt can be fulfilled from.
OPEN_PAYMENT_STATUSES = ("pending", "initiated")


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except InvalidOperation:
        return Decimal("0")


class FulfillmentService:
    """
    FulfillmentService: The bridge between a successful payment and platform features.

    A payment is only ever fulfilled against a pending SubscriptionPayment that checkout created.
    The plan, user and expected amount come from that row, never from the provider callback.
    """
    def __init__(self, db: Session):
        self.db = db

    def _lock_payment(self, correlation_id: str) -> Optional[SubscriptionPayment]:
        # Row lock so a webhook and the status poller cannot both extend the subscription.
        return (
            self.db.query(SubscriptionPayment)
            .filter(SubscriptionPayment.provider_reference == correlation_id)
            .with_for_update()
            .first()
        )

    def process_success(self, correlation_id: str, provider_ref: str, amount, currency: Optional[str] = None) -> bool:
        """
        Finalizes the subscription after the provider confirms payment.
        Returns True when the payment is (or already was) fulfilled.
        """
        pending_payment = self._lock_payment(correlation_id)

        if not pending_payment:
            logger.error(f"Fulfillment refused: no checkout found for correlation {correlation_id}")
            self.db.rollback()
            return False

        if pending_payment.status == "success":
            logger.warning(f"Idempotency Trigger: Payment {correlation_id} already processed successfully.")
            self.db.rollback()
            return True

        if pending_payment.status not in OPEN_PAYMENT_STATUSES:
            logger.error(f"Fulfillment refused: payment {correlation_id} is '{pending_payment.status}', not open")
            self.db.rollback()
            return False

        stored_meta = dict(pending_payment.payment_metadata or {})
        user_id = pending_payment.user_id
        expected_amount = _to_decimal(pending_payment.amount)
        paid_amount = _to_decimal(amount)
        expected_currency = (pending_payment.currency or "KES").upper()

        # 1. The provider must report at least the amount we asked for, in the same currency.
        currency_mismatch = bool(currency) and currency.upper() != expected_currency
        if paid_amount < expected_amount or currency_mismatch:
            stored_meta.update({
                "failure_reason": "amount_mismatch",
                "paid_amount": str(paid_amount),
                "paid_currency": currency or expected_currency,
                "receipt_number": provider_ref,
            })
            pending_payment.status = "failed"
            pending_payment.payment_metadata = stored_meta
            mismatched_invoice = self.db.get(Invoice, pending_payment.invoice_id) if pending_payment.invoice_id else None
            if mismatched_invoice is not None:
                billing.void_invoice(mismatched_invoice, "Provider reported a different amount or currency")
            self.db.add(AuditLog(
                actor_id=user_id,
                action="PAYMENT_AMOUNT_MISMATCH",
                entity_type="SUBSCRIPTION_PAYMENT",
                entity_id=str(pending_payment.payment_id),
                details={
                    "expected": str(expected_amount), "expected_currency": expected_currency,
                    "paid": str(paid_amount), "paid_currency": currency, "ref": provider_ref,
                    "correlation": correlation_id,
                },
            ))
            self.db.commit()
            logger.error(
                f"Fulfillment refused: {correlation_id} paid {paid_amount} {currency or ''}, expected {expected_amount} {expected_currency}"
            )
            self._notify_admins(
                f"Payment amount mismatch: {correlation_id}",
                f"Checkout <b>{correlation_id}</b> reported {paid_amount} {currency or expected_currency} "
                f"but expected {expected_amount} {expected_currency}. The subscription was NOT upgraded.<br>"
                f"Provider reference: {provider_ref}",
            )
            return False

        # 2. Resolve the plan the user chose at checkout.
        plan_id = stored_meta.get("plan_id")
        plan = self.db.query(Plan).filter(Plan.plan_id == parse_uuid(plan_id)).first() if plan_id else None
        if not plan:
            logger.error(f"Fulfillment failed: plan {plan_id} not found for correlation {correlation_id}")
            self.db.rollback()
            return False

        billing_cycle = stored_meta.get("billing_cycle") or "monthly"
        days_to_add = 365 if billing_cycle == "annual" else 30
        now = datetime.datetime.utcnow()

        # 3. Update/Create Subscription
        sub = self.db.query(Subscription).filter(Subscription.user_id == user_id).first()
        from_plan_id = sub.plan_id if sub else None
        if not sub:
            sub = Subscription(
                user_id=user_id,
                plan_id=plan.plan_id,
                status="active",
                start_date=now,
                end_date=now + datetime.timedelta(days=days_to_add),
            )
            self.db.add(sub)
            period_start = now
        else:
            # Paid time stacks on paid time still left; a trial ends the moment the user pays.
            still_paid = sub.end_date and sub.end_date > now and not sub.is_trial
            period_start = sub.end_date if still_paid else now
            sub.plan_id = plan.plan_id
            sub.status = "active"
            sub.end_date = period_start + datetime.timedelta(days=days_to_add)
        sub.is_trial = False
        price_id = stored_meta.get("price_id")
        sub.price_id = parse_uuid(price_id) if price_id else None
        self.db.flush()

        # 4. Record Payment. Keep provider_reference as the correlation ID the frontend polls for.
        stored_meta["receipt_number"] = provider_ref
        stored_meta["paid_amount"] = str(paid_amount)
        pending_payment.status = "success"
        pending_payment.payment_metadata = stored_meta

        # 4b. Settle the invoice and post the money to the billing ledger.
        invoice = self.db.get(Invoice, pending_payment.invoice_id) if pending_payment.invoice_id else None
        if invoice is not None:
            billing.mark_invoice_paid(invoice, period_start, sub.end_date, now)
        billing.post_payment(self.db, pending_payment, invoice, now)
        event_type = "renewed" if from_plan_id == plan.plan_id else "upgraded"
        billing.record_event(self.db, sub, event_type, from_plan_id=from_plan_id, to_plan_id=plan.plan_id,
                             invoice_id=invoice.invoice_id if invoice is not None else None, at=now)

        # 5. Forensic Audit
        self.db.add(AuditLog(
            actor_id=user_id,
            action="SUBSCRIPTION_UPGRADED",
            entity_type="PLAN",
            entity_id=str(plan.plan_id),
            details={"amount": str(paid_amount), "ref": provider_ref, "correlation": correlation_id},
        ))

        self.db.commit()

        amount_display = float(paid_amount)
        email = stored_meta.get("email")
        name = stored_meta.get("name") or "KapuLetu User"

        # 6. Dispatch Email Receipt
        if email:
            try:
                from models.communication_logs import CommunicationLog
                from services.notifications.tasks import send_email_task
                from services.notifications.templates.render import render_email_template

                subject = f"Your KapuLetu {plan.name} Receipt"
                html_body = render_email_template(
                    "payment_receipt.html",
                    name=name,
                    plan_name=plan.name,
                    billing_cycle=billing_cycle.title(),
                    amount=amount_display,
                    receipt_number=provider_ref,
                    date=now.strftime('%B %d, %Y')
                )

                log = CommunicationLog(
                    user_id=user_id,
                    channel="EMAIL",
                    destination=email,
                    subject=subject,
                    status="QUEUED"
                )
                self.db.add(log)
                self.db.commit()

                # Synchronous Execution
                send_email_task(str(log.log_id), email, subject, html_body)
            except Exception as e:
                logger.error(f"Failed to queue email receipt: {e}")

        # 7. In-App Notification
        try:
            create_notification(
                db=self.db,
                user_id=str(user_id),
                title="Subscription Upgraded",
                message=f"We received your payment of Ksh {amount_display:,.2f}. Your workspace is now on the {plan.name} tier. Receipt: {provider_ref}",
                type="subscription_update",
                related_entity_id=str(sub.subscription_id)
            )
        except Exception as e:
            logger.error(f"Failed to create in-app notification: {e}")

        # 8. Notify Admins
        self._notify_admins(
            f"Subscription Upgraded: {plan.name}",
            f"User <b>{name}</b> ({email}) just upgraded their workspace to the <b>{plan.name}</b> tier.<br><br>"
            f"Amount: Ksh {amount_display:,.2f}<br>Reference: {provider_ref}",
        )

        logger.info(f"Fulfillment Successful: User {user_id} upgraded to {plan.name}")
        return True

    def process_failure(self, correlation_id: str, reason: str = "") -> bool:
        """Marks an open checkout as failed after the provider reports a final failure (cancelled, timed out)."""
        pending_payment = self._lock_payment(correlation_id)
        if not pending_payment or pending_payment.status not in OPEN_PAYMENT_STATUSES:
            self.db.rollback()
            return False
        meta = dict(pending_payment.payment_metadata or {})
        meta["failure_reason"] = reason or "provider_reported_failure"
        pending_payment.payment_metadata = meta
        pending_payment.status = "failed"
        invoice = self.db.get(Invoice, pending_payment.invoice_id) if pending_payment.invoice_id else None
        if invoice is not None:
            billing.void_invoice(invoice, f"Payment failed: {meta['failure_reason']}")
        self.db.commit()
        return True

    @staticmethod
    def _notify_admins(subject: str, html_content: str):
        try:
            from services.notifications.admin_dispatcher import notify_admins_async
            notify_admins_async(subject=subject, html_content=html_content, category="finance")
        except Exception as e:
            logger.error(f"Failed to notify finance admins: {e}")
