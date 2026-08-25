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
                billing_cycle = metadata.get("billing_cycle", "monthly").title()
                html_body = f'''
                <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #1f2937; margin: 0; font-size: 24px;">KapuLetu</h1>
                        <p style="color: #6b7280; font-size: 14px; margin-top: 5px;">Payment Receipt</p>
                    </div>
                    
                    <div style="background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <h2 style="color: #10b981; margin-top: 0; text-align: center;">Payment Successful!</h2>
                        <p style="color: #374151; font-size: 16px;">Hi {name},</p>
                        <p style="color: #374151; font-size: 16px;">Thank you for subscribing to the <strong>KapuLetu {plan.name}</strong> plan.</p>
                        
                        <div style="margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                            <h3 style="color: #111827; font-size: 16px; margin-bottom: 15px;">Transaction Details</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 10px 0; color: #6b7280; font-size: 15px; border-bottom: 1px solid #f3f4f6;">Plan</td>
                                    <td style="padding: 10px 0; color: #111827; font-size: 15px; font-weight: 600; text-align: right; border-bottom: 1px solid #f3f4f6;">{plan.name} ({billing_cycle})</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; color: #6b7280; font-size: 15px; border-bottom: 1px solid #f3f4f6;">Amount Paid</td>
                                    <td style="padding: 10px 0; color: #111827; font-size: 15px; font-weight: 600; text-align: right; border-bottom: 1px solid #f3f4f6;">Ksh {amount:,.2f}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; color: #6b7280; font-size: 15px; border-bottom: 1px solid #f3f4f6;">Receipt No.</td>
                                    <td style="padding: 10px 0; color: #111827; font-size: 15px; font-weight: 600; text-align: right; border-bottom: 1px solid #f3f4f6;">{provider_ref}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; color: #6b7280; font-size: 15px; border-bottom: 1px solid #f3f4f6;">Date</td>
                                    <td style="padding: 10px 0; color: #111827; font-size: 15px; font-weight: 600; text-align: right; border-bottom: 1px solid #f3f4f6;">{datetime.datetime.utcnow().strftime('%B %d, %Y')}</td>
                                </tr>
                            </table>
                        </div>
                        
                        <p style="color: #374151; font-size: 15px; margin-top: 30px; line-height: 1.5;">Your workspace has been successfully upgraded and your new limits are now active. Welcome aboard!</p>
                    </div>
                    
                    <div style="text-align: center; margin-top: 20px; color: #9ca3af; font-size: 12px;">
                        <p>© {datetime.datetime.utcnow().year} KapuLetu Systems. All rights reserved.</p>
                    </div>
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
