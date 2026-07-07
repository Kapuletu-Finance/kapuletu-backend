from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user
from repositories.transaction_repo import TransactionRepository

router = APIRouter(prefix="/transactions", tags=["11. Evidence Management"])

@router.get("/{pending_id}/evidence", summary="Get Transaction Evidence")
async def get_evidence(
    pending_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    repo = TransactionRepository(db)
    pending = repo.fetch_pending_transaction_by_id(pending_id, current_user.get("sub"))
    if not pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
        
    return {
        "pending_id": pending_id,
        "evidence_url": pending.evidence_url,
        "message": "Evidence retrieved successfully" if pending.evidence_url else "No evidence available for this transaction"
    }

@router.post("/{pending_id}/evidence", summary="Upload Evidence (Future)")
async def upload_evidence(
    pending_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    # Future implementation for S3 or local file upload
    repo = TransactionRepository(db)
    pending = repo.fetch_pending_transaction_by_id(pending_id, current_user.get("sub"))
    if not pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
        
    return {
        "status": "pending",
        "message": "Evidence upload functionality is planned for a future release."
    }
