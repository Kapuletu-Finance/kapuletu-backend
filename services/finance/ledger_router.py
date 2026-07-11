from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user
from services.finance.ledger_service import LedgerService
from services.finance.schemas import LedgerResponse, IntegrityCheckOut

router = APIRouter(prefix="/ledger", tags=["9. Ledger (Immutable)"])

@router.get("", response_model=LedgerResponse, summary="Get Global Ledger")
async def get_global_ledger(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Returns the complete, immutable ledger of all approved transactions.
    """
    service = LedgerService(db)
    return service.get_global_ledger(owner_id=current_user.get("sub"))

@router.get("/campaign/{campaign_id}", response_model=LedgerResponse, summary="Get Ledger by Campaign")
async def get_campaign_ledger(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Returns the immutable ledger for a specific campaign, including aggregates.
    """
    service = LedgerService(db)
    return service.get_campaign_ledger(campaign_id=campaign_id, owner_id=current_user.get("sub"))

@router.get("/verify/{transaction_id}", response_model=IntegrityCheckOut, summary="Cryptographic Audit")
async def verify_transaction_integrity(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """
    Performs a deep cryptographic audit on a single transaction to ensure its data 
    has not been tampered with since approval.
    """
    service = LedgerService(db)
    try:
        return service.verify_integrity(transaction_id=transaction_id, owner_id=current_user.get("sub"))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
