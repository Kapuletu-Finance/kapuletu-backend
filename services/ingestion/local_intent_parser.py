import spacy
from spacy.matcher import Matcher
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LocalIntentParser:
    """
    Kapuletu AI: Local NLP Intent Parser
    
    A blazingly fast, 100% local, offline NLP engine using spaCy.
    It detects conversational commands like creating groups or campaigns,
    and extracts the entities (group name, campaign title) using
    rule-based matching and dependency parsing.
    """
    def __init__(self):
        try:
            # We try to load a small English model. If not available, fallback to blank.
            # In production, en_core_web_sm should be installed via `python -m spacy download en_core_web_sm`
            self.nlp = spacy.load("en_core_web_sm")
            self.matcher = Matcher(self.nlp.vocab)
            self._setup_patterns()
        except Exception as e:
            logger.warning(f"Kapuletu AI NLP Model not found. Falling back to blank model. {e}")
            self.nlp = spacy.blank("en")
            self.matcher = Matcher(self.nlp.vocab)
            self._setup_patterns()

    def _setup_patterns(self):
        # Intent: Create Group
        # Matches: "create a group", "add new group", "setup a welfare group", "new group"
        group_pattern_1 = [
            {"LOWER": {"IN": ["create", "add", "make", "setup", "new", "start"]}},
            {"IS_PUNCT": True, "OP": "?"},
            {"LOWER": {"IN": ["a", "an", "the", "new"]}, "OP": "?"},
            {"LOWER": {"IN": ["group", "welfare", "fund", "committee"]}}
        ]
        
        # Intent: Create Campaign
        # Matches: "create a campaign", "add new campaign", "start a project"
        campaign_pattern_1 = [
            {"LOWER": {"IN": ["create", "add", "make", "setup", "new", "start"]}},
            {"IS_PUNCT": True, "OP": "?"},
            {"LOWER": {"IN": ["a", "an", "the", "new"]}, "OP": "?"},
            {"LOWER": {"IN": ["campaign", "project", "goal", "drive", "harambee", "contribution"]}}
        ]

        self.matcher.add("CREATE_GROUP", [group_pattern_1])
        self.matcher.add("CREATE_CAMPAIGN", [campaign_pattern_1])

    def detect_intent(self, text: str) -> Dict[str, Any]:
        """
        Parses the text and returns a structured intent payload.
        """
        doc = self.nlp(text)
        matches = self.matcher(doc)
        
        # Default response
        result = {
            "intent": "unknown",
            "entities": {}
        }
        
        if not matches:
            return result

        # We take the first matched intent
        match_id, start, end = matches[0]
        intent_label = self.nlp.vocab.strings[match_id]
        
        if intent_label == "CREATE_GROUP":
            result["intent"] = "create_group"
            name = self._extract_name_after_match(doc, end)
            if name:
                result["entities"]["group_name"] = name
            else:
                # Fallback if dependency parser fails or it's a blank model
                # Just take the rest of the string
                result["entities"]["group_name"] = text[doc[end-1].idx + len(doc[end-1].text):].strip(" :-'\"")
                    
        elif intent_label == "CREATE_CAMPAIGN":
            result["intent"] = "create_campaign"
            title = self._extract_name_after_match(doc, end)
            if title:
                result["entities"]["campaign_title"] = title
            else:
                result["entities"]["campaign_title"] = text[doc[end-1].idx + len(doc[end-1].text):].strip(" :-'\"")

        # Basic fallback: if someone just types "NEW GROUP: Welfare", the substring logic captures "Welfare"
        # We can clean up the extracted text:
        for k, v in result["entities"].items():
            if v:
                # Remove common joining words if they start the phrase
                v_clean = v.strip()
                if v_clean.lower().startswith("called "):
                    v_clean = v_clean[7:].strip()
                elif v_clean.lower().startswith("for "):
                    v_clean = v_clean[4:].strip()
                elif v_clean.lower().startswith("named "):
                    v_clean = v_clean[6:].strip()
                result["entities"][k] = v_clean.strip(" :-'\"")
                
        return result

    def _extract_name_after_match(self, doc, match_end_idx) -> Optional[str]:
        """
        Uses simple heuristics to extract the proper noun or noun phrase following the match.
        """
        if match_end_idx >= len(doc):
            return None
            
        # Collect all tokens after the match that form the name
        tokens = []
        for i in range(match_end_idx, len(doc)):
            tok = doc[i]
            # Skip filler words immediately following
            if tok.lower_ in ["called", "named", "for", "as", ":", "-", "is"]:
                if len(tokens) == 0:
                    continue
            tokens.append(tok.text)
            
        return " ".join(tokens) if tokens else None

# Singleton instance
intent_parser = LocalIntentParser()
