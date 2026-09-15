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
        Returns core system health KPIs from SystemMetric.
        """
        from models.system_metric import SystemMetric
        # Get the most recent metric
        latest = self.db.query(SystemMetric).order_by(SystemMetric.timestamp.desc()).first()
        
        if not latest:
            return {
                "uptime_percent": 100.0,
                "avg_response_time_ms": 0,
                "cpu_load_percent": 0,
                "error_rate_percent": 0.0,
                "active_connections": 0
            }
            
        error_rate = (latest.error_count / latest.request_count * 100) if latest.request_count > 0 else 0.0

        return {
            "uptime_percent": 99.99, # Hardcoded uptime for now until we have uptime monitoring
            "avg_response_time_ms": int(latest.avg_response_time_ms),
            "cpu_load_percent": int(latest.cpu_percent),
            "error_rate_percent": round(error_rate, 2),
            "active_connections": latest.request_count # Using requests per minute as active connections proxy
        }

    def get_activity_trend(self) -> list:
        """
        Generates a 24-hour trend for active sessions and API volume by querying SystemMetric.
        """
        from models.system_metric import SystemMetric
        from sqlalchemy import cast, Integer

        now = datetime.datetime.utcnow()
        twenty_four_hours_ago = now - datetime.timedelta(hours=24)
        
        # We query the sum of requests and max active sessions per hour
        # using PostgreSQL date_trunc
        results = self.db.query(
            func.date_trunc('hour', SystemMetric.timestamp).label('hour'),
            func.sum(SystemMetric.request_count).label('api_requests'),
            func.max(SystemMetric.active_sessions_count).label('active_sessions')
        ).filter(
            SystemMetric.timestamp >= twenty_four_hours_ago
        ).group_by(
            func.date_trunc('hour', SystemMetric.timestamp)
        ).order_by('hour').all()
        
        # Build a map of results by hour string
        data_map = {}
        for row in results:
            hour_str = row.hour.strftime("%H:00")
            data_map[hour_str] = {
                "active_sessions": int(row.active_sessions or 0),
                "api_requests": int(row.api_requests or 0)
            }
            
        # Fill in the blanks to ensure exactly 24 points are returned in chronological order
        trend = []
        for i in range(24, -1, -1):
            time_point = now - datetime.timedelta(hours=i)
            hour_str = time_point.strftime("%H:00")
            if hour_str in data_map:
                trend.append({
                    "time": hour_str,
                    "active_sessions": data_map[hour_str]["active_sessions"],
                    "api_requests": data_map[hour_str]["api_requests"]
                })
            else:
                trend.append({
                    "time": hour_str,
                    "active_sessions": 0,
                    "api_requests": 0
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
            detailed_active.append({
                "user_id": str(u.user_id),
                "full_name": f"{u.first_name} {u.last_name}".strip(),
                "email": u.email,
                "role": u.role,
                "last_active_at": u.last_active_at.isoformat() if u.last_active_at else None,
                "current_action": u.current_action or "Active"
            })

        return {
            "active_now": detailed_active,
            "active_now_count": len(detailed_active),
            "recent_24h_count": recent_count,
            "total_active_24h": len(detailed_active) + recent_count
        }

    def get_system_events(self) -> list:
        """
        Returns recent system events by querying the AuditLog table.
        """
        from models.audit_log import AuditLog
        
        # Get the 10 most recent system-level audit logs
        logs = self.db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(10).all()
        
        events = []
        for log in logs:
            action_lower = log.action.lower()
            
            # Determine type
            event_type = "info"
            if any(x in action_lower for x in ["fail", "error", "crash", "exception", "reject"]):
                event_type = "error"
            elif any(x in action_lower for x in ["warn", "suspend", "block", "unusual"]):
                event_type = "warning"
                
            # Determine message
            message = log.action.replace("_", " ").title()
            if log.details and isinstance(log.details, dict) and "message" in log.details:
                message += f": {log.details['message']}"
                
            # Determine source
            source = str(log.entity_type).title()
                
            events.append({
                "id": str(log.log_id),
                "type": event_type,
                "message": message,
                "timestamp": log.created_at.isoformat() + "Z" if log.created_at else None,
                "source": source
            })
            
        return events
