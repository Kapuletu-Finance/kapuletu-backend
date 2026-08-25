from common.utils import parse_uuid
from sqlalchemy.orm import Session
from models.subscription import Subscription, SubscriptionPayment, Plan
from models.audit_log import AuditLog
import datetime
import uuid
import logging
from services.notifications.providers.resend_client import ResendClient
from services.notifications.service import create_notification

logger = logging.getLogger(__name__)

class FulfillmentService:
    """
    FulfillmentService: The bridge between a successful payment and platform features.
    """
    def __init__(self, db: Session):
        self.db = db

    def process_success(self, correlation_id: str, provider_ref: str, amount: float, metadata: dict = None):
        """
        Finalizes the subscription after payment confirmation.
        """
        # 1. Idempotency Check
        # Instead of just checking for provider_ref, we find the pending payment by correlation_id
        pending_payment = self.db.query(SubscriptionPayment).filter(SubscriptionPayment.provider_reference == correlation_id).first()
        
        if pending_payment and pending_payment.status == "success":
            logger.warning(f"Idempotency Trigger: Payment {correlation_id} already processed successfully.")
            return True

        # 2. Resolve Subscription Context
        user_id = metadata.get("user_id") if metadata else None
        plan_id = metadata.get("plan_id") if metadata else None
        
        if not user_id:
            logger.error(f"Fulfillment Failed: Missing user context for correlation {correlation_id}")
            return False

        # 3. Update/Create Subscription
        plan = self.db.query(Plan).filter(Plan.plan_id == plan_id).first()
        sub = self.db.query(Subscription).filter(Subscription.user_id == parse_uuid(user_id)).first()
        
        if not sub:
            sub = Subscription(
                user_id=parse_uuid(user_id),
                plan_id=plan_id,
                status="active",
                start_date=datetime.datetime.utcnow(),
                end_date=datetime.datetime.utcnow() + datetime.timedelta(days=365 if metadata.get("billing_cycle") == "annual" else 30)
            )
            self.db.add(sub)
        else:
            sub.plan_id = plan_id
            sub.status = "active"
            # Extend existing subscription
            current_end = sub.end_date if sub.end_date and sub.end_date > datetime.datetime.utcnow() else datetime.datetime.utcnow()
            days_to_add = 365 if metadata.get("billing_cycle") == "annual" else 30
            sub.end_date = current_end + datetime.timedelta(days=days_to_add)

        # 4. Record Payment
        if pending_payment:
            pending_payment.status = "success"
            
            # Store receipt number safely without overwriting the correlation ID
            # that the frontend is actively polling for.
            new_meta = dict(pending_payment.payment_metadata) if pending_payment.payment_metadata else {}
            new_meta["receipt_number"] = provider_ref
            pending_payment.payment_metadata = new_meta
            self.db.add(pending_payment)
        else:
            payment = SubscriptionPayment(
                user_id=parse_uuid(user_id),
                subscription_id=sub.subscription_id,
                amount=amount,
                status="success",
                payment_method="gateway",
                provider_reference=provider_ref
            )
            self.db.add(payment)

        # 5. Forensic Audit
        audit = AuditLog(
            actor_id=parse_uuid(user_id),
            action="SUBSCRIPTION_UPGRADED",
            entity_type="PLAN",
            entity_id=str(plan_id),
            details={"amount": amount, "ref": provider_ref, "correlation": correlation_id}
        )
        self.db.add(audit)

        self.db.commit()
        
        # 6. Dispatch Email Receipt
        email = metadata.get("email") if metadata else None
        name = metadata.get("name", "KapuLetu User") if metadata else "KapuLetu User"
        if email:
            try:
                resend = ResendClient()
                subject = f"Your KapuLetu {plan.name} Receipt"
                html_body = f'''
                <div style="font-family: sans-serif; max-width: 600px; margin: auto;">
                    <h2>Payment Successful!</h2>
                    <p>Hi {name},</p>
                    <p>Thank you for subscribing to KapuLetu <strong>{plan.name}</strong>.</p>
                    <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                        <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Amount Paid:</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">Ksh {amount:,.2f}</td></tr>
                        <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>M-Pesa Receipt:</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{provider_ref}</td></tr>
                    </table>
                    <p style="margin-top: 20px;">Your workspace has been successfully upgraded. Welcome aboard!</p>
                </div>
                '''
                resend.send_email(email, subject, html_body)
            except Exception as e:
                logger.error(f"Failed to send email receipt: {e}")
                
        # 7. In-App Notification
        try:
            create_notification(
                db=self.db,
                user_id=user_id,
                title="Subscription Upgraded",
                message=f"We received your payment of Ksh {amount:,.2f}. Your workspace is now on the {plan.name} tier. Receipt: {provider_ref}",
                type="subscription_update",
                related_entity_id=str(sub.subscription_id)
            )
        except Exception as e:
            logger.error(f"Failed to create in-app notification: {e}")

        logger.info(f"Fulfillment Successful: User {user_id} upgraded to {plan.name}")
        return True
