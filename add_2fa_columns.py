from common.database import engine
from sqlalchemy import text

def add_columns():
    with engine.connect() as conn:
        print("Checking if two_factor_enabled exists...")
        # We can just try to run ALTER TABLE
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN DEFAULT FALSE;"))
            print("Added two_factor_enabled column successfully.")
        except Exception as e:
            print("two_factor_enabled might already exist or error:", e)

        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_channel VARCHAR(255);"))
            print("Added two_factor_channel column successfully.")
        except Exception as e:
            print("two_factor_channel might already exist or error:", e)
            
        try:
            conn.commit()
            print("Committed changes.")
        except Exception as e:
            pass
            
    print("Database modification complete!")

if __name__ == "__main__":
    add_columns()
