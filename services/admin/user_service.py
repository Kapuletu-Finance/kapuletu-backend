from common.utils import parse_uuid
from sqlalchemy.orm import Session
from models.users import User
from models.group import Group
from models.subscription import SubscriptionPayment, Subscription, Plan
from models.audit_log import AuditLog
from models.campaign import Campaign
import uuid
import datetime
from sqlalchemy import func, or_

class UserService:
    """
    UserService: Manages administrative visibility and control over Treasurer accounts.
    """
    def __init__(self, db: Session):
        self.db = db

    def list_treasurers(self, page=1, limit=50, status=None, q=None):
        """
        Lists all treasurers with high-level metadata.
        """
        # Subquery to count successful payments per user
        payment_counts = self.db.query(
            SubscriptionPayment.user_id,
            func.count(SubscriptionPayment.payment_id).label("payment_count")
        ).filter(SubscriptionPayment.status == "success").group_by(SubscriptionPayment.user_id).subquery()

        query = self.db.query(
            User, 
            Plan.name.label("plan_name"),
            func.coalesce(payment_counts.c.payment_count, 0).label("payment_count")
        ).outerjoin(
            Subscription, User.user_id == Subscription.user_id
        ).outerjoin(
            Plan, Subscription.plan_id == Plan.plan_id
        ).outerjoin(
            payment_counts, User.user_id == payment_counts.c.user_id
        ).filter(User.role == "treasurer")
        
        if status == "active":
            query = query.filter(User.is_active == True)
        elif status == "suspended":
            query = query.filter(User.is_active == False)
            
        if q:
            search_term = f"%{q}%"
            query = query.filter(
                or_(
                    User.first_name.ilike(search_term),
                    User.last_name.ilike(search_term),
                    User.email.ilike(search_term)
                )
            )
            
        total = query.count()
        users_with_plans = query.offset((page - 1) * limit).limit(limit).all()
        
        # Calculate KPIs
        now = datetime.datetime.utcnow()
        start_of_month = datetime.datetime(now.year, now.month, 1)
        
        total_treasurers = self.db.query(func.count(User.user_id)).filter(User.role == "treasurer").scalar() or 0
        active_treasurers = self.db.query(func.count(User.user_id)).filter(User.role == "treasurer", User.is_active == True).scalar() or 0
        suspended_treasurers = total_treasurers - active_treasurers
        new_this_month = self.db.query(func.count(User.user_id)).filter(User.role == "treasurer", User.created_at >= start_of_month).scalar() or 0
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "kpis": {
                "total": total_treasurers,
                "active": active_treasurers,
                "suspended": suspended_treasurers,
                "new_this_month": new_this_month
            },
            "users": [{
                "user_id": str(u.user_id),
                "slug": u.slug or str(u.user_id),
                "full_name": f"{u.first_name} {u.last_name}",
                "email": u.email,
                "phone": u.phone_number,
                "is_active": u.is_active,
                "plan_name": f"{plan_name} (Trial)" if (plan_name == "Professional" and payment_count == 0) else (plan_name or "Basic"),
                "created_at": u.created_at.isoformat() if u.created_at else None
            } for u, plan_name, payment_count in users_with_plans]
        }

    def get_recent_activity(self):
        """
        Returns recent users segmented into 'active_now' (last 15 mins) and 'recent' (last 24 hours).
        """
        now = datetime.datetime.utcnow()
        fifteen_mins_ago = now - datetime.timedelta(minutes=15)
        twenty_four_hours_ago = now - datetime.timedelta(hours=24)
        
        users = self.db.query(User).filter(
            User.last_active_at >= twenty_four_hours_ago
        ).order_by(User.last_active_at.desc()).all()
        
        active_now = []
        recent = []
        
        for u in users:
            data = {
                "user_id": str(u.user_id),
                "slug": u.slug or str(u.user_id),
                "full_name": f"{u.first_name} {u.last_name}",
                "email": u.email,
                "role": u.role,
                "last_active_at": u.last_active_at.isoformat() if u.last_active_at else None
            }
            if u.last_active_at >= fifteen_mins_ago:
                active_now.append(data)
            else:
                recent.append(data)
                
        return {
            "active_now": active_now,
            "recent": recent,
            "kpis": {
                "active_now_count": len(active_now),
                "recent_count": len(recent)
            }
        }

    def get_treasurer_details(self, identifier: str):
        """
        Retrieves deep-dive data for a specific treasurer.
        """
        try:
            uid = parse_uuid(identifier)
            user = self.db.query(User).filter(User.user_id == uid).first()
        except ValueError:
            user = self.db.query(User).filter(User.slug == identifier).first()
            
        if not user:
            return None
            
        group_count = self.db.query(Group).filter(Group.owner_id == user.user_id).count()
        
        # Determine plan name and trial status
        sub = self.db.query(Subscription, Plan).outerjoin(Plan, Subscription.plan_id == Plan.plan_id).filter(Subscription.user_id == user.user_id).first()
        payment_count = self.db.query(func.count(SubscriptionPayment.payment_id)).filter(
            SubscriptionPayment.user_id == user.user_id,
            SubscriptionPayment.status == "success"
        ).scalar() or 0
        
        plan_name = "Basic"
        if sub and sub.Plan:
            if sub.Plan.name == "Professional" and payment_count == 0:
                plan_name = "Professional (Trial)"
            else:
                plan_name = sub.Plan.name
        
        return {
            "profile": {
                "user_id": str(user.user_id),
                "slug": user.slug,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": user.phone_number,
                "role": user.role,
                "is_active": user.is_active,
                "plan_name": plan_name,
                "created_at": user.created_at.isoformat()
            },
            "stats": {
                "total_groups": group_count
            }
        }

    def get_user_groups(self, identifier: str):
        """
        Lists all community groups owned by the treasurer.
        """
        try:
            uid = parse_uuid(identifier)
            user = self.db.query(User).filter(User.user_id == uid).first()
        except ValueError:
            user = self.db.query(User).filter(User.slug == identifier).first()
        
        if not user: return []
        
        groups = self.db.query(Group).filter(Group.owner_id == user.user_id).all()
        
        result = []
        for g in groups:
            campaigns = self.db.query(Campaign).filter(Campaign.group_id == g.group_id).all()
            result.append({
                "group_id": str(g.group_id),
                "name": g.group_name,
                "description": g.description,
                "created_at": g.created_at.isoformat(),
                "campaigns": [{
                    "campaign_id": str(c.campaign_id),
                    "name": c.title,
                    "target_amount": c.target_amount,
                    "status": c.status
                } for c in campaigns]
            })
        return result

    def get_user_recent_activity(self, identifier: str, limit: int = 50):
        """
        Retrieves recent audit log actions performed by this user.
        """
        try:
            uid = parse_uuid(identifier)
            user = self.db.query(User).filter(User.user_id == uid).first()
        except ValueError:
            user = self.db.query(User).filter(User.slug == identifier).first()
            
        if not user:
            return []
            
        logs = self.db.query(AuditLog).filter(
            AuditLog.actor_id == user.user_id
        ).order_by(AuditLog.created_at.desc()).limit(limit).all()
        
        return [{
            "log_id": str(l.log_id),
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": str(l.entity_id) if l.entity_id else None,
            "details": l.details,
            "timestamp": l.created_at.isoformat()
        } for l in logs]

    def update_user_status(self, identifier: str, is_active: bool, reason: str = None):
        """
        Suspends or reactivates a user account.
        """
        try:
            uid = parse_uuid(identifier)
            user = self.db.query(User).filter(User.user_id == uid).first()
        except ValueError:
            user = self.db.query(User).filter(User.slug == identifier).first()
            
        if not user:
            return False
            
        user.is_active = is_active
        self.db.commit()
        
        # Note: In production, we would also trigger a Cognito AdminUpdateUser call
        # to globally disable the user's ability to get new tokens.
        
        return True

    def escalated_update(self, identifier: str, updates: dict):
        """
        Allows an admin to manually correct user profile data.
        """
        try:
            uid = parse_uuid(identifier)
            user = self.db.query(User).filter(User.user_id == uid).first()
        except ValueError:
            user = self.db.query(User).filter(User.slug == identifier).first()
            
        if not user:
            return False
            
        if "first_name" in updates: user.first_name = updates["first_name"]
        if "last_name" in updates: user.last_name = updates["last_name"]
        if "email" in updates: user.email = updates["email"]
        if "phone_number" in updates: user.phone_number = updates["phone_number"]
        
        self.db.commit()
        return True

    def upgrade_user_role(self, identifier: str, new_role: str):
        """
        Upgrades or changes the user's role (e.g. treasurer to admin).
        """
        from common.enums import UserRole
        valid_roles = [e.value for e in UserRole]
        if new_role not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of {valid_roles}")
            
        try:
            uid = parse_uuid(identifier)
            user = self.db.query(User).filter(User.user_id == uid).first()
        except ValueError:
            user = self.db.query(User).filter(User.slug == identifier).first()
            
        if not user:
            return False
            
        user.role = new_role
        self.db.commit()
        return True
