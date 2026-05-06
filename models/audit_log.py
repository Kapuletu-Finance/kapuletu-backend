from sqlalchemy import Column, String, Integer

from .base import Base

class AuditLog(Base):
    """
    AuditLog Model: Tracks all administrative actions within the system.
    
    This is used for platform security and transparency, recording 
    who did what and when (e.g., 'Subscription Created', 'User Suspended').
    """
    __tablename__ = "audit_logs"

    # Auto-incrementing primary key
    log_id = Column(Integer, primary_key=True)
    # The action performed
    action = Column(String)
    # The category of the entity affected (e.g. 'USER', 'PLAN', 'GROUP')
    entity_type = Column(String)
