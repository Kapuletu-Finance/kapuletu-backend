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
            "max_transactions": p.max_transactions_per_month,
            "allowed_features": p.allowed_features or []
        } for p in plans]

    def get_plan(self, plan_id: str):
        """
        Retrieves a specific plan.
        """
        try:
            parsed_id = parse_uuid(plan_id)
        except ValueError:
            return None
            
        p = self.db.query(Plan).filter(Plan.plan_id == parsed_id).first()
        if not p: return None
        return {
            "plan_id": str(p.plan_id),
            "name": p.name,
            "price": p.price,
            "max_groups": p.max_groups,
            "max_campaigns": p.max_campaigns,
            "max_transactions": p.max_transactions_per_month,
            "allowed_features": p.allowed_features or []
        }

    def update_plan(self, plan_id: str, data: dict):
        """
        Updates an existing plan dynamically.
        """
        try:
            parsed_id = parse_uuid(plan_id)
        except ValueError:
            return False
            
        p = self.db.query(Plan).filter(Plan.plan_id == parsed_id).first()
        if not p: return False
        
        if "name" in data: p.name = data["name"]
        if "price" in data: p.price = data["price"]
        if "max_groups" in data: p.max_groups = data["max_groups"]
        if "max_campaigns" in data: p.max_campaigns = data["max_campaigns"]
        if "max_transactions" in data: p.max_transactions_per_month = data["max_transactions"]
        if "allowed_features" in data: p.allowed_features = data["allowed_features"]
        
        self.db.commit()
        return True

    def create_plan(self, data: dict):
        """
        Creates a new subscription tier.
        """
        plan = Plan(
            name=data["name"],
            price=data["price"],
            max_groups=data.get("max_groups", 1),
            max_campaigns=data.get("max_campaigns", 5),
            max_transactions_per_month=data.get("max_transactions", 100),
            allowed_features=data.get("allowed_features", [])
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
                "transaction_type": p.transaction_type,
                "created_at": p.created_at.isoformat() if p.created_at else None
            } for p, u, pl in results],
            "total": total,
            "page": page,
            "limit": limit
        }

    def process_refund(self, payment_id: str, reason: str = ""):
        """
        Processes a Record-Only refund for a payment.
        """
        original_payment = self.db.query(SubscriptionPayment).filter(
            SubscriptionPayment.payment_id == parse_uuid(payment_id)
        ).first()
        
        if not original_payment or original_payment.status != "success":
            return False
            
        # Create a negative ledger entry
        refund_payment = SubscriptionPayment(
            user_id=original_payment.user_id,
            subscription_id=original_payment.subscription_id,
            amount=-abs(original_payment.amount),
            currency=original_payment.currency,
            status="success",
            payment_method="admin_refund",
            transaction_type="refund",
            provider_reference=original_payment.provider_reference,
            payment_metadata={"reason": reason, "original_payment_id": str(original_payment.payment_id)}
        )
        
        # We also might want to downgrade the user, but for now just process the refund ledger
        
        self.db.add(refund_payment)
        self.db.commit()
        return True

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
        # 2. Upsert Subscription
        sub = self.db.query(Subscription).filter(Subscription.user_id == parse_uuid(user_id)).first()
        if not sub:
            sub = Subscription(
                user_id=parse_uuid(user_id),
                plan_id=parse_uuid(plan_id),
                status="active",
                start_date=datetime.datetime.utcnow(),
                end_date=datetime.datetime.utcnow() + datetime.timedelta(days=duration_days)
            )
            self.db.add(sub)
        else:
            sub.plan_id = parse_uuid(plan_id)
            sub.status = "active"
            sub.end_date = (sub.end_date or datetime.datetime.utcnow()) + datetime.timedelta(days=duration_days)
            
        self.db.commit()
        return True
