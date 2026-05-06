import os
import json
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTIVE_LEARNING_PATH = os.path.join(BASE_DIR, "data", "active_learning_pool.json")

def log_for_active_learning(raw_text: str, finalized_data: Dict[str, Any]):
    """
    Continuous Learning Module (Active Learning).
    
    When a Treasurer manually edits or approves a transaction, this function captures 
    the ground-truth corrections, computes the precise character offsets within the 
    raw message, and saves it to an active learning pool.
    
    A background worker can later use this pool to incrementally fine-tune the AI model.
    """
    entities = []
    
    # We must find the EXACT start and end character offsets in the raw_text
    def find_offset(value, label):
        if not value: return
        val_str = str(value)
        # Handle cases where value is a float (e.g. 510.0), but text has 510.00
        if label == "AMOUNT":
            # Just look for the number ignoring formatting if possible, or try a direct match
            # To be safe and avoid misalignments, we'll search for the numeric string in text
            # Often, if the user corrected it, we might have to be fuzzy, but for safety:
            matches = [m for m in re.finditer(r"[\d,.]+", raw_text)]
            for match in matches:
                clean_match = re.sub(r"[^\d.]", "", match.group(0))
                try:
                    if float(clean_str(clean_match)) == float(val_str):
                        # We found the exact amount substring
                        entities.append((match.start(), match.end(), label))
                        return
                except: pass
        else:
            # For SENDER, CODE, PROVIDER
            start_idx = raw_text.find(val_str)
            if start_idx != -1:
                entities.append((start_idx, start_idx + len(val_str), label))

    def clean_str(s):
        if s.count(".") > 1:
            parts = s.split(".")
            return "".join(parts[:-1]) + "." + parts[-1]
        return s

    find_offset(finalized_data.get("transaction_code"), "CODE")
    find_offset(finalized_data.get("sender_name"), "SENDER")
    find_offset(finalized_data.get("amount"), "AMOUNT")
    find_offset(finalized_data.get("provider"), "PROVIDER")
    find_offset(finalized_data.get("transaction_date"), "DATE")
    
    if not entities:
        logger.info("Active Learning: No mappable entities found. Skipping.")
        return

    record = {
        "text": raw_text,
        "entities": entities
    }
    
    # Append to the active learning pool safely
    pool = []
    if os.path.exists(ACTIVE_LEARNING_PATH):
        try:
            with open(ACTIVE_LEARNING_PATH, "r", encoding="utf-8") as f:
                pool = json.load(f)
        except Exception: pass
        
    pool.append(record)
    
    # Save back
    try:
        os.makedirs(os.path.dirname(ACTIVE_LEARNING_PATH), exist_ok=True)
        with open(ACTIVE_LEARNING_PATH, "w", encoding="utf-8") as f:
            json.dump(pool, f, indent=2)
        logger.info(f"Active Learning: Logged 1 new highly-valuable ground-truth sample.")
    except Exception as e:
        logger.error(f"Active Learning: Failed to write to pool: {e}")
