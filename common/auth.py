import jwt
import datetime
import os
from passlib.context import CryptContext
from common.config import get_config

config = get_config()
# Authentication & Security Utilities
# This module handles password security (hashing) and session management (JWT).

config = get_config()
# Use bcrypt for industry-standard password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security parameters for JWT generation
SECRET_KEY = os.getenv("JWT_SECRET", "supersecret")
ALGORITHM = "HS256"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Checks if a plain-text password matches its hashed version.
    Used during user login.
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Generates a secure hash of a password.
    Used during user registration.
    """
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: datetime.timedelta = None) -> str:
    """
    Generates a JSON Web Token (JWT) for session management.
    
    Args:
        data (dict): The payload to include (e.g., user_id, role).
        expires_delta (timedelta): How long the token is valid for.
        
    Returns:
        str: An encoded JWT string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        # Default session duration is 15 minutes for high security
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """
    Parses and validates a JWT.
    
    Returns:
        dict: The decrypted payload if the token is valid and not expired.
        None: If the token is invalid or corrupted.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        # Errors include ExpiredSignatureError and InvalidTokenError
        return None
