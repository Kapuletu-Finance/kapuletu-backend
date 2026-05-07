from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.pending_transaction import PendingTransaction
from models.users import User


class TransactionRepository:
    """
    TransactionRepository: Encapsulates all database interactions related to transactions.
    
    This layer abstracts the SQLAlchemy logic away from the service layer, 
    ensuring a clean separation of concerns and making the code easier to test.
    """
    
    def __init__(self, db: Session):
        """Initializes the repository with a database session."""
        self.db = db

    def insert_pending_transaction(self, pending_txn: PendingTransaction) -> PendingTransaction:
        """
        Persists a new pending transaction to the PostgreSQL database.
        
        Args:
            pending_txn (PendingTransaction): The model instance to save.
            
        Returns:
            PendingTransaction: The persisted instance with generated IDs and timestamps.
        """
        self.db.add(pending_txn)
        self.db.commit()
        self.db.refresh(pending_txn)
        return pending_txn

    def check_duplicate_transaction_code(self, transaction_code: str) -> bool:
        """
        Checks if a transaction code (or idempotency hash) already exists in 
        EITHER the pending queue or the finalized ledger.
        
        Args:
            transaction_code (str): The unique code to check.
            
        Returns:
            bool: True if a match is found in either table, False otherwise.
        """
        if not transaction_code:
            return False
            
        # 1. Check Pending Transactions
        from models.transaction import Transaction
        
        pending_exists = self.db.query(PendingTransaction).filter(
            PendingTransaction.transaction_code == transaction_code
        ).first() is not None
        
        if pending_exists:
            return True
            
        # 2. Check Finalized Transactions
        finalized_exists = self.db.query(Transaction).filter(
            Transaction.transaction_code == transaction_code
        ).first() is not None
        
        return finalized_exists

    def resolve_owner_by_phone(self, phone_number: str) -> Optional[User]:
        """
        Identifies the Treasurer (User) associated with a specific phone number.
        This is used during ingestion to route messages to the correct account.
        
        Args:
            phone_number (str): The sender's phone number.
            
        Returns:
            Optional[User]: The User record if found, else None.
        """
        stmt = select(User).where(User.phone_number == phone_number)
        return self.db.execute(stmt).scalars().first()

    def fetch_pending_transactions_by_owner(self, owner_id: UUID) -> List[PendingTransaction]:
        """
        Retrieves all unprocessed pending transactions for a specific treasurer.
        Typically used to populate the treasurer's approval inbox.
        
        Args:
            owner_id (UUID): The unique ID of the treasurer.
            
        Returns:
            List[PendingTransaction]: A list of pending transactions.
        """
        stmt = select(PendingTransaction).where(
            PendingTransaction.owner_id == owner_id,
            PendingTransaction.is_processed == False
        )
        return self.db.execute(stmt).scalars().all()
