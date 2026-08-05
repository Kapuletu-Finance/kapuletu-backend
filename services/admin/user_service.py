from sqlalchemy.orm import Session
from models.users import User
from models.group import Group
from models.subscription import SubscriptionPayment
import uuid

class UserService:
    """
    UserService: Manages administrative visibility and control over Treasurer accounts.
    """
    def __init__(self, db: Session):
        self.db = db

    def list_treasurers(self, page=1, limit=50, status=None):
        """
        Lists all treasurers with high-level metadata.
        """
        query = self.db.query(User).filter(User.role == "treasurer")
        
        if status == "active":
            query = query.filter(User.is_active == True)
        elif status == "suspended":
            query = query.filter(User.is_active == False)
            
        total = query.count()
        users = query.offset((page - 1) * limit).limit(limit).all()
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "users": [{
                "user_id": str(u.user_id),
                "full_name": f"{u.first_name} {u.last_name}",
                "email": u.email,
                "phone": u.phone_number,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat()
            } for u in users]
        }

    def get_treasurer_details(self, user_id: str):
        """
        Retrieves deep-dive data for a specific treasurer.
        """
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return None
            
        group_count = self.db.query(Group).filter(Group.owner_id == user_id).count()
        
        return {
            "profile": {
                "user_id": str(user.user_id),
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": user.phone_number,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat()
            },
            "stats": {
                "total_groups": group_count
            }
        }

    def get_user_groups(self, user_id: str):
        """
        Lists all community groups owned by the treasurer.
        """
        groups = self.db.query(Group).filter(Group.owner_id == user_id).all()
        return [{
            "group_id": str(g.group_id),
            "name": g.group_name,
            "description": g.description,
            "created_at": g.created_at.isoformat()
        } for g in groups]

    def update_user_status(self, user_id: str, is_active: bool, reason: str = None):
        """
        Suspends or reactivates a user account.
        """
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
            
        user.is_active = is_active
        self.db.commit()
        
        # Note: In production, we would also trigger a Cognito AdminUpdateUser call
        # to globally disable the user's ability to get new tokens.
        
        return True

    def escalated_update(self, user_id: str, updates: dict):
        """
        Allows an admin to manually correct user profile data.
        """
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
            
        if "first_name" in updates: user.first_name = updates["first_name"]
        if "last_name" in updates: user.last_name = updates["last_name"]
        if "email" in updates: user.email = updates["email"]
        if "phone_number" in updates: user.phone_number = updates["phone_number"]
        
        self.db.commit()
        return True

    def upgrade_user_role(self, user_id: str, new_role: str):
        """
        Upgrades or changes the user's role (e.g. treasurer to admin).
        """
        from common.enums import UserRole
        valid_roles = [e.value for e in UserRole]
        if new_role not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of {valid_roles}")
            
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
            
        user.role = new_role
        self.db.commit()
        return True
