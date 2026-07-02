from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from common.database import get_db
from services.auth.auth_service import decode_token
from models.users import User

# This line magically enables the "Authorize" padlock in Swagger UI!
# It tells Swagger that authentication is handled by sending form-data to /auth/token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Dependency to secure endpoints.
    Extracts the Bearer token, validates it securely via PyJWT, and fetches user data from Postgres.
    """
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Replicate the dictionary structure that Cognito used, so routers remain compatible
    user_data = {
        'sub': str(user.user_id),
        'email': user.email,
        'given_name': user.first_name,
        'family_name': user.last_name,
        'phone_number': user.phone_number,
        'email_verified': 'true' if user.email_verified else 'false',
        'phone_number_verified': 'true' if user.phone_number_verified else 'false',
        'role': user.role,
        'access_token': token
    }
    return user_data

def get_optional_user(token: str = Depends(OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)), db: Session = Depends(get_db)) -> Optional[Dict[str, Any]]:
    """
    For endpoints where authentication is optional.
    """
    if not token:
        return None
    try:
        return get_current_user(token, db)
    except HTTPException:
        return None
