import logging
import hashlib
from sqlalchemy.orm import Session
from services.ingestion.parser_engine import parse_message
from repositories.transaction_repo import TransactionRepository
from models.pending_transaction import PendingTransaction
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class IngestionService:
    """
    IngestionService: Orchestrates the transformation of raw webhook payloads 
    into validated, structured 'Pending Transactions'.
    
    This service acts as the 'Gatekeeper', ensuring that only messages from 
    authorized treasurers are processed and that no duplicate entries reach the database.
    """
    
    def __init__(self, db: Session):
        """
        Initializes the service with a database session.
        Uses TransactionRepository for all data persistence and lookup logic.
        """
        self.db = db
        self.repo = TransactionRepository(db)

    def process_webhook(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes a raw message payload from Twilio.
        
        High-Level Workflow:
        1. Authentication: Verifies the sender's phone number maps to a Treasurer.
        2. Intelligence: Routes the text to the AI Parser Engine.
        3. Security: Generates and checks idempotency keys to prevent double-billing/duplicates.
        4. Persistence: Saves the result as a PendingTransaction in PostgreSQL.
        
        Args:
            raw_payload (dict): The dictionary of data received from the webhook.
            
        Returns:
            dict: Outcome of the processing (success, error, or ignored).
        """
        message_body = raw_payload.get("Body", "").strip()
        sender_phone = raw_payload.get("From", "")
        
        logger.info(f"Ingesting message from {sender_phone}: {message_body[:50]}...")

        # 1. Resolve Owner (Treasurer)
        # Every transaction MUST belong to a treasurer. We use the phone number as the identifier.
        owner = self.repo.resolve_owner_by_phone(sender_phone)
        if not owner:
            logger.warning(f"Unauthorized Access: No treasurer found for phone: {sender_phone}")
            return {"status": "error", "message": "unauthorized_phone"}

        # 2. Parse Logic (AI + Regex Hybrid)
        # The parser extracts sender name, amount, and transaction codes from the message text.
        parsed_data = parse_message(message_body)
        
        # 3. Idempotency Check (Duplicate Prevention)
        # We ensure every transaction is processed EXACTLY once.
        # Logic: 
        # - Use the official M-Pesa/Bank transaction code if present.
        # - If manual entry, generate a deterministic hash of the (Treasurer + Message Body).
        txn_code = parsed_data.get("transaction_code")
        if not txn_code:
            # Fallback idempotency key generation
            context_string = f"{owner.user_id}:{message_body}"
            txn_code = f"HASH-{hashlib.md5(context_string.encode()).hexdigest()[:12]}"
            parsed_data["transaction_code"] = txn_code

        # Check if this code has already been seen in the system
        if self.repo.check_duplicate_transaction_code(txn_code):
            logger.info(f"Idempotency Trigger: Duplicate entry detected ({txn_code}). Skipping processing.")
            return {"status": "ignored", "message": "duplicate_entry", "code": txn_code}

        # 4. Create Pending Record
        # We store the message in a 'Pending' state, awaiting treasurer review/approval.
        pending_txn = PendingTransaction(
            owner_id=owner.user_id,
            raw_message=message_body,
            sender_name=parsed_data.get("sender_name"),
            amount=parsed_data.get("amount"),
            currency=parsed_data.get("currency") or "KES",
            transaction_code=txn_code,
            sender_phone=parsed_data.get("phone") or sender_phone,
            purpose=parsed_data.get("purpose"),
            confidence_score=parsed_data.get("confidence_score"),
            workflow_status="pending"
        )
        
        # Save to database
        saved_txn = self.repo.insert_pending_transaction(pending_txn)
        
        logger.info(f"Ingestion Successful: ID {saved_txn.pending_id} created with {saved_txn.confidence_score*100}% AI confidence.")
        
        # Log the parsed output for developer visibility
        import json
        logger.info(f"Parsed Output:\n{json.dumps(parsed_data, indent=2)}")
        
        return {
            "status": "success",
            "pending_id": str(saved_txn.pending_id),
            "owner_id": str(owner.user_id),
            "parsed_data": parsed_data
        }
