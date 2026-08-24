import os
import sys
import datetime
import logging
from common.utils import parse_uuid
from sqlalchemy import select

# Ensure backend root is in PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.database import SessionLocal
from models.subscription import Subscription, Plan
from models.users import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def mock_send_reminder(user: User, plan_name: str, days_left: int):
    """
    Simulates sending an email or WhatsApp reminder.
    In production, this would integrate with Resend (Email) or Meta (WhatsApp).
    """
    if days_left == 0:
        logger.info(f"[NOTIFY] To: {user.email} - Your {plan_name} trial has expired. You have been downgraded to the Free tier.")
    elif days_left == 1:
        logger.info(f"[NOTIFY] To: {user.email} - URGENT: Your {plan_name} trial expires in 24 hours!")
    else:
        logger.info(f"[NOTIFY] To: {user.email} - Reminder: Your {plan_name} trial expires in {days_left} days.")

def run_expiry_sweep():
    """
    Runs the daily sweep to find expiring subscriptions, send reminders, and downgrade expired accounts.
    """
    logger.info("Starting Daily Subscription Expiry Sweep...")
    db = SessionLocal()
    
    try:
        now = datetime.datetime.utcnow()
        
        # Get Free Plan ID for downgrades
        free_plan = db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
        if not free_plan:
            logger.error("System Configuration Error: 'Free' plan not found in database.")
            return

        active_subs = db.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.end_date != None
            )
        ).scalars().all()

        for sub in active_subs:
            user = db.execute(select(User).where(User.user_id == parse_uuid(sub.user_id))).scalars().first()
            if not user:
                continue
                
            plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
            plan_name = plan.name if plan else "Pro"
            
            delta = sub.end_date - now
            days_left = delta.days
            
            # Day 0: Expiration & Downgrade
            if days_left < 0:
                logger.info(f"Downgrading User {user.email} to Free Tier. (Expired {abs(days_left)} days ago)")
                sub.plan_id = free_plan.plan_id
                sub.status = "active"
                sub.end_date = None
                mock_send_reminder(user, plan_name, 0)
                
            # Reminders: T-1 (24 hours), T-3, T-7
            elif days_left == 0:  # < 24 hours
                mock_send_reminder(user, plan_name, 1)
            elif days_left == 3:
                mock_send_reminder(user, plan_name, 3)
            elif days_left == 7:
                mock_send_reminder(user, plan_name, 7)

        db.commit()
        logger.info("Daily Expiry Sweep Completed.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during expiry sweep: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_expiry_sweep()
