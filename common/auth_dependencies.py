from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Dict, Any

from services.auth.cognito_service import cognito_service

# This line magically enables the "Authorize" padlock in Swagger UI!
# It tells Swagger that authentication is handled by sending form-data to /auth/token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Dependency to secure endpoints.
    Extracts the Bearer token, validates it securely with AWS Cognito, and returns user data.
    """
    user_data = cognito_service.get_user(access_token=token)
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Store the raw token in the dict so we can use it for logout / change-password if needed
    user_data['access_token'] = token
    return user_data

def get_optional_user(token: str = Depends(OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False))) -> Dict[str, Any]:
    """
    For endpoints where authentication is optional.
    """
    if not token:
        return None
    return cognito_service.get_user(access_token=token)
