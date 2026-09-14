import asyncio
from services.auth.auth_service import AuthService
from common.database import SessionLocal
from common.auth_dependencies import get_current_user
from fastapi import Request

class MockRequest:
    def __init__(self, token):
        self.cookies = {"kapuletu_access_token": token}

async def main():
    db = SessionLocal()
    service = AuthService()
    try:
        # First log in to get a token
        res = service.login(db, "danielkarume.work@gmail.com", "Password123!")
        token = res["AccessToken"]
        
        # Now test get_current_user
        req = MockRequest(token)
        user_data = get_current_user(req, token, db)
        print("Success:", user_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

asyncio.run(main())
