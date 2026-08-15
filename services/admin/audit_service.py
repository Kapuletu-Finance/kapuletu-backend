from common.utils import parse_uuid
from sqlalchemy.orm import Session
from models.audit_log import AuditLog
from sqlalchemy import or_

class AuditService:
    """
    AuditService: Provides a forensic window into all system-altering actions.
    """
    def __init__(self, db: Session):
        self.db = db

    def search_logs(self, filters: dict):
        """
        Advanced search for forensic logs.
        Supports filtering by actor, entity type, action, and time.
        """
        query = self.db.query(AuditLog)
        
        if filters.get("actor_id"):
            query = query.filter(AuditLog.actor_id == parse_uuid(filters["actor_id"]))
            
        if filters.get("entity_type"):
            query = query.filter(AuditLog.entity_type == filters["entity_type"])
            
        if filters.get("action"):
            query = query.filter(AuditLog.action == filters["action"])
            
        if filters.get("query"):
            # Text search in details or action
            search_text = f"%{filters['query']}%"
            query = query.filter(or_(
                AuditLog.action.ilike(search_text),
                AuditLog.entity_id.ilike(search_text)
            ))

        # Pagination
        limit = int(filters.get("limit", 50))
        page = int(filters.get("page", 1))
        
        total = query.count()
        logs = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        
        return {
            "total": total,
            "page": page,
            "logs": [{
                "log_id": str(l.log_id),
                "actor_id": str(l.actor_id) if l.actor_id else None,
                "action": l.action,
                "entity_type": l.entity_type,
                "entity_id": l.entity_id,
                "details": l.details,
                "timestamp": l.created_at.isoformat()
            } for l in logs]
        }

    @staticmethod
    def log_action(db: Session, actor_id, action, entity_type, entity_id=None, details=None):
        """
        Utility to inject a forensic log entry.
        """
        log = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            details=details
        )
        db.add(log)
        db.commit()
