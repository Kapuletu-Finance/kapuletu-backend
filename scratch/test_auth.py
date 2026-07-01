import requests
import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BASE_URL = "http://127.0.0.1:8000"
PHONE = "+254700112233"
EMAIL = "test_swagger@example.com"
PASSWORD = "SecurePassword123!"

def run_test():
    print("1. Registering user...")
    res = requests.post(f"{BASE_URL}/auth/register", json={
        "email": EMAIL,
        "password": PASSWORD,
        "first_name": "Swagger",
        "last_name": "Test",
        "phone_number": PHONE
    })
    
    if res.status_code == 400 and "already exists" in res.text:
        print("User already exists, proceeding...")
    else:
        print("Register:", res.status_code, res.json())
        assert res.status_code == 200, "Registration failed"

    print("\n2. Getting OTP from database...")
    conn = psycopg2.connect("postgresql://postgres:password@127.0.0.1:5433/kapuletu")
    cur = conn.cursor()
    cur.execute("SELECT code FROM otps WHERE username = %s ORDER BY expires_at DESC LIMIT 1", (PHONE,))
    otp = cur.fetchone()[0]
    print(f"OTP found: {otp}")
    
    print("\n3. Verifying user...")
    res = requests.post(f"{BASE_URL}/auth/verify", json={
        "phone_number": PHONE,
        "code": otp
    })
    print("Verify:", res.status_code, res.json())
    
    print("\n4. Logging in (simulating Swagger UI /auth/token)...")
    res = requests.post(f"{BASE_URL}/auth/token", data={
        "username": PHONE,
        "password": PASSWORD
    })
    print("Login:", res.status_code, res.json())
    assert res.status_code == 200, "Login failed"
    token = res.json()["access_token"]
    
    print("\n5. Accessing protected endpoint (/auth/me)...")
    res = requests.get(f"{BASE_URL}/auth/me", headers={
        "Authorization": f"Bearer {token}"
    })
    print("Me:", res.status_code, res.json())
    assert res.status_code == 200, "Protected endpoint failed"
    
    print("\nALL TESTS PASSED! Swagger UI is fully functional.")

if __name__ == "__main__":
    run_test()
