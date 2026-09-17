import sys
import os

sys.path.append(os.getcwd())

from models.users import User
from models.token_blacklist import TokenBlacklist
from common.database import SessionLocal
from services.admin.user_service import UserService

def test_delete_user():
    db = SessionLocal()
    user_service = UserService(db)
    
    # Create test user
    test_user = User(
        first_name="Test",
        last_name="User",
        email="testdelete@kapuletu.local",
        phone_number="+1234567890",
        role="treasurer"
    )
    db.add(test_user)
    db.commit()
    db.refresh(test_user)
    
    print(f"Created user: {test_user.user_id}")
    
    # Create a TokenBlacklist entry
    token = TokenBlacklist(
        token="some_dummy_token",
        user_id=test_user.user_id,
        reason="test"
    )
    db.add(token)
    db.commit()
    
    print("Created TokenBlacklist entry")
    
    # Delete the user using user_service
    # Need to pass actor_id, we can pass test_user.user_id
    try:
        res = user_service.delete_user(str(test_user.user_id), str(test_user.user_id))
        print("Delete User Result:", res)
    except Exception as e:
        print("Error during deletion:")
        print(e)
    finally:
        # Cleanup if it failed
        u = db.query(User).filter(User.email == "testdelete@kapuletu.local").first()
        if u:
            print("Cleanup: User still exists, attempting to delete...")
            db.query(TokenBlacklist).filter(TokenBlacklist.user_id == u.user_id).delete()
            db.delete(u)
            db.commit()
            print("Cleanup done")

if __name__ == "__main__":
    test_delete_user()
