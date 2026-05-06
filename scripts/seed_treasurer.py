import sys
import os
import uuid
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.database import SessionLocal
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_treasurer(phone_number: str):
    db = SessionLocal()
    try:
        # Check if user already exists
        result = db.execute(text("SELECT user_id, full_name FROM users WHERE phone_number = :phone"), {"phone": phone_number}).fetchone()
        
        if not result:
            logger.info(f"Creating new treasurer with phone {phone_number}...")
            user_id = str(uuid.uuid4())
            db.execute(
                text("INSERT INTO users (user_id, full_name, phone_number, email, password_hash, role, is_active) VALUES (:id, :name, :phone, :email, :pwd, :role, :status)"),
                {"id": user_id, "name": "Joseph Treasurer", "phone": phone_number, "email": "joseph@example.com", "pwd": "hashedpassword123", "role": "treasurer", "status": True}
            )
            logger.info("Treasurer created successfully!")
        else:
            user_id = result[0]
            logger.info(f"Treasurer already exists: {result[1]}")

        db.commit()

    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_treasurer("+254714703374")
