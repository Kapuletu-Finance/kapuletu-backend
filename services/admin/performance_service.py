import datetime
import random
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.users import User

class PerformanceService:
    """
    Dedicated service for tracking and aggregating platform activity
    and simulated/mocked system performance metrics.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_system_health(self) -> dict:
        """
        Returns core system health KPIs.
        In a real prod app, these would come from APM / Datadog / psutil.
        """
        return {
            "uptime_percent": 99.98,
            "avg_response_time_ms": random.randint(120, 250),
            "cpu_load_percent": random.randint(35, 75),
            "error_rate_percent": round(random.uniform(0.1, 0.9), 2),
            "active_connections": random.randint(150, 450)
        }

    def get_activity_trend(self) -> list:
        """
        Generates a 24-hour trend for active sessions and API volume.
        """
        trend = []
        now = datetime.datetime.utcnow()
        for i in range(24, -1, -1):
            time_point = now - datetime.timedelta(hours=i)
            trend.append({
                "time": time_point.strftime("%H:00"),
                "active_sessions": random.randint(20, 200),
                "api_requests": random.randint(1000, 5000)
            })
        return trend

    def get_extended_active_users(self) -> dict:
        """
        Returns active users with more detailed properties for the new UI.
        """
        # Active in last 15 mins
        now = datetime.datetime.utcnow()
        active_threshold = now - datetime.timedelta(minutes=15)
        recent_threshold = now - datetime.timedelta(hours=24)

        active_users = self.db.query(User).filter(
            User.last_active_at >= active_threshold
        ).order_by(User.last_active_at.desc()).all()

        # Just get the recent count
        recent_count = self.db.query(func.count(User.user_id)).filter(
            User.last_active_at >= recent_threshold,
            User.last_active_at < active_threshold
        ).scalar() or 0

        # Enhance the response for the UI
        detailed_active = []
        for u in active_users:
            actions = ["Viewing Dashboard", "Processing Payment", "Reviewing Campaign", "Exporting Data"]
            detailed_active.append({
                "user_id": str(u.user_id),
                "full_name": f"{u.first_name} {u.last_name}".strip(),
                "email": u.email,
                "role": u.role,
                "last_active_at": u.last_active_at.isoformat() if u.last_active_at else None,
                "current_action": random.choice(actions) # Simulated detailed state
            })

        return {
            "active_now": detailed_active,
            "active_now_count": len(detailed_active),
            "recent_24h_count": recent_count,
            "total_active_24h": len(detailed_active) + recent_count
        }

    def get_system_events(self) -> list:
        """
        Returns a list of simulated critical system events for the data table.
        Could be hooked up to `AuditService` in the future.
        """
        now = datetime.datetime.utcnow()
        events = [
            {"id": "ev_1", "type": "error", "message": "High latency detected on Payment Gateway API", "timestamp": (now - datetime.timedelta(minutes=5)).isoformat(), "source": "Finance Module"},
            {"id": "ev_2", "type": "info", "message": "Database automated backup completed successfully", "timestamp": (now - datetime.timedelta(minutes=45)).isoformat(), "source": "System"},
            {"id": "ev_3", "type": "warning", "message": "Unusual spike in login failures", "timestamp": (now - datetime.timedelta(hours=2)).isoformat(), "source": "Auth Service"},
            {"id": "ev_4", "type": "info", "message": "AI Model Retraining Triggered", "timestamp": (now - datetime.timedelta(hours=4)).isoformat(), "source": "AI Governance"},
            {"id": "ev_5", "type": "error", "message": "SMTP Connection Timeout", "timestamp": (now - datetime.timedelta(hours=12)).isoformat(), "source": "CRM Service"},
        ]
        return events
