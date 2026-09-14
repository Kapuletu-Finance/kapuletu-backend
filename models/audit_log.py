import datetime
import uuid
from sqlalchemy import UUID, Column, DateTime, Integer, String, JSON
from .base import Base

class AuditLog(Base):
    """
    AuditLog Model: Tracks all administrative and critical system actions.
    Provides an immutable-style trail for forensic investigation.
    """
    __tablename__ = "audit_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Who performed the action (User ID)
    actor_id = Column(UUID(as_uuid=True), nullable=True) 
    
    # What was done (e.g. 'USER_SUSPENDED', 'PLAN_CREATED')
    action = Column(String, nullable=False)
    
    # Target context
    entity_type = Column(String, nullable=False) # USER, GROUP, PLAN, etc.
    entity_id = Column(String) # The ID of the affected resource
    
    # Forensic Payload: Deep diff or metadata about the change
    details = Column(JSON) 
    
    # Network context (Optional but useful for forensics)
    ip_address = Column(String)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
