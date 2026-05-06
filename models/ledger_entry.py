from dataclasses import dataclass

@dataclass
class LedgerEntry:
    """
    LedgerEntry Dataclass: Represents a cryptographically verifiable record.
    
    This corresponds to a document stored in Amazon QLDB. It includes a 
    checksum that ensures the transaction data has not been tampered with.
    """
    # Unique identifier in the ledger
    id: str
    # Reference to the finalized transaction in PostgreSQL
    transaction_id: str
    # SHA-256 hash or QLDB digest for verification
    checksum: str
    # Timestamp of the ledger commitment
    timestamp: str
