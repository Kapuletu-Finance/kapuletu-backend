import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from models.employees import ApprovalRequest, EmployeeAuditLog
from models.users import User
from common.enums import ApprovalStatus

class ApprovalService:
    def __init__(self, db: Session):
        self.db = db

    def _record_audit_log(self, employee_id: str, action_type: str, details: dict = None, resource_id: str = None):
        log = EmployeeAuditLog(
            employee_id=employee_id,
            action_type=action_type,
            details=details or {},
            resource_id=resource_id
        )
        self.db.add(log)
        self.db.commit()

    def create_request(self, requested_by: str, action_type: str, payload: dict, justification: str = None) -> ApprovalRequest:
        new_request = ApprovalRequest(
            requested_by=requested_by,
            action_type=action_type,
            payload=payload,
            justification=justification,
            status=ApprovalStatus.PENDING.value
        )
        self.db.add(new_request)
        self.db.commit()
        self.db.refresh(new_request)
        
        self._record_audit_log(
            employee_id=requested_by, 
            action_type="CREATED_APPROVAL_REQUEST", 
            details={"action_type": action_type}, 
            resource_id=str(new_request.id)
        )
        return new_request

    def list_pending_requests(self) -> List[ApprovalRequest]:
        return self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.status == ApprovalStatus.PENDING.value)
            .order_by(ApprovalRequest.created_at.desc())
        ).scalars().all()

    def list_all_requests(self, limit: int = 50) -> List[ApprovalRequest]:
        return self.db.execute(
            select(ApprovalRequest)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(limit)
        ).scalars().all()

    def resolve_request(self, request_id: str, resolved_by: str, action: str) -> ApprovalRequest:
        req = self.db.query(ApprovalRequest).get(request_id)
        if not req:
            raise ValueError("Approval request not found.")
            
        if req.status != ApprovalStatus.PENDING.value:
            raise ValueError("Request is already resolved.")
            
        if str(req.requested_by) == str(resolved_by):
            raise ValueError("You cannot approve your own request.")

        if action == "approve":
            req.status = ApprovalStatus.APPROVED.value
            # Note: The actual execution of the payload should be handled by the caller or a dispatcher here.
            # We will assume caller handles execution upon return of APPROVED status.
        elif action == "reject":
            req.status = ApprovalStatus.REJECTED.value
        else:
            raise ValueError("Invalid action. Must be 'approve' or 'reject'.")

        req.resolved_by = resolved_by
        req.resolved_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(req)
        
        self._record_audit_log(
            employee_id=resolved_by, 
            action_type=f"RESOLVED_APPROVAL_REQUEST_{action.upper()}", 
            details={"action_type": req.action_type}, 
            resource_id=str(req.id)
        )
        
        return req
