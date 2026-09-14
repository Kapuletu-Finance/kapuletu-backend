from common.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    queries = [
        "ALTER TABLE pending_transactions ADD COLUMN processed_by VARCHAR;",
        "ALTER TABLE pending_transactions ADD COLUMN rejection_reason TEXT;",
        "ALTER TABLE pending_transactions ADD COLUMN payment_method VARCHAR;",
        "ALTER TABLE pending_transactions ADD COLUMN source_evidence TEXT;",
    ]
    for q in queries:
        try:
            conn.execute(text(q))
            conn.commit()
            print(f"Executed: {q}")
        except Exception as e:
            if "duplicate column name" in str(e):
                pass
            else:
                print(f"Error on {q}: {e}")

