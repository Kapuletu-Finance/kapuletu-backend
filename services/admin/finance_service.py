from common.utils import parse_uuid
from sqlalchemy.orm import Session
from models.subscription import Plan, Subscription, SubscriptionPayment
import uuid
import datetime

class FinanceService:
    """
    FinanceService: Manages platform-wide monetization, plans, and billing overrides.
    """
    def __init__(self, db: Session):
        self.db = db

    def list_plans(self):
        """
        Retrieves all available subscription plans.
        """
        plans = self.db.query(Plan).all()
        return [{
            "plan_id": str(p.plan_id),
            "name": p.name,
            "price": p.price,
            "max_groups": p.max_groups,
            "max_campaigns": p.max_campaigns,
            "max_transactions": p.max_transactions_per_month
        } for p in plans]

    def create_plan(self, data: dict):
        """
        Creates a new subscription tier.
        """
        plan = Plan(
            name=data["name"],
            price=data["price"],
            max_groups=data.get("max_groups", 1),
            max_campaigns=data.get("max_campaigns", 5),
            max_transactions_per_month=data.get("max_transactions", 100)
        )
        self.db.add(plan)
        self.db.commit()
        return str(plan.plan_id)

    def list_all_payments(self, page=1, limit=50):
        """
        Platform-wide financial audit stream.
        """
        payments = self.db.query(SubscriptionPayment).order_by(SubscriptionPayment.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return [{
            "payment_id": str(p.payment_id),
            "user_id": str(p.user_id),
            "amount": p.amount,
            "status": p.status,
            "method": p.payment_method,
            "created_at": p.created_at.isoformat()
        } for p in payments]

    def manual_override_subscription(self, user_id: str, plan_id: str, duration_days: int = 30):
        """
        Manually grants or extends a subscription for a user (e.g. for VIPs or support resolution).
        """
        # 1. Create a dummy payment record for the override
        payment = SubscriptionPayment(
            user_id=user_id,
            subscription_id=uuid.uuid4(), # Placeholder
            amount=0,
            payment_method="admin_override",
            status="success",
            provider_reference=f"ADMIN_GRANT_{datetime.datetime.utcnow().strftime('%Y%m%d')}"
        )
        self.db.add(payment)
        
        # 2. Upsert Subscription
        sub = self.db.query(Subscription).filter(Subscription.user_id == parse_uuid(user_id)).first()
        if not sub:
            sub = Subscription(
                user_id=user_id,
                plan_id=plan_id,
                status="active",
                start_date=datetime.datetime.utcnow(),
                end_date=datetime.datetime.utcnow() + datetime.timedelta(days=duration_days)
            )
            self.db.add(sub)
        else:
            sub.plan_id = plan_id
            sub.status = "active"
            sub.end_date = (sub.end_date or datetime.datetime.utcnow()) + datetime.timedelta(days=duration_days)
            
        self.db.commit()
        return True
