from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.enums import ApprovalStatus
from common.utils import parse_uuid
from models.employees import ApprovalRequest, EmployeeAuditLog


class ApprovalService:
    """
    Maker-checker queue for sensitive actions. Pass commit=False to make a request or decision part of the
    caller's transaction (e.g. a refund and its approval request are saved together or not at all).
    """
    def __init__(self, db: Session):
        self.db = db

    def _record_audit_log(self, employee_id, action_type: str, details: dict = None, resource_id: str = None,
                          commit: bool = True):
        self.db.add(EmployeeAuditLog(
            employee_id=parse_uuid(employee_id),
            action_type=action_type,
            details=details or {},
            resource_id=resource_id
        ))
        if commit:
            self.db.commit()

    def create_request(self, requested_by, action_type: str, payload: dict, justification: str = None,
                       commit: bool = True) -> ApprovalRequest:
        new_request = ApprovalRequest(
            requested_by=parse_uuid(requested_by),
            action_type=action_type,
            payload=payload,
            justification=justification,
            status=ApprovalStatus.PENDING.value
        )
        self.db.add(new_request)
        self.db.flush()
        self._record_audit_log(
            employee_id=requested_by,
            action_type="CREATED_APPROVAL_REQUEST",
            details={"action_type": action_type},
            resource_id=str(new_request.id),
            commit=False,
        )
        if commit:
            self.db.commit()
            self.db.refresh(new_request)
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

    def get_request(self, request_id) -> Optional[ApprovalRequest]:
        try:
            return self.db.get(ApprovalRequest, parse_uuid(request_id))
        except ValueError:
            return None

    def resolve_request(self, request_id, resolved_by, action: str, commit: bool = True) -> ApprovalRequest:
        req = self.get_request(request_id)
        if not req:
            raise ValueError("Approval request not found.")

        if req.status != ApprovalStatus.PENDING.value:
            raise ValueError("Request is already resolved.")

        if str(req.requested_by) == str(resolved_by):
            raise ValueError("You cannot approve your own request.")

        if action == "approve":
            req.status = ApprovalStatus.APPROVED.value
        elif action == "reject":
            req.status = ApprovalStatus.REJECTED.value
        else:
            raise ValueError("Invalid action. Must be 'approve' or 'reject'.")

        req.resolved_by = parse_uuid(resolved_by)
        req.resolved_at = datetime.utcnow()
        self._record_audit_log(
            employee_id=resolved_by,
            action_type=f"RESOLVED_APPROVAL_REQUEST_{action.upper()}",
            details={"action_type": req.action_type},
            resource_id=str(req.id),
            commit=False,
        )
        if commit:
            self.db.commit()
            self.db.refresh(req)
        return req
