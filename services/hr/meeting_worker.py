"""
Meeting worker — run every 5–10 minutes from cron (see docs/hr/attendance_and_meetings.md):

    python -m services.hr.meeting_worker

1. Sends 24-hour and 1-hour meeting reminders (in-app + email), at most once per attendee per window.
2. After a meeting ends, records every attendee without a mark as 'missed' (once per meeting).
"""
import logging
import os
import sys

# Ensure the backend root is importable when run as a plain script
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.database import SessionLocal
from services.hr.meeting_service import finalize_ended_meetings, send_due_reminders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run() -> None:
    db = SessionLocal()
    try:
        jobs = send_due_reminders(db)
        finalized = finalize_ended_meetings(db)
    finally:
        db.close()

    # Reminder emails were queued in the outbox; the API's dispatcher sends them
    logger.info(f"Meeting worker: {len(jobs)} reminder email(s) queued, {finalized} meeting(s) finalized.")


if __name__ == "__main__":
    run()
