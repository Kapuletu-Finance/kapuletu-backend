import uuid
from common.database import SessionLocal
from models import User, Plan, Subscription
import datetime

def seed():
    """
    Database Seeding Utility: Populates the DB with initial required records.
    """
    print("Populating database with core plans and administrative users...")
    db = SessionLocal()
    try:
        # 1. Create Default Plans
        basic_plan = db.query(Plan).filter(Plan.name == "Basic").first()
        if not basic_plan:
            basic_plan = Plan(
                name="Basic",
                max_groups=1,
                max_campaigns=5,
                max_transactions_per_month=100,
                price=0
            )
            db.add(basic_plan)
            print("Added Basic Plan.")

        pro_plan = db.query(Plan).filter(Plan.name == "Pro").first()
        if not pro_plan:
            pro_plan = Plan(
                name="Pro",
                max_groups=5,
                max_campaigns=20,
                max_transactions_per_month=1000,
                price=5000
            )
            db.add(pro_plan)
            print("Added Pro Plan.")

        db.commit()

        # 2. Create Default Admin User
        admin_user = db.query(User).filter(User.email == "admin@kapuletu.com").first()
        if not admin_user:
            admin_user = User(
                user_id=uuid.uuid4(),
                full_name="System Admin",
                email="admin@kapuletu.com",
                phone_number="+254700000000",
                password_hash="hashed_password_here", # In real app, use pwd_context.hash()
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print("Added Admin User.")
            
            # Subscribe admin to Pro plan
            sub = Subscription(
                user_id=admin_user.user_id,
                plan_id=pro_plan.plan_id,
                status="active",
                start_date=datetime.datetime.utcnow()
            )
            db.add(sub)
            db.commit()
            print("Subscribed Admin to Pro Plan.")

        print("Seeding completed successfully.")
    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed()
