import hashlib
import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from models.pending_transaction import PendingTransaction
from repositories.transaction_repo import TransactionRepository
from services.ingestion.parser_engine import parse_message
from services.notifications.service import create_notification

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
        from services.ingestion.parser_engine import parse_message, split_batch_messages
        messages = split_batch_messages(message_body)
        
        parsed_results = []
        for msg in messages:
            parsed_data = parse_message(msg)
            
            # Check for intelligent guardrails
            if parsed_data.get("status") in ["REPORT_OR_SUMMARY", "CHATTER"]:
                # If there's only one message, return the invalid status right away
                if len(messages) == 1:
                    return {"status": "invalid", "message": parsed_data["status"]}
                continue # Skip invalid ones in a batch

            # MVD Validation
            amount = parsed_data.get("amount") or 0.0
            sender_name = parsed_data.get("sender_name")
            txn_code_parsed = parsed_data.get("transaction_code")
            
            if amount <= 0 and not sender_name and not txn_code_parsed:
                if len(messages) == 1:
                    logger.warning(f"Validation Guardrail: Message failed MVD threshold. Not a valid transaction.")
                    return {"status": "invalid", "message": "unrecognized_format"}
                continue
            
            # Idempotency Check
            txn_code = parsed_data.get("transaction_code")
            if not txn_code:
                context_string = f"{owner.user_id}:{msg}"
                txn_code = f"HASH-{hashlib.md5(context_string.encode()).hexdigest()[:12]}"
                parsed_data["transaction_code"] = txn_code

            if self.repo.check_duplicate_transaction_code(txn_code, owner.user_id):
                if len(messages) == 1:
                    logger.info(f"Idempotency Trigger: Duplicate entry detected ({txn_code}). Skipping processing.")
                    return {"status": "ignored", "message": "duplicate_entry", "code": txn_code}
                continue

            # Create Pending Record
            pending_txn = PendingTransaction(
                owner_id=owner.user_id,
                raw_message=msg,
                sender_name=parsed_data.get("sender_name"),
                amount=parsed_data.get("amount"),
                currency=parsed_data.get("currency") or "KES",
                transaction_code=txn_code,
                sender_phone=parsed_data.get("phone") or sender_phone,
                purpose=parsed_data.get("purpose"),
                original_ai_output=parsed_data,
                confidence_score=parsed_data.get("confidence_score"),
                workflow_status="pending",
                payment_method="M-Pesa",
                source_evidence=msg
            )
            
            saved_txn = self.repo.insert_pending_transaction(pending_txn)
            parsed_results.append({
                "pending_id": str(saved_txn.pending_id),
                "parsed_data": parsed_data
            })
            
            logger.info(f"Ingestion Successful: ID {saved_txn.pending_id} created with {saved_txn.confidence_score*100}% AI confidence.")
            
            # Notify the Treasurer
            create_notification(
                db=self.db,
                user_id=str(owner.user_id),
                title="New Pending Transaction",
                message=f"A transaction of {saved_txn.currency} {saved_txn.amount} from {saved_txn.sender_name or 'a member'} is awaiting your approval.",
                type="transaction_pending",
                related_entity_id=str(saved_txn.pending_id)
            )

        if not parsed_results:
            if len(messages) > 1:
                return {"status": "error", "message": "No valid transactions found in batch"}
            # The singular cases are already handled above

        # Return a bulk success if there are results
        return {
            "status": "success",
            "owner_id": str(owner.user_id),
            "results": parsed_results
        }
