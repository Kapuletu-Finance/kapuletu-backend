from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from common.database import get_db
from services.auth.auth_service import decode_token
from models.users import User
from models.token_blacklist import TokenBlacklist

# auto_error=False so it doesn't fail immediately if Header is missing; we want to check cookies too.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Dependency to secure endpoints.
    Extracts token from either Authorization Header or HTTP-Only Cookies.
    """
    if not token:
        token = request.cookies.get("kapuletu_access_token")
        
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    is_blacklisted = db.query(TokenBlacklist).filter(TokenBlacklist.token == token).first()
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
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

def get_optional_user(request: Request, token: str = Depends(OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)), db: Session = Depends(get_db)) -> Optional[Dict[str, Any]]:
    """
    For endpoints where authentication is optional.
    """
    try:
        return get_current_user(request, token, db)
    except HTTPException:
        return None

def get_verified_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    For endpoints where the user MUST be verified.
    """
    user_data = get_current_user(request, token, db)
    if user_data.get('phone_number_verified') != 'true' and user_data.get('email_verified') != 'true':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not verified. Please verify your phone or email to access this feature."
        )
    return user_data

def get_admin_user(current_user: Dict[str, Any] = Depends(get_verified_user)) -> Dict[str, Any]:
    """
    For endpoints restricted to admin and super_admin roles.
    """
    from common.enums import UserRole
    if current_user.get('role') not in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges. Admin access required."
        )
    return current_user

def get_super_admin_user(current_user: Dict[str, Any] = Depends(get_verified_user)) -> Dict[str, Any]:
    """
    For endpoints restricted exclusively to super_admin roles.
    """
    from common.enums import UserRole
    if current_user.get('role') != UserRole.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges. Super Admin access required."
        )
    return current_user


