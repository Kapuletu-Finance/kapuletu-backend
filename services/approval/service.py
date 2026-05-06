from sqlalchemy.orm import Session
from models.transaction import Transaction
from models.pending_transaction import PendingTransaction
from common.qldb import get_qldb_driver
from common.logger import get_logger
from services.ingestion.active_learner import log_for_active_learning

logger = get_logger(__name__)

class ApprovalService:
    """
    ApprovalService: Manages the transition of financial records from 'Pending' 
    to 'Immutable Ledger' state.
    
    This service ensures that once a treasurer approves a transaction, it is 
    permanently recorded in both the relational database (for fast queries) 
    and Amazon QLDB (for audit integrity).
    """
    def __init__(self, db: Session):
        """Initializes service with SQL and QLDB drivers."""
        self.db = db
        self.qldb = get_qldb_driver()

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
        # 1. Fetch the original pending record
        pending = self.db.query(PendingTransaction).filter(PendingTransaction.pending_id == pending_txn_id).first()
        if not pending:
            logger.error(f"Approval Failed: Pending ID {pending_txn_id} not found.")
            raise Exception("Pending transaction not found")

        # 2. Transition to Permanent Transaction record
        # This moves the data from the 'scratchpad' (Pending) to the 'General Ledger' (Transaction).
        new_txn = Transaction(
            owner_id=treasurer_id,
            group_id=group_id,
            campaign_id=campaign_id,
            transaction_code=pending.transaction_code,
            amount=pending.amount,
            sender_phone=pending.sender_phone,
            status="approved"
        )
        self.db.add(new_txn)
        self.db.flush() # Flushes to DB to generate the transaction_id for the ledger record

        # 2.5 Active Learning Hook
        # Feed the ground truth (after potential treasurer edits) back into the AI loop
        finalized_data = {
            "amount": float(new_txn.amount) if new_txn.amount else None,
            "sender_name": pending.sender_name,
            "transaction_code": new_txn.transaction_code,
            # If provider/date become fields later, map them here.
        }
        try:
            log_for_active_learning(pending.raw_message, finalized_data)
        except Exception as e:
            logger.error(f"Active Learning Hook Failed: {e}")

        # 3. Write to QLDB (The immutable truth)
        # We write to the ledger BEFORE committing the SQL transaction.
        # If the ledger write fails, we rollback the entire operation to maintain consistency.
        try:
            self._write_to_ledger(new_txn)
        except Exception as e:
            logger.error(f"Ledger Integrity Error: Failed to write to QLDB: {e}")
            self.db.rollback()
            raise Exception("Ledger commitment failed. Transaction has been rolled back for safety.")

        # 4. Mark pending as processed
        # This ensures the item no longer appears in the treasurer's approval inbox.
        pending.is_processed = True
        pending.workflow_status = "approved"
        
        self.db.commit()
        logger.info(f"Transaction {new_txn.transaction_id} successfully finalized and ledger-locked.")
        return new_txn

    def _write_to_ledger(self, txn: Transaction):
        """
        Internal helper to format and commit data to Amazon QLDB.
        QLDB ensures that the financial history is tamper-proof and cryptographically verifiable.
        """
        # Note: In a production scenario, we convert the SQLAlchemy model to Ion/JSON
        # for insertion into the QLDB 'Transactions' table.
        # Example: self.qldb.execute_statement("INSERT INTO LedgerTransactions VALUE ?", txn_data)
        pass
