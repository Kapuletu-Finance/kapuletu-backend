from common.utils import parse_uuid
from sqlalchemy.orm import Session
from models.subscription import Subscription, SubscriptionPayment, Plan
from models.audit_log import AuditLog
import datetime
import uuid
import logging

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
                user_id=user_id,
                plan_id=plan_id,
                status="active",
                start_date=datetime.datetime.utcnow(),
                end_date=datetime.datetime.utcnow() + datetime.timedelta(days=30)
            )
            self.db.add(sub)
        else:
            sub.plan_id = plan_id
            sub.status = "active"
            # Extend existing subscription
            current_end = sub.end_date if sub.end_date and sub.end_date > datetime.datetime.utcnow() else datetime.datetime.utcnow()
            sub.end_date = current_end + datetime.timedelta(days=30)

        # 4. Record Payment
        if pending_payment:
            pending_payment.status = "success"
            pending_payment.provider_reference = provider_ref # Update to the receipt number if it changed
        else:
            payment = SubscriptionPayment(
                user_id=user_id,
                subscription_id=sub.subscription_id,
                amount=amount,
                status="success",
                payment_method="gateway",
                provider_reference=provider_ref
            )
            self.db.add(payment)

        # 5. Forensic Audit
        audit = AuditLog(
            actor_id=user_id,
            action="SUBSCRIPTION_UPGRADED",
            entity_type="PLAN",
            entity_id=str(plan_id),
            details={"amount": amount, "ref": provider_ref, "correlation": correlation_id}
        )
        self.db.add(audit)

        self.db.commit()
        logger.info(f"Fulfillment Successful: User {user_id} upgraded to {plan_id}")
        return True
