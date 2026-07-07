from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models.audit_log import AuditLog
import logging

logger = logging.getLogger(__name__)

class AuditService:
    """
    Core utility for tracking administrative and security actions in KapuLetu.
    """
    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Creates an immutable forensic record.
        
        Args:
            actor_id (str): The User ID performing the action.
            action (str): Standardized action name (e.g. 'TXN_APPROVED', 'PASSWORD_CHANGED').
            entity_type (str): Type of resource affected (e.g. 'TRANSACTION', 'USER').
            entity_id (str): Unique ID of the affected resource.
            details (dict): Optional JSON payload for deep forensic diffs.
            ip_address (str): Optional network context.
        """
        try:
            log_entry = AuditLog(
                actor_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details or {},
                ip_address=ip_address
            )
            self.db.add(log_entry)
            self.db.commit()
            self.db.refresh(log_entry)
            
            logger.info(f"Audit Log [{action}] for {entity_type} {entity_id} by {actor_id}")
            return log_entry
        except Exception as e:
            # Audit logging should ideally never crash the main transaction
            self.db.rollback()
            logger.error(f"Failed to record audit log {action} for {actor_id}: {e}")
            # We don't re-raise here to prevent blocking user workflows, but in a bank it might be required.
            return None
