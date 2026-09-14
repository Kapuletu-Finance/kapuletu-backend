from common.database import SessionLocal
from models.pending_transaction import PendingTransaction

db = SessionLocal()
try:
    txs = db.query(PendingTransaction).limit(1).all()
    print("Success")
except Exception as e:
    print(f"Error: {e}")
