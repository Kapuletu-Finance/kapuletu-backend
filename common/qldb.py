import os
from pyqldb.driver.qldb_driver import QldbDriver

def get_qldb_driver():
    """
    Initializes and returns the Amazon QLDB (Quantum Ledger Database) driver.
    
    QLDB is used as the immutable, cryptographically verifiable source of truth 
    for all finalized financial transactions. Every approval is logged here 
    to ensure a tamper-proof audit trail.
    """
    ledger_name = os.environ.get('QLDB_LEDGER_NAME', 'kapuletu-ledger')
    # The driver handles connection pooling and retries automatically
    return QldbDriver(ledger_name=ledger_name)
