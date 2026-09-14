from services.auth.auth_service import AuthService
from common.database import SessionLocal
import traceback

db = SessionLocal()
service = AuthService()
try:
    res = service.login(db, 'danielkarume.work@gmail.com', 'Password123!')
    refresh_token = res['RefreshToken']
    res2 = service.refresh_token(db, refresh_token)
    print("Refresh success!")
except Exception as e:
    traceback.print_exc()

