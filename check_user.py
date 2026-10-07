import asyncio
from common.database import SessionLocal
from models.users import User

def check_user():
    db = SessionLocal()
    try:
        user_id = "64b6aab8-641f-4e8d-a623-d16ecf3e52d9"
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            print(f"Found user: {user.email}, role: {user.role}, is_active: {user.is_active}")
        else:
            print("User not found in DB")
    finally:
        db.close()

if __name__ == "__main__":
    check_user()
