from common.utils import parse_uuid
from sqlalchemy.orm import Session

from common.logger import get_logger
import hashlib
import json
from models.pending_transaction import PendingTransaction
from models.transaction import Transaction
from models.users import User
from models.group import Group
from models.campaign import Campaign
from services.ingestion.active_learner import log_for_active_learning
from services.audit.service import AuditService
from services.notifications.service import create_notification
from sqlalchemy import func

logger = get_logger(__name__)

class ApprovalService:
    """
    ApprovalService: Manages the transition of financial records from 'Pending' 
    to 'Immutable Ledger' state.
    
    This service ensures that once a treasurer approves a transaction, it is 
    permanently recorded in the relational database with a cryptographic integrity 
    seal (SHA-256) to prevent tampering.
    """
    def __init__(self, db: Session):
        """Initializes service with SQL session."""
        self.db = db

    def approve_transaction(self, pending_txn_id, treasurer_id, group_id, campaign_id=None):
        """
        Finalizes a pending transaction.
        
        High-Level Workflow:
        1. Retrieval: Finds the pending record in the database.
        2. Finalization: Creates a permanent Transaction record.
        3. Audit Commitment: Writes the transaction to the immutable QLDB ledger.
        4. State Update: Marks the pending record as 'processed' to clear the inbox.
        
        Args:
            pending_txn_id (UUID): The ID of the record being approved.
            treasurer_id (UUID): The ID of the authorizing treasurer.
            group_id (UUID): The target group for the funds.
            campaign_id (UUID, optional): Specific campaign mapping.
            
        Returns:
            Transaction: The newly created permanent transaction record.
        """
        # 1. Fetch the original pending record with an exclusive DB lock to prevent double-approvals
        try:
            pending = self.db.query(PendingTransaction).filter(PendingTransaction.pending_id == parse_uuid(pending_txn_id)).with_for_update(nowait=True).first()
        except Exception as e:
            logger.error(f"Approval Failed: Database lock could not be acquired for Pending ID {pending_txn_id}. {e}")
            raise Exception("Transaction is currently being processed by another request. Please try again.")
            
        if not pending:
            logger.error(f"Approval Failed: Pending ID {pending_txn_id} not found.")
            raise Exception("Pending transaction not found")
            
        # Security: Verify group ownership (IDOR prevention)
        from models.group import Group
        group = self.db.query(Group).filter(Group.group_id == parse_uuid(group_id), Group.owner_id ==parse_uuid(parse_uuid(treasurer_id))).first()
        if not group:
            logger.error(f"Approval Failed: Treasurer {treasurer_id} attempted to approve transaction into unauthorized Group {group_id}")
            raise Exception("Forbidden: You do not have permission to approve transactions for this group.")

        # 2. Transition to Permanent Transaction record
        # This moves the data from the 'scratchpad' (Pending) to the 'General Ledger' (Transaction).
        new_txn = Transaction(
            owner_id=parse_uuid(treasurer_id),
            group_id=parse_uuid(group_id),
            campaign_id=parse_uuid(campaign_id) if campaign_id else None,
            transaction_code=pending.transaction_code,
            amount=pending.amount,
            sender_phone=pending.sender_phone,
            sender_name=pending.sender_name,
            payment_method=pending.payment_method,
            source_evidence=pending.source_evidence,
            status="approved"
        )
        try:
            self.db.add(new_txn)
            self.db.flush() # Flushes to DB to generate the transaction_id for the ledger record
        except Exception as e:
            # If UNIQUE constraint fails, the transaction was already approved previously
            # (e.g. UUID bug caused is_processed to not be set). Just find the existing one and continue.
            from sqlalchemy.exc import IntegrityError
            if isinstance(e, IntegrityError) and "UNIQUE constraint failed" in str(e):
                self.db.rollback()
                new_txn = self.db.query(Transaction).filter(
                    Transaction.transaction_code == pending.transaction_code,
                    Transaction.owner_id == parse_uuid(treasurer_id)
                ).first()
                if not new_txn:
                    raise Exception("Transaction already exists but could not be located.")
                logger.warning(f"Approval: Transaction {pending.transaction_code} already existed, marking pending as processed.")
            else:
                self.db.rollback()
                raise

        # 2.5 Active Learning Hook
        # Feed the ground truth (after potential treasurer edits) back into the AI loop
        finalized_data = {
            "amount": float(new_txn.amount) if new_txn.amount else None,
            "sender_name": pending.sender_name,
            "transaction_code": new_txn.transaction_code,
        }
        
        # Admin Feedback Loop: Record the correction if the ground truth differs from the AI's first guess.
        # CRITICAL: Only log if the user has opted-in to AI training (Privacy Guard)
        user = self.db.query(User).filter(User.user_id ==parse_uuid(parse_uuid(treasurer_id))).first()
        if user and user.allow_ai_training and pending.original_ai_output:
            from services.admin.ai_governance_service import AIGovernanceService
            ai_service = AIGovernanceService(self.db)
            ai_service.log_treasurer_correction(
                pending_txn_id, 
                treasurer_id, 
                pending.original_ai_output, 
                finalized_data
            )

        try:
            log_for_active_learning(self.db, pending.raw_message, finalized_data)
        except Exception as e:
            logger.error(f"Active Learning Hook Failed: {e}")

        # 3. Create Integrity Seal (The verifiable truth)
        # We calculate a SHA-256 hash of the transaction data to ensure auditability.
        try:
            self._write_to_ledger(new_txn)
        except Exception as e:
            logger.error(f"Ledger Integrity Error: Failed to generate seal: {e}")
            self.db.rollback()
            raise Exception("Integrity sealing failed. Transaction has been rolled back for safety.")

        # 4. Mark pending as processed
        # This ensures the item no longer appears in the treasurer's approval inbox.
        from datetime import datetime
        pending.is_processed = True
        pending.workflow_status = "approved"
        pending.processed_at = datetime.utcnow()
        pending.processed_by = parse_uuid(treasurer_id)
        
        self.db.commit()
        
        target_name = "Unknown"
        if campaign_id:
            camp = self.db.query(Campaign).filter(Campaign.campaign_id == parse_uuid(campaign_id)).first()
            if camp:
                target_name = camp.title
        else:
            grp = self.db.query(Group).filter(Group.group_id == parse_uuid(group_id)).first()
            if grp:
                target_name = grp.group_name

        AuditService(self.db).log_action(
            actor_id=treasurer_id,
            action="TXN_APPROVED",
            entity_type="TRANSACTION",
            entity_id=str(new_txn.transaction_id),
            details={
                "amount": float(new_txn.amount),
                "message": f"Ksh. {float(new_txn.amount)} for {target_name} approved",
                "campaign_id": str(campaign_id) if campaign_id else None
            }
        )
        
        logger.info(f"Transaction {new_txn.transaction_id} successfully finalized and ledger-locked.")
        
        # --- Notification Hooks ---
        sender_display = new_txn.sender_name or "Anonymous"
        
        # 1. Notify about the new contribution
        create_notification(
            db=self.db,
            user_id=str(treasurer_id),
            title="New contribution received",
            message=f"Ksh. {float(new_txn.amount)} has been received from {sender_display} for {target_name}.",
            type="transaction_approved",
            related_entity_id=str(new_txn.transaction_id)
        )
        
        # 2. Check Campaign Goal
        if campaign_id and camp:
            # Calculate total raised for this campaign so far
            total_raised = self.db.query(func.sum(Transaction.amount)).filter(
                Transaction.campaign_id == parse_uuid(str(campaign_id)),
                Transaction.status == "approved"
            ).scalar() or 0.0
            
            # If we crossed the threshold exactly with this transaction
            # (To avoid spamming, we could check if total_raised - new_txn.amount < camp.target_amount)
            if float(total_raised) >= float(camp.target_amount) and float(total_raised) - float(new_txn.amount) < float(camp.target_amount):
                create_notification(
                    db=self.db,
                    user_id=str(treasurer_id),
                    title="Campaign goal achieved.",
                    message=f"You've reached your target amount for campaign {camp.title}.",
                    type="campaign_goal_reached",
                    related_entity_id=str(campaign_id)
                )

        return new_txn

    def split_transaction(self, pending_txn_id, treasurer_id, group_id, allocations, campaign_id=None):
        """
        Splits a single pending transaction into multiple member allocations.
        """
        from models.review_allocation import ReviewAllocation
        import uuid

        # 1. Fetch record
        try:
            pending = self.db.query(PendingTransaction).filter(
                PendingTransaction.pending_id == parse_uuid(pending_txn_id)
            ).with_for_update(nowait=True).first()
        except Exception:
            raise Exception("Transaction is currently being processed by another request. Please try again.")

        if not pending:
            raise Exception("Pending transaction not found")

        # 2. Math Validation: Ensure total matches
        total_split = sum(float(a["amount"]) for a in allocations)
        if abs(total_split - float(pending.amount)) > 0.01:
            raise Exception(f"Math Error: Total split ({total_split}) does not match payment amount ({pending.amount})")

        # 3. Create Parent Transaction
        new_txn = Transaction(
            owner_id=parse_uuid(treasurer_id),
            group_id=parse_uuid(group_id),
            campaign_id=parse_uuid(campaign_id) if campaign_id else None,
            transaction_code=pending.transaction_code,
            amount=pending.amount,
            sender_phone=pending.sender_phone,
            sender_name=", ".join(a["name"] for a in allocations),
            payment_method=pending.payment_method,
            source_evidence=pending.source_evidence,
            status="approved"
        )
        self.db.add(new_txn)
        self.db.flush()

        # 4. Create Individual Allocations
        for alloc in allocations:
            item = ReviewAllocation(
                allocation_id=uuid.uuid4(),
                transaction_id=new_txn.transaction_id,
                pending_id=pending.pending_id,
                member_name=alloc["name"],
                allocated_amount=alloc["amount"]
            )
            self.db.add(item)

        # 5. Ledger Commitment
        self._write_to_ledger(new_txn)

        # 6. Mark Processed
        from datetime import datetime
        pending.is_processed = True
        pending.workflow_status = "split_approved"
        pending.processed_at = datetime.utcnow()
        pending.processed_by = parse_uuid(treasurer_id)
        
        self.db.commit()

        target_name = "Unknown"
        if campaign_id:
            camp = self.db.query(Campaign).filter(Campaign.campaign_id == parse_uuid(campaign_id)).first()
            if camp:
                target_name = camp.title
        else:
            grp = self.db.query(Group).filter(Group.group_id == parse_uuid(group_id)).first()
            if grp:
                target_name = grp.group_name

        AuditService(self.db).log_action(
            actor_id=treasurer_id,
            action="TXN_SPLIT_APPROVED",
            entity_type="TRANSACTION",
            entity_id=str(new_txn.transaction_id),
            details={
                "splits": len(allocations),
                "message": f"Ksh. {float(new_txn.amount)} split across {len(allocations)} members for {target_name}",
                "campaign_id": str(campaign_id) if campaign_id else None
            }
        )

        return new_txn



    def reject_transaction(self, pending_txn_id, treasurer_id, reason=None):
        """
        Marks a pending transaction as rejected.
        
        Args:
            pending_txn_id (UUID): The record to reject.
            treasurer_id (UUID): The treasurer rejecting the record.
            reason (str, optional): Why it was rejected.
        """
        try:
            pending = self.db.query(PendingTransaction).filter(
                PendingTransaction.pending_id == parse_uuid(pending_txn_id),
                PendingTransaction.owner_id ==parse_uuid(parse_uuid(treasurer_id))
            ).with_for_update(nowait=True).first()
        except Exception:
            raise Exception("Transaction is currently being processed by another request.")
        
        if not pending:
            raise Exception("Pending transaction not found or access denied")

        from datetime import datetime
        pending.is_processed = True
        pending.workflow_status = "rejected"
        pending.processed_at = datetime.utcnow()
        pending.processed_by = parse_uuid(treasurer_id)
        pending.rejection_reason = reason
        
        self.db.commit()
        
        AuditService(self.db).log_action(
            actor_id=treasurer_id,
            action="TXN_REJECTED",
            entity_type="PENDING_TRANSACTION",
            entity_id=str(pending_txn_id),
            details={
                "message": "Transaction rejected",
                "campaign_id": str(pending.campaign_id) if hasattr(pending, 'campaign_id') and pending.campaign_id else None
            }
        )
        
        logger.info(f"Transaction {pending_txn_id} rejected by treasurer {treasurer_id}.")
        return {"status": "rejected"}

    def undo_rejection(self, pending_txn_id, treasurer_id):
        """
        Reverts a rejected transaction back to the pending state.
        
        Args:
            pending_txn_id (UUID): The record to undo.
            treasurer_id (UUID): The treasurer undoing the action.
        """
        try:
            pending = self.db.query(PendingTransaction).filter(
                PendingTransaction.pending_id == parse_uuid(pending_txn_id),
                PendingTransaction.owner_id == parse_uuid(treasurer_id)
            ).with_for_update(nowait=True).first()
        except Exception:
            raise Exception("Transaction is currently being processed by another request.")
            
        if not pending:
            raise Exception("Pending transaction not found or access denied")
            
        if pending.workflow_status != "rejected" or not pending.is_processed:
            raise Exception("Only rejected transactions can be undone.")
            
        pending.is_processed = False
        pending.workflow_status = "pending"
        pending.processed_at = None
        pending.processed_by = None
        pending.rejection_reason = None
        
        self.db.commit()
        
        AuditService(self.db).log_action(
            actor_id=treasurer_id,
            action="TXN_UNDO_REJECT",
            entity_type="PENDING_TRANSACTION",
            entity_id=str(pending_txn_id),
            details={
                "message": "Transaction rejection was undone"
            }
        )
        
        logger.info(f"Rejection of transaction {pending_txn_id} was undone by treasurer {treasurer_id}.")
        return pending

    def bulk_approve(self, pending_ids: list, treasurer_id, group_id, campaign_id=None):
        """Processes multiple approvals in a single batch."""
        results = []
        for pid in pending_ids:
            try:
                txn = self.approve_transaction(pid, treasurer_id, group_id, campaign_id)
                results.append({"pending_id": str(pid), "status": "success", "transaction_id": str(txn.transaction_id)})
            except Exception as e:
                results.append({"pending_id": str(pid), "status": "error", "message": str(e)})
        return results

    def bulk_reject(self, pending_ids: list, treasurer_id):
        """Processes multiple rejections in a single batch."""
        results = []
        for pid in pending_ids:
            try:
                self.reject_transaction(pid, treasurer_id)
                results.append({"pending_id": str(pid), "status": "success"})
            except Exception as e:
                results.append({"pending_id": str(pid), "status": "error", "message": str(e)})
        return results

    def _write_to_ledger(self, txn: Transaction):
        """
        Internal helper to generate a cryptographic seal for the transaction.
        Even without QLDB, we maintain a verifiable hash in RDS to detect tampering.
        """
        # 1. Prepare data for hashing
        # We use a deterministic JSON serialization (sorted keys)
        txn_payload = {
            "transaction_id": str(txn.transaction_id),
            "owner_id": str(txn.owner_id),
            "group_id": str(txn.group_id),
            "campaign_id": str(txn.campaign_id) if txn.campaign_id else None,
            "transaction_code": txn.transaction_code,
            "amount": float(txn.amount),
            "sender_phone": txn.sender_phone,
            "payment_method": txn.payment_method,
            "source_evidence": txn.source_evidence,
            "status": txn.status,
            "created_at": txn.created_at.isoformat()
        }

        # 2. Calculate SHA-256 Hash
        serialized = json.dumps(txn_payload, sort_keys=True).encode()
        txn.ledger_hash = hashlib.sha256(serialized).hexdigest()
        
        logger.info(f"Integrity Seal Created: Transaction {txn.transaction_id} hashed and finalized in RDS.")
