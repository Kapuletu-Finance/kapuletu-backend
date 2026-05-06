from sqlalchemy import Column, String, DateTime, JSON
import datetime
from .base import Base

from sqlalchemy import Column, String, JSON, DateTime
from .users import Base
import datetime

class ParserKnowledge(Base):
    """
    ParserKnowledge Model: The permanent memory of the Ingestion AI.
    
    This table stores structural 'fingerprints' of financial messages that have 
    been successfully parsed and confirmed by treasurers. It allows the AI 
    to learn over time: if a message shape is seen repeatedly, the system 
    increases its confidence score for that specific format.
    """
    __tablename__ = "parser_knowledge_base"

    # Fingerprint: A normalized representation of a message's structure 
    # (e.g., 'TOKEN Confirmed. You have received Ksh NUM from NAME')
    fingerprint = Column(String, primary_key=True)
    
    # Mapping logic: Stores the specific index positions or regex groups 
    # that reliably extract data for this specific fingerprint.
    # Structure: {"sender_name_indices": [0], "amount_index": 2}
    mapping_logic = Column(JSON, nullable=False)
    
    # Track the popularity and reliability of this message pattern
    last_seen = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    discovery_date = Column(DateTime, default=datetime.datetime.utcnow)
