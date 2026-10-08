"""
Daily finance jobs, run once a day after FINANCE_JOBS_HOUR_EAT (default 07:00 Nairobi) in a daemon thread:
  1. send scheduled reports that are due;
  2. reconcile yesterday's Flutterwave transactions (when FLW_SECRET_KEY is set).
Restart-safe (the last run date is kept in system config); disable with FINANCE_JOBS_ENABLED=false.
"""
import datetime
import logging
import os
import threading
import time

from common.database import SessionLocal
from common.system_config_service import get_system_config, set_system_config

logger = logging.getLogger(__name__)

LAST_RUN_KEY = "finance_jobs_last_run"
EAT_OFFSET = datetime.timedelta(hours=3)


def run_finance_jobs(now: datetime.datetime = None) -> dict:
    from .reconciliation import ReconciliationService
    from .schedules import ScheduleService

    now = now or datetime.datetime.utcnow()
    result = {"reports_sent": 0, "flutterwave": None}
    db = SessionLocal()
    try:
        try:
            result["reports_sent"] = ScheduleService(db).send_due(now)
        except Exception as e:
            db.rollback()
            logger.error(f"Scheduled reports failed: {e}")

        if os.environ.get("FLW_SECRET_KEY"):
            yesterday = (now + EAT_OFFSET).date() - datetime.timedelta(days=1)
            try:
                result["flutterwave"] = ReconciliationService(db).pull_flutterwave(yesterday, yesterday)
            except Exception as e:
                db.rollback()
                logger.error(f"Flutterwave reconciliation failed: {e}")

        set_system_config(db, LAST_RUN_KEY, (now + EAT_OFFSET).date().isoformat())
    finally:
        db.close()
    logger.info(f"Finance jobs done: {result}")
    return result


def _due() -> bool:
    now_eat = datetime.datetime.utcnow() + EAT_OFFSET
    if now_eat.hour < int(os.getenv("FINANCE_JOBS_HOUR_EAT", "7")):
        return False
    db = SessionLocal()
    try:
        return get_system_config(db, LAST_RUN_KEY) != now_eat.date().isoformat()
    finally:
        db.close()


def _loop(check_every_seconds: int):
    while True:
        try:
            if _due():
                run_finance_jobs()
        except Exception as e:
            logger.error(f"Finance scheduler error: {e}")
        time.sleep(check_every_seconds)


_started = False


def start_finance_scheduler(check_every_seconds: int = 1800):
    global _started
    if _started or os.getenv("FINANCE_JOBS_ENABLED", "true").lower() != "true":
        return
    _started = True
    threading.Thread(target=_loop, args=(check_every_seconds,), daemon=True, name="finance-jobs").start()
    logger.info("Finance jobs scheduler started.")
