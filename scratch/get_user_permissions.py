import os
import sys

# Add the project root to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.database import SessionLocal
from models.users import User

def get_user_permissions():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == 'carsite694@gmail.com').first()
        if user:
            print(f"Found User: {user.email}")
            print(f"Role: {user.role}")
            print(f"Permissions: {user.permissions}")
        else:
            print("User not found")
    finally:
        db.close()

if __name__ == '__main__':
    get_user_permissions()
