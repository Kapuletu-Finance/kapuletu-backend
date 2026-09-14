from common.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE pending_transactions ADD COLUMN processed_at DATETIME;"))
        conn.commit()
        print("Successfully added processed_at column.")
    except Exception as e:
        print(f"Error: {e}")
