import os
import sys
import datetime
import logging
import threading
import time
import zoneinfo

# Ensure backend root is in PYTHONPATH before importing local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.utils import parse_uuid
from sqlalchemy import select, text
from common.database import SessionLocal
from common.system_config_service import get_system_config, set_system_config
from models.audit_log import AuditLog
from models.subscription import Subscription, Plan
from models.users import User
from services.finance import billing
from services.finance.plans import get_free_plan

logger = logging.getLogger(__name__)

from services.notifications.templates.render import render_email_template
from services.communications.outbox import queue_email

EAT = zoneinfo.ZoneInfo("Africa/Nairobi")
LAST_RUN_KEY = "subscription_sweep_last_run"
# First time the sweep ever ran. Subscriptions that lapsed before then get their grace period from this
# moment instead of from their old end date, so nobody is downgraded without notice on day one.
STARTED_AT_KEY = "subscription_sweep_started_at"
ADVISORY_LOCK_KEY = 74_210_301  # arbitrary, unique to this job


def send_real_reminder(user: User, plan_name: str, days_left: int):
    """
    Queues a reminder email synchronously and logs it to CommunicationLog.
    """
    if not user.email:
        return
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

        queue_email(db, user.email, subject, html_body, kind="subscription_reminder", user_id=user.user_id,
                    layout=False)
        db.commit()
        logger.info(f"Successfully sent {days_left}-day reminder email to {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to queue reminder email to {user.email}: {e}")
    finally:
        db.close()


def _grace_days(db) -> int:
    return max(0, int(billing.get_settings(db).grace_period_days or 0))


def _sweep_started_at(db, now: datetime.datetime) -> datetime.datetime:
    value = get_system_config(db, STARTED_AT_KEY)
    if value:
        try:
            return datetime.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            pass
    set_system_config(db, STARTED_AT_KEY, now.isoformat())
    return now


def run_expiry_sweep():
    """
    Runs the daily sweep: reminds users before their plan ends, tells them when it has ended,
    and moves them to the free tier once the grace period (Billing Rules) has passed.
    """
    logger.info("Starting Daily Subscription Expiry Sweep...")
    db = SessionLocal()
    locked = False

    try:
        try:
            locked = bool(db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar())
        except Exception:
            db.rollback()
            locked = True  # not PostgreSQL; nothing else to coordinate with
        if not locked:
            logger.info("Expiry sweep already running in another process; skipping.")
            return

        now = datetime.datetime.utcnow()
        free_plan = get_free_plan(db)
        if not free_plan:
            logger.error("System Configuration Error: no free-tier plan found in database.")
            return

        grace = datetime.timedelta(days=_grace_days(db))
        started_at = _sweep_started_at(db, now)

        active_subs = db.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.end_date != None,
                Subscription.plan_id != free_plan.plan_id,
            )
        ).scalars().all()

        for sub in active_subs:
            try:
                user = db.execute(select(User).where(User.user_id == parse_uuid(sub.user_id))).scalars().first()
                if not user:
                    continue

                plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
                plan_name = plan.name if plan else "paid"

                if sub.end_date > now:
                    # Reminders: T-1 (under 24 hours), T-3, T-7
                    days_left = (sub.end_date - now).days
                    if days_left in (0, 3, 7):
                        send_real_reminder(user, plan_name, days_left or 1)
                    continue

                # Lapsed. The grace period runs from the end date, or from the sweep's first run for older lapses.
                effective_end = max(sub.end_date, started_at)
                if (now - effective_end).days == 0:
                    send_real_reminder(user, plan_name, 0)

                if now < effective_end + grace:
                    continue

                logger.info(f"Downgrading user {user.user_id} from {plan_name} to {free_plan.name} (ended {sub.end_date:%Y-%m-%d}).")
                db.add(AuditLog(
                    actor_id=None,
                    action="SUBSCRIPTION_EXPIRED",
                    entity_type="SUBSCRIPTION",
                    entity_id=str(sub.subscription_id),
                    details={
                        "user_id": str(user.user_id),
                        "from_plan": plan_name,
                        "to_plan": free_plan.name,
                        "ended_at": sub.end_date.isoformat(),
                        "grace_days": grace.days,
                    },
                ))
                from_plan_id = sub.plan_id
                sub.plan_id = free_plan.plan_id
                sub.status = "active"
                sub.end_date = None
                sub.is_auto_renew = False
                sub.is_trial = False
                sub.price_id = None
                billing.record_event(db, sub, "expired", from_plan_id=from_plan_id, to_plan_id=free_plan.plan_id,
                                     reason=f"Lapsed; {grace.days}-day grace period over", at=now)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Expiry sweep failed for subscription {sub.subscription_id}: {e}")

        set_system_config(db, LAST_RUN_KEY, datetime.datetime.now(EAT).date().isoformat())
        logger.info("Daily Expiry Sweep Completed.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during expiry sweep: {e}")
    finally:
        if locked:
            try:
                db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
                db.commit()
            except Exception:
                db.rollback()
        db.close()


def _sweep_due() -> bool:
    run_hour = int(os.getenv("SUBSCRIPTION_SWEEP_HOUR_EAT", "6"))
    now_eat = datetime.datetime.now(EAT)
    if now_eat.hour < run_hour:
        return False
    db = SessionLocal()
    try:
        return get_system_config(db, LAST_RUN_KEY) != now_eat.date().isoformat()
    finally:
        db.close()


def _scheduler_loop(check_every_seconds: int):
    while True:
        try:
            if _sweep_due():
                run_expiry_sweep()
        except Exception as e:
            logger.error(f"Subscription sweep scheduler error: {e}")
        time.sleep(check_every_seconds)


_scheduler_started = False


def start_expiry_scheduler(check_every_seconds: int = 1800):
    """
    Runs the sweep once a day (after SUBSCRIPTION_SWEEP_HOUR_EAT, default 06:00 Nairobi time) in a daemon
    thread. Restart-safe: the last run date is stored in system config. Disable with SUBSCRIPTION_SWEEP_ENABLED=false.
    """
    global _scheduler_started
    if _scheduler_started or os.getenv("SUBSCRIPTION_SWEEP_ENABLED", "true").lower() != "true":
        return
    _scheduler_started = True
    threading.Thread(target=_scheduler_loop, args=(check_every_seconds,), daemon=True, name="subscription-sweep").start()
    logger.info("Subscription expiry scheduler started.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_expiry_sweep()
