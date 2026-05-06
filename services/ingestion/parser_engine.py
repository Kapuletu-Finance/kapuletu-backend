import os
import re
import spacy
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# THE AI CORE: Loads the proprietary trained weights if available
MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../models/kapuletu_ai_v1")

class ModelBasedParser:
    """
    KapuLetu AI Core: Intelligent Financial Message Parsing Engine.
    
    This engine combines Machine Learning (SpaCy NER) with deterministic heuristics 
    to extract structured financial data from unstructured text messages (WhatsApp/SMS).
    
    The architecture follows a 'Safety-First' approach:
    1. Named Entity Recognition (NER) identifies primary fields.
    2. Heuristics (Regex) act as a fallback/validation layer.
    3. Cleaning logic normalizes financial strings into floats/standard codes.
    """
    
    def __init__(self):
        """
        Initializes the NLP pipeline. 
        Attempts to load a custom-trained SpaCy model for higher accuracy.
        Falls back to a blank English model if the proprietary weights are missing.
        """
        try:
            if os.path.exists(MODEL_PATH):
                logger.info(f"AI Core: Loading production model weights from {MODEL_PATH}")
                self.nlp = spacy.load(MODEL_PATH)
                self.is_trained = True
            else:
                logger.warning("AI Core: Custom model weights not found. Falling back to heuristic-heavy mode.")
                self.nlp = spacy.blank("en") # Efficient but requires fallback regex
                self.is_trained = False
        except Exception as e:
            logger.error(f"AI Core Initialization Error: {e}")
            self.nlp = spacy.blank("en")
            self.is_trained = False

    def parse(self, message_text: str) -> Dict[str, Any]:
        """
        Executes the full parsing pipeline on a single message string.
        
        Logic Flow:
        1. Contextual Extraction: SpaCy identifies entities like SENDER, AMOUNT, PURPOSE.
        2. Safeguard Check: If critical data (amount/name) is missing, regex logic is triggered.
        3. Confidence Scoring: Assigns a score based on whether the custom model was used.
        
        Args:
            message_text (str): The raw text of the received message.
            
        Returns:
            dict: Structured data containing amount, transaction_code, sender_name, purpose.
        """
        # Run the NLP pipeline with error handling
        try:
            doc = self.nlp(message_text)
        except Exception as e:
            logger.error(f"AI Core Runtime Error: {e}. Falling back to heuristics.")
            # Create a blank doc if model fails
            doc = spacy.blank("en")(message_text)
            self.is_trained = False
        
        # Initialize the data schema
        data = {
            "sender_name": None,
            "amount": 0.0,
            "transaction_code": None,
            "purpose": None,
            "provider": None,
            "transaction_date": None,
            "account": None,
            "confidence_score": 0.0
        }

        # 1. AI-Driven Extraction using Named Entities
        # We iterate through the identified 'entities' in the text.
        for ent in doc.ents:
            if ent.label_ == "SENDER":
                data["sender_name"] = ent.text
            elif ent.label_ == "AMOUNT":
                data["amount"] = self._clean_amount(ent.text)
            elif ent.label_ == "CODE":
                data["transaction_code"] = ent.text
            elif ent.label_ == "PURPOSE":
                data["purpose"] = ent.text
            elif ent.label_ == "PROVIDER":
                data["provider"] = ent.text
            elif ent.label_ == "DATE":
                data["transaction_date"] = ent.text
            elif ent.label_ == "ACCOUNT":
                data["account"] = ent.text

        # 2. Heuristic Safeguard (Regex Fallback)
        # If the AI model missed critical fields (common with unstructured SMS),
        # we run deterministic regex patterns to 'catch' the data.
        if not data["amount"] or not data["sender_name"] or not data["transaction_code"]:
            data = self._safeguard_heuristics(message_text, data)

        # 3. Confidence Calculation
        # In production, this would be based on the model's 'prob' output.
        # Here we use a static indicator of model presence.
        data["confidence_score"] = 1.0 if self.is_trained else 0.7
        return data

    def _safeguard_heuristics(self, text: str, existing_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Regex-based fallback logic to ensure high capture rates.
        Uses common Kenyan financial message patterns (Ksh, MPESA codes).
        """
        # Capture Amount (e.g. 'Ksh 1,500.00' or 'Ksh1500')
        if not existing_data["amount"]:
            amt_match = re.search(r"Ksh\s?([\d,.]+)", text, re.I)
            if amt_match:
                existing_data["amount"] = self._clean_amount(amt_match.group(1))
        
        # Capture Transaction Code (Alpha-numeric, usually 10+ chars)
        if not existing_data["transaction_code"]:
            code_match = re.search(r"\b([A-Z\d]{10,})\b", text)
            if code_match:
                existing_data["transaction_code"] = code_match.group(1)
                
        return existing_data

    def _clean_amount(self, amt_str: str) -> float:
        """
        Normalizes currency strings into machine-readable floats.
        Removes currency symbols, commas, and whitespace.
        """
        try:
            import re
            clean_str = re.sub(r"[^\d.]", "", amt_str)
            # Remove trailing/multiple dots if they appear by accident
            if clean_str.count(".") > 1:
                parts = clean_str.split(".")
                clean_str = "".join(parts[:-1]) + "." + parts[-1]
            return float(clean_str)
        except (ValueError, TypeError):
            return 0.0

_parser_instance = None

def parse_message(message_text: str) -> Dict[str, Any]:
    """Utility wrapper for one-off parsing calls using a cached singleton."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = ModelBasedParser()
    return _parser_instance.parse(message_text)
