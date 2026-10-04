import datetime
import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, String, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship

from .base import Base
from common.enums import ApprovalStatus, UserRole

class EmployeeInvite(Base):
    """
    Onboarding table for new employees invited by the Super Admin.
    """
    __tablename__ = "employee_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    permissions = Column(JSON, default=list)
    
    # Hashed token or random UUID sent via email
    token = Column(String, unique=True, nullable=False, index=True)
    
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Track who issued this invite
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)


class EmployeeAuditLog(Base):
    """
    Tracks every action taken by employees for the Super Admin Activity Feed.
    """
    __tablename__ = "employee_audit_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Which employee performed the action
    employee_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    action_type = Column(String, nullable=False, index=True) # e.g. 'CREATED_BLOG', 'DELETED_USER'
    resource_id = Column(String, nullable=True) # e.g. the ID of the blog or user affected
    
    # Additional context about what changed
    details = Column(JSON, nullable=True)
    
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    ip_address = Column(String, nullable=True)
    
    # Relationship to user
    employee = relationship("User", foreign_keys=[employee_id])


class ApprovalRequest(Base):
    """
    Maker-Checker workflow for highly sensitive operations.
    Standard employees initiate the request, Super Admin approves/rejects.
    """
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Who requested it?
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    # What are they trying to do?
    action_type = Column(String, nullable=False)
    
    # The payload needed to actually execute the action once approved
    payload = Column(JSON, nullable=False)
    
    # Justification note from the requester
    justification = Column(Text, nullable=True)
    
    status = Column(String, default=ApprovalStatus.PENDING.value, index=True)
    
    # Who resolved it?
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    requester = relationship("User", foreign_keys=[requested_by])
    resolver = relationship("User", foreign_keys=[resolved_by])
