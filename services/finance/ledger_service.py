import json
import hashlib
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from models.transaction import Transaction
from models.campaign import Campaign
from services.finance.schemas import LedgerEntryOut, CampaignLedgerSummaryOut, LedgerResponse, IntegrityCheckOut

logger = logging.getLogger(__name__)

class LedgerService:
    """
    LedgerService: Manages retrieval and cryptographic verification of finalized financial records.
    """
    def __init__(self, db: Session):
        self.db = db

    def _recalculate_hash(self, txn: Transaction) -> str:
        """
        Recalculates the SHA-256 integrity seal for a given transaction.
        Must perfectly match the generation logic in ApprovalService.
        """
        txn_payload = {
            "transaction_id": str(txn.transaction_id),
            "owner_id": str(txn.owner_id),
            "group_id": str(txn.group_id),
            "campaign_id": str(txn.campaign_id) if txn.campaign_id else None,
            "transaction_code": txn.transaction_code,
            "amount": float(txn.amount),
            "sender_phone": txn.sender_phone,
            "status": txn.status,
            "created_at": txn.created_at.isoformat()
        }
        serialized = json.dumps(txn_payload, sort_keys=True).encode()
        return hashlib.sha256(serialized).hexdigest()

    def verify_integrity(self, transaction_id: str, owner_id: str) -> IntegrityCheckOut:
        """
        Performs a deep cryptographic audit of a single transaction.
        """
        txn = self.db.execute(
            select(Transaction).where(
                Transaction.transaction_id == transaction_id,
                Transaction.owner_id == owner_id
            )
        ).scalars().first()
        
        if not txn:
            raise ValueError("Transaction not found or access denied")
            
        recalculated = self._recalculate_hash(txn)
        is_valid = (recalculated == txn.ledger_hash)
        
        return IntegrityCheckOut(
            transaction_id=str(txn.transaction_id),
            is_valid=is_valid,
            original_hash=txn.ledger_hash,
            recalculated_hash=recalculated,
            message="Valid immutable record" if is_valid else "TAMPERING DETECTED: Cryptographic seal broken."
        )

    def get_campaign_ledger(self, campaign_id: str, owner_id: str) -> LedgerResponse:
        """
        Fetches the immutable ledger for a specific campaign, performing
        on-the-fly integrity verification.
        """
        # 1. Fetch Campaign Details
        campaign = self.db.execute(
            select(Campaign).where(Campaign.campaign_id == campaign_id)
        ).scalars().first()
        
        # 2. Fetch all approved transactions for this campaign
        stmt = select(Transaction).where(
            Transaction.owner_id == owner_id,
            Transaction.campaign_id == campaign_id,
            Transaction.status == "approved"
        ).order_by(Transaction.created_at.desc())
        
        txns = self.db.execute(stmt).scalars().all()
        
        # 3. Process Entries and Verify Integrity
        entries = []
        total_raised = 0.0
        
        for txn in txns:
            # On-the-fly verification
            recalculated = self._recalculate_hash(txn)
            is_tampered = (recalculated != txn.ledger_hash)
            
            # If not tampered, add to trusted total
            if not is_tampered:
                total_raised += float(txn.amount)
                
            entries.append(
                LedgerEntryOut(
                    transaction_id=str(txn.transaction_id),
                    owner_id=str(txn.owner_id),
                    group_id=str(txn.group_id),
                    campaign_id=str(txn.campaign_id) if txn.campaign_id else None,
                    transaction_code=txn.transaction_code,
                    amount=float(txn.amount),
                    sender_phone=txn.sender_phone,
                    sender_name=txn.sender_name,
                    status=txn.status,
                    created_at=txn.created_at,
                    ledger_hash=txn.ledger_hash,
                    is_tampered=is_tampered
                )
            )
            
        # 4. Calculate Summary
        summary = None
        if campaign:
            target = float(campaign.target_amount or 0.0)
            progress = (total_raised / target * 100) if target > 0 else 0.0
            summary = CampaignLedgerSummaryOut(
                campaign_id=str(campaign.campaign_id),
                title=campaign.title,
                target_amount=target,
                total_raised=total_raised,
                transaction_count=len(entries),
                progress_percentage=round(progress, 2)
            )
            
        return LedgerResponse(summary=summary, entries=entries)

    def get_global_ledger(self, owner_id: str) -> LedgerResponse:
        """
        Fetches the complete ledger for the owner.
        """
        stmt = select(Transaction).where(
            Transaction.owner_id == owner_id,
            Transaction.status == "approved"
        ).order_by(Transaction.created_at.desc())
        
        txns = self.db.execute(stmt).scalars().all()
        
        entries = []
        for txn in txns:
            recalculated = self._recalculate_hash(txn)
            is_tampered = (recalculated != txn.ledger_hash)
            
            entries.append(
                LedgerEntryOut(
                    transaction_id=str(txn.transaction_id),
                    owner_id=str(txn.owner_id),
                    group_id=str(txn.group_id),
                    campaign_id=str(txn.campaign_id) if txn.campaign_id else None,
                    transaction_code=txn.transaction_code,
                    amount=float(txn.amount),
                    sender_phone=txn.sender_phone,
                    sender_name=txn.sender_name,
                    status=txn.status,
                    created_at=txn.created_at,
                    ledger_hash=txn.ledger_hash,
                    is_tampered=is_tampered
                )
            )
            
        return LedgerResponse(summary=None, entries=entries)
