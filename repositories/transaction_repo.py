from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from common.utils import parse_uuid
from sqlalchemy.orm import Session
import time

_UNAUTHORIZED_PHONE_CACHE = {}

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

    def check_duplicate_transaction_code(self, transaction_code: str, owner_id: UUID) -> bool:
        """
        Checks if a transaction code (or idempotency hash) already exists in 
        EITHER the pending queue or the finalized ledger FOR THIS SPECIFIC USER.
        
        Args:
            transaction_code (str): The unique code to check.
            owner_id (UUID): The user to check against.
            
        Returns:
            bool: True if a match is found in either table, False otherwise.
        """
        if not transaction_code:
            return False
            
        # 1. Check Pending Transactions
        from models.transaction import Transaction
        
        pending_exists = self.db.query(PendingTransaction).filter(
            PendingTransaction.transaction_code == transaction_code,
            PendingTransaction.owner_id == parse_uuid(owner_id)
        ).first() is not None
        
        if pending_exists:
            return True
            
        # 2. Check Finalized Transactions
        finalized_exists = self.db.query(Transaction).filter(
            Transaction.transaction_code == transaction_code,
            Transaction.owner_id == parse_uuid(owner_id)
        ).first() is not None
        
        return finalized_exists

    def resolve_owner_by_phone(self, phone_number: str) -> Optional[User]:
        """
        Identifies the Treasurer (User) associated with a specific phone number.
        This is used during ingestion to route messages to the correct account.
        Includes a 5-minute TTL cache for unauthorized numbers to prevent DB DoS attacks.
        
        Args:
            phone_number (str): The sender's phone number.
            
        Returns:
            Optional[User]: The User record if found, else None.
        """
        now = time.time()
        
        # Check Circuit Breaker / Cache
        if phone_number in _UNAUTHORIZED_PHONE_CACHE:
            if now - _UNAUTHORIZED_PHONE_CACHE[phone_number] < 300: # 5 minute TTL
                return None
            else:
                del _UNAUTHORIZED_PHONE_CACHE[phone_number]
                
        stmt = select(User).where(User.phone_number == phone_number)
        user = self.db.execute(stmt).scalars().first()
        
        if not user:
            _UNAUTHORIZED_PHONE_CACHE[phone_number] = now
            # Cap memory growth
            if len(_UNAUTHORIZED_PHONE_CACHE) > 10000:
                _UNAUTHORIZED_PHONE_CACHE.clear()
                
        return user

    def fetch_pending_transactions_by_owner(self, owner_id: UUID, skip: int = 0, limit: int = 100, search: Optional[str] = None, filter_val: Optional[str] = None) -> tuple[List[PendingTransaction], int]:
        """
        Retrieves all unprocessed pending transactions for a specific treasurer with pagination.
        Typically used to populate the treasurer's approval inbox.
        
        Args:
            owner_id (UUID): The unique ID of the treasurer.
            skip (int): Pagination offset.
            limit (int): Pagination limit.
            search (Optional[str]): Search query for name or code.
            filter_val (Optional[str]): Date filter.
            
        Returns:
            tuple: (List[PendingTransaction], total_count)
        """
        from sqlalchemy import func, or_
        from datetime import datetime, timedelta
        
        base_query = self.db.query(PendingTransaction).filter(
            PendingTransaction.owner_id == parse_uuid(owner_id),
            PendingTransaction.is_processed == False
        )
        
        if search:
            search_term = f"%{search}%"
            base_query = base_query.filter(or_(
                PendingTransaction.sender_name.ilike(search_term),
                PendingTransaction.transaction_code.ilike(search_term)
            ))
            
        if filter_val:
            now = datetime.utcnow()
            if filter_val == "today":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                base_query = base_query.filter(PendingTransaction.created_at >= start_date)
            elif filter_val == "this_week":
                start_date = now - timedelta(days=now.weekday())
                start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                base_query = base_query.filter(PendingTransaction.created_at >= start_date)
            elif filter_val == "this_month":
                start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                base_query = base_query.filter(PendingTransaction.created_at >= start_date)
            elif filter_val == "this_year":
                start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                base_query = base_query.filter(PendingTransaction.created_at >= start_date)

        total = base_query.count()
        items = base_query.order_by(PendingTransaction.created_at.desc()).offset(skip).limit(limit).all()
        return items, total

    def fetch_pending_transactions_by_campaign(self, campaign_id: UUID, owner_id: UUID, skip: int = 0, limit: int = 100):
        """Fetches pending transactions for a specific campaign."""
        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(PendingTransaction).where(
            PendingTransaction.owner_id == parse_uuid(owner_id),
            PendingTransaction.campaign_id == parse_uuid(campaign_id),
            PendingTransaction.is_processed == False
        )
        total = self.db.execute(count_stmt).scalar()
        
        stmt = select(PendingTransaction).where(
            PendingTransaction.owner_id == parse_uuid(owner_id),
            PendingTransaction.campaign_id == parse_uuid(campaign_id),
            PendingTransaction.is_processed == False
        ).order_by(PendingTransaction.created_at.desc()).offset(skip).limit(limit)
        
        items = self.db.execute(stmt).scalars().all()
        return items, total

    def fetch_pending_transaction_by_id(self, pending_id: str, owner_id: UUID) -> Optional[PendingTransaction]:
        """
        Retrieves a specific pending transaction for a specific treasurer.
        
        Args:
            pending_id (str): The unique ID of the pending transaction.
            owner_id (UUID): The unique ID of the treasurer.
            
        Returns:
            Optional[PendingTransaction]: The pending transaction if found and owned by user, else None.
        """
        stmt = select(PendingTransaction).where(
            PendingTransaction.pending_id == parse_uuid(pending_id),
            PendingTransaction.owner_id == parse_uuid(owner_id),
            PendingTransaction.is_processed == False
        )
        return self.db.execute(stmt).scalars().first()

    def fetch_inbox_history(
        self, owner_id: UUID, skip: int = 0, limit: int = 100, 
        status: Optional[str] = None, search: Optional[str] = None, 
        date_from: Optional[str] = None, date_to: Optional[str] = None
    ):
        """
        Retrieves processed inbox transactions for history.
        """
        from sqlalchemy import or_, desc
        from datetime import datetime

        query = self.db.query(
            PendingTransaction,
            User.first_name,
            User.last_name
        ).outerjoin(User, PendingTransaction.processed_by == User.user_id).filter(
            PendingTransaction.owner_id == parse_uuid(owner_id),
            PendingTransaction.is_processed == True
        )

        if status and status != "all":
            query = query.filter(PendingTransaction.workflow_status == status)

        if search:
            search_term = f"%{search}%"
            query = query.filter(or_(
                PendingTransaction.sender_name.ilike(search_term),
                PendingTransaction.transaction_code.ilike(search_term)
            ))

        if date_from:
            try:
                dt_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                query = query.filter(PendingTransaction.processed_at >= dt_from)
            except ValueError:
                pass

        if date_to:
            try:
                dt_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                query = query.filter(PendingTransaction.processed_at <= dt_to)
            except ValueError:
                pass

        total = query.count()
        items = query.order_by(desc(PendingTransaction.processed_at)).offset(skip).limit(limit).all()

        results = []
        for pending, fname, lname in items:
            processed_by_name = f"{fname or ''} {lname or ''}".strip() if fname or lname else None
            results.append({
                "pending": pending,
                "processed_by_name": processed_by_name
            })
            
        return results, total
