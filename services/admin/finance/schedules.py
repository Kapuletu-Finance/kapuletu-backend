"""
Scheduled finance reports: emailed weekly (Mondays, previous Monday–Sunday) or monthly (the 1st, previous month),
with the report attached. Periods follow Nairobi calendar days.
"""
import base64
import datetime
import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from models.communication_logs import CommunicationLog
from models.finance_ops import ReportSchedule

from .common import FinanceError, as_uuid, audit, iso
from .reports import ReportService

logger = logging.getLogger(__name__)

EAT_OFFSET = datetime.timedelta(hours=3)


def last_complete_period(frequency: str, now_utc: datetime.datetime) -> Tuple[datetime.datetime, datetime.datetime]:
    """The most recent full week or month before now, as UTC bounds of Nairobi calendar days."""
    local_today = (now_utc + EAT_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0)
    if frequency == "weekly":
        end_local = local_today - datetime.timedelta(days=local_today.weekday())  # this Monday
        start_local = end_local - datetime.timedelta(days=7)
    else:
        end_local = local_today.replace(day=1)
        start_local = (end_local - datetime.timedelta(days=1)).replace(day=1)
    return start_local - EAT_OFFSET, end_local - EAT_OFFSET


class ScheduleService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _out(s: ReportSchedule) -> dict:
        return {
            "schedule_id": str(s.schedule_id), "report_type": s.report_type, "frequency": s.frequency,
            "format": s.format, "recipients": s.recipients or [], "is_active": s.is_active,
            "last_sent_at": iso(s.last_sent_at), "last_period_end": iso(s.last_period_end), "last_error": s.last_error,
            "created_at": iso(s.created_at),
        }

    def _get(self, schedule_id: str) -> ReportSchedule:
        try:
            s = self.db.get(ReportSchedule, as_uuid(schedule_id))
        except ValueError:
            s = None
        if not s:
            raise FinanceError("Schedule not found", 404)
        return s

    def list(self) -> List[dict]:
        return [self._out(s) for s in self.db.query(ReportSchedule).order_by(ReportSchedule.created_at).all()]

    def create(self, data: dict, actor_id) -> dict:
        if data["report_type"] not in ReportService.REPORTS:
            raise FinanceError(f"Unknown report '{data['report_type']}'")
        s = ReportSchedule(report_type=data["report_type"], frequency=data["frequency"], format=data["format"],
                           recipients=[str(r).lower() for r in data["recipients"]], is_active=True,
                           created_by=as_uuid(actor_id))
        self.db.add(s)
        self.db.flush()
        audit(self.db, actor_id, "REPORT_SCHEDULE_CREATED", "REPORT_SCHEDULE", s.schedule_id, self._out(s))
        self.db.commit()
        return self._out(s)

    def update(self, schedule_id: str, data: dict, actor_id) -> dict:
        s = self._get(schedule_id)
        for key in ("frequency", "format", "is_active"):
            if data.get(key) is not None:
                setattr(s, key, data[key])
        if data.get("recipients") is not None:
            s.recipients = [str(r).lower() for r in data["recipients"]]
        audit(self.db, actor_id, "REPORT_SCHEDULE_UPDATED", "REPORT_SCHEDULE", s.schedule_id, self._out(s))
        self.db.commit()
        return self._out(s)

    def delete(self, schedule_id: str, actor_id):
        s = self._get(schedule_id)
        audit(self.db, actor_id, "REPORT_SCHEDULE_DELETED", "REPORT_SCHEDULE", s.schedule_id, self._out(s))
        self.db.delete(s)
        self.db.commit()

    # --- sending ---

    def send(self, s: ReportSchedule, now: Optional[datetime.datetime] = None, actor_id=None) -> int:
        """Emails the last complete period's report to every recipient. Returns how many were queued."""
        from services.notifications.tasks import send_email_task

        now = now or datetime.datetime.utcnow()
        start, end = last_complete_period(s.frequency, now)
        reports = ReportService(self.db)
        report = reports.build(s.report_type, start, end)
        content, mime, filename = reports.render(report, s.format, prepared_by="Kapuletu finance (scheduled)",
                                                 actor_id=actor_id)
        attachment = [{"filename": filename, "content": base64.b64encode(content).decode()}]
        subject = f"Kapuletu {report.title}: {report.period_label}"
        figures = "".join(f"<li><strong>{label}:</strong> {value}</li>" for label, value in report.figures)
        body = (f"<p>Your {s.frequency} <strong>{report.title}</strong> report for {report.period_label} "
                f"is attached ({filename}).</p><ul>{figures}</ul>")

        sent = 0
        for recipient in s.recipients or []:
            log = CommunicationLog(channel="EMAIL", destination=recipient, subject=subject, status="QUEUED")
            self.db.add(log)
            self.db.commit()
            send_email_task(str(log.log_id), recipient, subject, body, attachments=attachment)
            sent += 1
        s.last_period_end, s.last_sent_at, s.last_error = end, now, None
        self.db.commit()
        return sent

    def send_now(self, schedule_id: str, actor_id) -> dict:
        s = self._get(schedule_id)
        sent = self.send(s, actor_id=actor_id)
        audit(self.db, actor_id, "REPORT_SCHEDULE_SENT", "REPORT_SCHEDULE", s.schedule_id, {"recipients": sent})
        self.db.commit()
        return {**self._out(s), "sent_to": sent}

    def send_due(self, now: Optional[datetime.datetime] = None) -> int:
        """Called by the daily finance job: sends each active schedule whose latest period hasn't gone out."""
        now = now or datetime.datetime.utcnow()
        sent = 0
        for s in self.db.query(ReportSchedule).filter(ReportSchedule.is_active.is_(True)).all():
            _, end = last_complete_period(s.frequency, now)
            if s.last_period_end is not None and s.last_period_end >= end:
                continue
            try:
                self.send(s, now)
                sent += 1
            except Exception as e:  # one broken schedule must not stop the rest
                self.db.rollback()
                s.last_error = str(e)[:500]
                self.db.commit()
                logger.error(f"Scheduled report {s.schedule_id} failed: {e}")
        return sent
