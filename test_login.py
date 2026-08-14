import asyncio
from services.auth.auth_service import AuthService
from common.database import SessionLocal

async def main():
    db = SessionLocal()
    service = AuthService()
    try:
        res = service.login(db, "danielkarume.work@gmail.com", "Password123!")
        print("Success!", res)
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

asyncio.run(main())
