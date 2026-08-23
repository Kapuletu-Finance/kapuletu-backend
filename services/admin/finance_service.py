from common.utils import parse_uuid
from sqlalchemy.orm import Session
from models.subscription import Plan, Subscription, SubscriptionPayment
import uuid
import datetime

from models.users import User

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
        results = self.db.query(SubscriptionPayment, User, Plan).join(
            User, SubscriptionPayment.user_id == User.user_id
        ).outerjoin(
            Subscription, SubscriptionPayment.subscription_id == Subscription.subscription_id
        ).outerjoin(
            Plan, Subscription.plan_id == Plan.plan_id
        ).order_by(SubscriptionPayment.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        
        total = self.db.query(SubscriptionPayment).count()

        return {
            "items": [{
                "payment_id": str(p.payment_id),
                "user_id": str(p.user_id),
                "user_name": f"{u.first_name} {u.last_name}".strip() if u else "Unknown User",
                "plan_name": pl.name if pl else "Unknown Plan",
                "amount": p.amount,
                "status": p.status,
                "method": p.payment_method,
                "created_at": p.created_at.isoformat() if p.created_at else None
            } for p, u, pl in results],
            "total": total,
            "page": page,
            "limit": limit
        }

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
        sub = self.db.query(Subscription).filter(Subscription.user_id ==parse_uuid(parse_uuid(user_id))).first()
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
