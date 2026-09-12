import os
import sys
import datetime
import logging

# Ensure backend root is in PYTHONPATH before importing local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.utils import parse_uuid
from sqlalchemy import select
from common.database import SessionLocal
from models.subscription import Subscription, Plan
from models.users import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from services.notifications.templates.render import render_email_template
from services.notifications.tasks import send_email_task
from models.communication_logs import CommunicationLog

def send_real_reminder(user: User, plan_name: str, days_left: int):
    """
    Queues a reminder email synchronously and logs it to CommunicationLog.
    """
    db = SessionLocal()
    try:
        name = user.first_name if user.first_name else "User"
        
        if days_left == 0:
            subject = f"Your KapuLetu {plan_name} plan has expired"
        elif days_left == 1:
            subject = f"Urgent: Your KapuLetu {plan_name} plan expires in 24 hours"
        else:
            subject = f"Reminder: Your KapuLetu {plan_name} plan expires in {days_left} days"

        from common.config import get_config
        dashboard_url = get_config().FRONTEND_URL.rstrip('/') + "/dashboard"

        html_body = render_email_template(
            "subscription_reminder.html",
            name=name,
            plan_name=plan_name,
            days_left=days_left,
            dashboard_url=dashboard_url
        )
        
        log = CommunicationLog(
            user_id=user.user_id,
            channel="EMAIL",
            destination=user.email,
            subject=subject,
            status="QUEUED"
        )
        db.add(log)
        db.commit()

        send_email_task(str(log.log_id), user.email, subject, html_body)
        logger.info(f"Successfully sent {days_left}-day reminder email to {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to queue reminder email to {user.email}: {e}")
    finally:
        db.close()

def run_expiry_sweep():
    """
    Runs the daily sweep to find expiring subscriptions, send reminders, and downgrade expired accounts.
    """
    logger.info("Starting Daily Subscription Expiry Sweep...")
    db = SessionLocal()
    
    try:
        now = datetime.datetime.utcnow()
        
        # Get Basic Plan ID for downgrades
        free_plan = db.execute(select(Plan).where(Plan.name == "Basic")).scalars().first()
        if not free_plan:
            logger.error("System Configuration Error: 'Basic' plan not found in database.")
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
                logger.info(f"Downgrading User {user.email} to Basic Tier. (Expired {abs(days_left)} days ago)")
                sub.plan_id = free_plan.plan_id
                sub.status = "active"
                sub.end_date = None
                send_real_reminder(user, plan_name, 0)
                
            # Reminders: T-1 (24 hours), T-3, T-7
            elif days_left == 0:  # < 24 hours
                send_real_reminder(user, plan_name, 1)
            elif days_left == 3:
                send_real_reminder(user, plan_name, 3)
            elif days_left == 7:
                send_real_reminder(user, plan_name, 7)

        db.commit()
        logger.info("Daily Expiry Sweep Completed.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during expiry sweep: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_expiry_sweep()
