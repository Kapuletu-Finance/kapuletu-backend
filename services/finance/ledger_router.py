from typing import List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from common.database import get_db
from common.auth_dependencies import get_verified_user
from models.transaction import Transaction

router = APIRouter(prefix="/ledger", tags=["8. Ledger (Immutable)"])

@router.get("", summary="Get Ledger Entries")
async def list_ledger(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    stmt = select(Transaction).where(Transaction.owner_id == current_user.get("sub")).order_by(Transaction.created_at.desc())
    txns = db.execute(stmt).scalars().all()
    return txns

@router.get("/campaign/{campaign_id}", summary="Get Ledger by Campaign")
async def ledger_by_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    stmt = select(Transaction).where(
        Transaction.owner_id == current_user.get("sub"),
        Transaction.campaign_id == campaign_id
    ).order_by(Transaction.created_at.desc())
    txns = db.execute(stmt).scalars().all()
    return txns

@router.get("/{ledger_id}", summary="Get Ledger Entry")
async def get_ledger_entry(
    ledger_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    stmt = select(Transaction).where(
        Transaction.transaction_id == ledger_id,
        Transaction.owner_id == current_user.get("sub")
    )
    txn = db.execute(stmt).scalars().first()
    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ledger entry not found")
    return txn
