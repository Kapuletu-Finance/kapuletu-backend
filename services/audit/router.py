from fastapi import APIRouter, Depends, HTTPException, Query, Request
from common.utils import parse_uuid
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List

from common.database import get_db
from common.auth_dependencies import get_verified_user
from models.audit_log import AuditLog
from services.audit.schemas import AuditLogOut

router = APIRouter(prefix="/audit", tags=["12. Audit Logs"])

@router.get("/logs", response_model=List[AuditLogOut], summary="Get Audit Logs")
def get_logs(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user_data: dict = Depends(get_verified_user)
):
    """
    Fetches the recent activity timeline for the currently logged-in treasurer.
    """
    user_id = user_data["user_id"]
    
    logs = db.execute(
        select(AuditLog)
        .where(AuditLog.actor_id == parse_uuid(user_id))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).scalars().all()
    
    return logs

@router.get("/logs/{entity_type}/{entity_id}", response_model=List[AuditLogOut], summary="Get Logs by Entity")
def get_logs_by_entity(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    user_data: dict = Depends(get_verified_user)
):
    """
    Fetches the forensic history for a specific entity (e.g. TRANSACTION 1234).
    Ensures the acting user is the one who generated the logs (Tenant Isolation).
    """
    user_id = user_data["user_id"]
    
    logs = db.execute(
        select(AuditLog)
        .where(
            AuditLog.actor_id == parse_uuid(user_id),
            AuditLog.entity_type == entity_type.upper(),
            AuditLog.entity_id == entity_id
        )
        .order_by(AuditLog.created_at.desc())
    ).scalars().all()
    
    return logs
