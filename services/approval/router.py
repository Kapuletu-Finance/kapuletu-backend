from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user
from services.approval.schemas import (
    TransactionActionIn, TransactionEditIn, TransactionSplit, BulkActionIn,
    PendingTransactionOut, TransactionOut, PaginatedPendingResponse,
    PaginatedInboxHistoryResponse, InboxHistoryItemOut
)
from repositories.transaction_repo import TransactionRepository
from services.approval.service import ApprovalService

router = APIRouter(prefix="/transactions", tags=["8. Review & Approval Workflow"])

from fastapi import Query
import math

@router.get("/pending", response_model=PaginatedPendingResponse, summary="Get Pending Transactions (Inbox)")
async def get_pending(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    filter: Optional[str] = Query(None),
    status: str = Query("pending"),
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    repo = TransactionRepository(db)
    items, total = repo.fetch_pending_transactions_by_owner(current_user.get("sub"), skip, limit, search, filter, status)
    return {
        "items": items,
        "total_items": total,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
        "page": (skip // limit) + 1,
        "limit": limit
    }

from pydantic import BaseModel

class ClearHistoryIn(BaseModel):
    pending_ids: Optional[List[str]] = None

@router.delete("/history", summary="Clear Processed History")
async def clear_history(
    payload: ClearHistoryIn,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = ApprovalService(db)
    result = service.clear_history(current_user.get("sub"), payload.pending_ids)
    return result

@router.get("/history", response_model=PaginatedInboxHistoryResponse, summary="Get Processed Transactions History")
async def get_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    repo = TransactionRepository(db)
    results, total = repo.fetch_inbox_history(
        owner_id=current_user.get("sub"), 
        skip=skip, limit=limit, 
        status=status, search=search, 
        date_from=date_from, date_to=date_to
    )
    
    formatted_items = []
    for r in results:
        pending = r["pending"]
        item = InboxHistoryItemOut(
            pending_id=pending.pending_id,
            sender_name=pending.sender_name,
            sender_phone=pending.sender_phone,
            amount=pending.amount,
            currency=pending.currency,
            transaction_code=pending.transaction_code,
            purpose=pending.purpose,
            workflow_status=pending.workflow_status,
            processed_at=pending.processed_at,
            processed_by_name=r["processed_by_name"],
            rejection_reason=pending.rejection_reason,
            created_at=pending.created_at
        )
        formatted_items.append(item)
        
    return {
        "items": formatted_items,
        "total_items": total,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
        "page": (skip // limit) + 1,
        "limit": limit
    }

@router.get("/pending/{pending_id}", response_model=PendingTransactionOut, summary="Get Single Pending")
async def get_pending_single(
    pending_id: str,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    repo = TransactionRepository(db)
    pending = repo.fetch_pending_transaction_by_id(pending_id, current_user.get("sub"))
    if not pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
    return pending

@router.post("/bulk/approve", summary="Bulk Approval")
async def bulk_approve(
    payload: BulkActionIn, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = ApprovalService(db)
    results = service.bulk_approve(payload.pending_ids, current_user.get("sub"), payload.group_id, payload.campaign_id)
    return {"results": results}

@router.post("/bulk/reject", summary="Bulk Reject")
async def bulk_reject(
    payload: BulkActionIn, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = ApprovalService(db)
    results = service.bulk_reject(payload.pending_ids, current_user.get("sub"))
    return {"results": results}

@router.post("/{pending_id}/approve", response_model=TransactionOut, summary="Approve Transaction")
async def approve(
    pending_id: str, 
    payload: Optional[TransactionActionIn] = None, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = ApprovalService(db)
    group_id = payload.group_id if payload else None
    campaign_id = payload.campaign_id if payload else None
    try:
        txn = service.approve_transaction(pending_id, current_user.get("sub"), group_id, campaign_id)
        return {
            "transaction_id": txn.transaction_id,
            "transaction_code": txn.transaction_code,
            "status": "success",
            "message": "Transaction approved and committed to ledger."
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{pending_id}/reject", summary="Reject Transaction")
async def reject(
    pending_id: str, 
    payload: Optional[TransactionActionIn] = None, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = ApprovalService(db)
    try:
        reason = payload.internal_note if payload else None
        service.reject_transaction(pending_id, current_user.get("sub"), reason)
        return {"status": "success", "message": "Transaction rejected."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{pending_id}/undo", response_model=PendingTransactionOut, summary="Undo Action")
async def undo_action(
    pending_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = ApprovalService(db)
    try:
        pending = service.undo_action(pending_id, current_user.get("sub"))
        return pending
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{pending_id}/split", response_model=TransactionOut, summary="Split Transaction")
async def split_tx(
    pending_id: str, 
    payload: TransactionSplit, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = ApprovalService(db)
    try:
        allocs = [{"name": a.name, "amount": a.amount} for a in payload.allocations]
        txn = service.split_transaction(pending_id, current_user.get("sub"), payload.group_id, allocs, payload.campaign_id)
        return {
            "transaction_id": txn.transaction_id,
            "transaction_code": txn.transaction_code,
            "status": "success",
            "message": "Transaction split and committed to ledger."
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.patch("/{pending_id}", response_model=PendingTransactionOut, summary="Edit Transaction")
async def edit_tx(
    pending_id: str, 
    payload: TransactionEditIn, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    repo = TransactionRepository(db)
    pending = repo.fetch_pending_transaction_by_id(pending_id, current_user.get("sub"))
    if not pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
        
    if payload.extracted_amount is not None:
        pending.amount = payload.extracted_amount
    if payload.extracted_sender_name is not None:
        pending.sender_name = payload.extracted_sender_name
    if payload.extracted_code is not None:
        pending.transaction_code = payload.extracted_code
        
    db.commit()
    db.refresh(pending)
    return pending

@router.post("/{pending_id}/note", summary="Add Note")
async def add_note(
    pending_id: str, 
    payload: TransactionActionIn, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    repo = TransactionRepository(db)
    pending = repo.fetch_pending_transaction_by_id(pending_id, current_user.get("sub"))
    if not pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
        
    if payload.internal_note:
        pending.purpose = (pending.purpose + " | " + payload.internal_note) if pending.purpose else payload.internal_note
        db.commit()
        
    return {"status": "success", "message": "Note added successfully"}

@router.post("/{pending_id}/reparse", response_model=PendingTransactionOut, summary="Re-parse Message")
async def reparse(
    pending_id: str, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    from services.ingestion.parser_engine import parse_message
    repo = TransactionRepository(db)
    pending = repo.fetch_pending_transaction_by_id(pending_id, current_user.get("sub"))
    if not pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
        
    parsed_data = parse_message(pending.raw_message)
    pending.amount = parsed_data.get("amount") or pending.amount
    pending.sender_name = parsed_data.get("sender_name") or pending.sender_name
    pending.transaction_code = parsed_data.get("transaction_code") or pending.transaction_code
    pending.sender_phone = parsed_data.get("phone") or pending.sender_phone
    pending.purpose = parsed_data.get("purpose") or pending.purpose
    pending.confidence_score = parsed_data.get("confidence_score", pending.confidence_score)
    
    db.commit()
    db.refresh(pending)
    return pending

@router.post("/{pending_id}/validate", summary="Validate Transaction")
async def validate_tx(
    pending_id: str, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    repo = TransactionRepository(db)
    pending = repo.fetch_pending_transaction_by_id(pending_id, current_user.get("sub"))
    if not pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
        
    if not pending.amount or not pending.sender_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required extracted fields (amount, sender_name)")
        
    return {"status": "success", "message": "Transaction is valid and ready for approval"}


