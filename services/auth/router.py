from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

from common.database import get_db
from common.utils import parse_uuid
from services.auth.schemas import (
    RegisterIn, RegisterOut, LoginIn, VerifyIn, VerifyEmailIn, ResendCodeIn, Resend2FAIn, RefreshIn,
    ForgotPasswordIn, ResetPasswordIn, ChangePasswordIn, UpdateProfileIn,
    TokenOut, UserOut, MessageOut, SettingsIn, SettingsOut, format_phone
)
from services.auth.auth_service import auth_service
from common.auth_dependencies import get_current_user
from common.enums import UserRole

router = APIRouter(prefix="/auth", tags=["1. Authentication"])

# ==========================================
# PUBLIC ENDPOINTS
# ==========================================

@router.post("/register", response_model=RegisterOut, summary="Register Treasurer")
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterIn, db: Session = Depends(get_db)):
    from common.system_config_service import get_system_config
    
    open_signups = get_system_config(db, "open_signups", default=True)
    # Check if open_signups is explicitly false, or if it's the string "false"
    if open_signups is False or open_signups == "false":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Public registrations are currently closed."
        )

    user_id = auth_service.register(
        db=db,
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone_number=payload.phone_number
    )
    return RegisterOut(message="User registered. Please check email/WhatsApp for verification code.", user_id=user_id)

@router.post("/verify", response_model=MessageOut, summary="Verify Phone (Complete Registration) - Public")
@limiter.limit("5/minute")
async def verify(request: Request, payload: VerifyIn, db: Session = Depends(get_db)):
    auth_service.verify_account(db=db, username=payload.identifier, code=payload.code)
    return MessageOut(message="Account successfully verified. You can now log in.")

@router.post("/resend-code", response_model=MessageOut, summary="Resend Registration Code - Public")
@limiter.limit("3/minute")
async def resend_code(request: Request, payload: ResendCodeIn, db: Session = Depends(get_db)):
    details = auth_service.resend_confirmation_code(db=db, username=payload.identifier)
    medium = details.get('DeliveryMedium', 'your contact method')
    destination = details.get('Destination', '')
    return MessageOut(message=f"Verification code resent successfully to {medium} ({destination}).")

@router.post("/login", response_model=TokenOut, summary="Login (JSON payload)")
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    """Standard JSON login endpoint. Sets HTTP-Only cookies for frontend."""
    from common.config import get_config
    is_secure = not get_config().IS_LOCAL
    
    auth_result = auth_service.login(db=db, username=payload.identifier, password=payload.password)
    
    if auth_result.get('Requires2FA'):
        return TokenOut(
            requires_2fa=True, 
            two_fa_token=auth_result.get('2FAToken'),
            access_token=None,
            refresh_token=None,
            id_token=None
        )
    
    # Set HTTP-Only Cookies
    response.set_cookie(
        key="kapuletu_access_token", 
        value=auth_result.get('AccessToken'), 
        httponly=True, 
        secure=is_secure, 
        samesite='lax', 
        max_age=15 * 60 # 15 minutes
    )
    response.set_cookie(
        key="kapuletu_refresh_token", 
        value=auth_result.get('RefreshToken'), 
        httponly=True, 
        secure=is_secure, 
        samesite='lax', 
        max_age=1 * 24 * 60 * 60 # 1 day
    )
    
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        refresh_token=auth_result.get('RefreshToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600),
        requires_2fa=False
    )

@router.post("/token", response_model=TokenOut, include_in_schema=False)
async def login_for_swagger(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Hidden endpoint exclusively for Swagger UI Authorize button (expects form-data)."""
    formatted_username = format_phone(form_data.username) or form_data.username
    auth_result = auth_service.login(db=db, username=formatted_username, password=form_data.password)
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        refresh_token=auth_result.get('RefreshToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600)
    )

class Verify2FAIn(BaseModel):
    two_fa_token: str = Field(..., json_schema_extra={"example": "eyJhb..."})
    code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})

@router.post("/verify-2fa", response_model=TokenOut, summary="Verify 2FA Code")
@limiter.limit("10/minute")
async def verify_2fa(request: Request, payload: Verify2FAIn, response: Response, db: Session = Depends(get_db)):
    """Verifies the 2FA code and issues the final JWT tokens."""
    from common.config import get_config
    is_secure = not get_config().IS_LOCAL
    
    auth_result = auth_service.verify_2fa(db=db, two_fa_token=payload.two_fa_token, code=payload.code)
    
    # Set HTTP-Only Cookies
    response.set_cookie(
        key="kapuletu_access_token", 
        value=auth_result.get('AccessToken'), 
        httponly=True, 
        secure=is_secure, 
        samesite='lax', 
        max_age=15 * 60 # 15 minutes
    )
    response.set_cookie(
        key="kapuletu_refresh_token", 
        value=auth_result.get('RefreshToken'), 
        httponly=True, 
        secure=is_secure, 
        samesite='lax', 
        max_age=1 * 24 * 60 * 60 # 1 day
    )
    
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        refresh_token=auth_result.get('RefreshToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600),
        requires_2fa=False
    )

@router.post("/resend-2fa", response_model=MessageOut, summary="Resend 2FA Code")
@limiter.limit("3/minute")
async def resend_2fa(request: Request, payload: Resend2FAIn, db: Session = Depends(get_db)):
    """Resends the 2FA code."""
    details = auth_service.resend_2fa(db=db, two_fa_token=payload.two_fa_token)
    medium = details.get('DeliveryMedium', 'your contact method')
    destination = details.get('Destination', '')
    return MessageOut(message=f"2FA code resent successfully via {medium}.")

@router.post("/refresh", response_model=TokenOut, summary="Refresh Token")
async def refresh(request: Request, response: Response, payload: RefreshIn = None, db: Session = Depends(get_db)):
    """Refreshes the access token using the HTTP-Only refresh cookie."""
    # Check cookie first, fallback to JSON payload if provided
    refresh_token = request.cookies.get("kapuletu_refresh_token")
    if not refresh_token and payload:
        refresh_token = payload.refresh_token
        
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
        
    from common.config import get_config
    is_secure = not get_config().IS_LOCAL
    
    auth_result = auth_service.refresh_token(db=db, refresh_token=refresh_token)
    
    # Set new Access Token cookie
    response.set_cookie(
        key="kapuletu_access_token", 
        value=auth_result.get('AccessToken'), 
        httponly=True, 
        secure=is_secure, 
        samesite='lax', 
        max_age=15 * 60
    )
    
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600)
    )

@router.post("/forgot-password", response_model=MessageOut, summary="Request Password Reset")
@limiter.limit("3/minute")
async def forgot_password(request: Request, payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    auth_service.forgot_password(db=db, username=payload.identifier)
    return MessageOut(message="Password reset code sent to your email/phone.")

@router.post("/reset-password", response_model=MessageOut, summary="Reset Password")
async def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    auth_service.reset_password(db=db, username=payload.identifier, code=payload.code, new_password=payload.new_password)
    return MessageOut(message="Password successfully reset. You can now log in.")

# ==========================================
# PROTECTED ENDPOINTS (Requires valid Token)
# ==========================================

@router.post("/logout", response_model=MessageOut, summary="Logout")
async def logout(response: Response, current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    """Logs out by clearing the HTTP-Only cookies."""
    auth_service.logout(db=db, access_token=current_user['access_token'], user_id=current_user['sub'])
    response.delete_cookie("kapuletu_access_token")
    response.delete_cookie("kapuletu_refresh_token")
    return MessageOut(message="Logged out successfully.")

@router.post("/change-password", response_model=MessageOut, summary="Change Password")
async def change_password(payload: ChangePasswordIn, current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    auth_service.change_password(
        db=db,
        user_id=current_user['sub'],
        old_password=payload.old_password,
        new_password=payload.new_password
    )
    return MessageOut(message="Password changed successfully.")

@router.get("/me", response_model=UserOut, summary="Get Current User Profile")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns the profile of the currently authenticated user."""
    from models.users import User
    user = db.query(User).filter(User.user_id == parse_uuid(current_user.get('sub'))).first()
    
    return UserOut(
        user_id=current_user.get('sub', ''),
        email=current_user.get('email', ''),
        first_name=current_user.get('given_name', ''),
        last_name=current_user.get('family_name', ''),
        phone_number=current_user.get('phone_number', ''),
        email_verified=current_user.get('email_verified') == 'true',
        phone_number_verified=current_user.get('phone_number_verified') == 'true',
        role=current_user.get('role', UserRole.TREASURER.value),
        two_factor_enabled=user.two_factor_enabled if user else False,
        two_factor_channel=user.two_factor_channel if user else None
    )

@router.patch("/me", response_model=MessageOut, summary="Update Profile")
async def update_profile(payload: UpdateProfileIn, current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    updates = {}
    if payload.first_name: updates['first_name'] = payload.first_name
    if payload.last_name: updates['last_name'] = payload.last_name
    if payload.phone_number: updates['phone_number'] = payload.phone_number
    
    if updates:
        auth_service.update_profile(db=db, user_id=current_user['sub'], updates=updates)
    
    return MessageOut(message="Profile updated successfully.")

@router.post("/verify-email/request", response_model=MessageOut, summary="Request Email Verification Code")
async def request_email_verification(current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    """Triggers backend to send a 6-digit verification code to the user's email."""
    if current_user.get('email_verified') == 'true':
        raise HTTPException(status_code=400, detail="Email is already verified.")
    
    auth_service.request_email_verification(db=db, user_id=current_user['sub'])
    return MessageOut(message="Email verification code sent successfully.")

@router.post("/verify-email/confirm", response_model=MessageOut, summary="Confirm Email Verification")
async def confirm_email_verification(payload: VerifyEmailIn, current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    """Submits the 6-digit email verification code."""
    auth_service.confirm_email_verification(db=db, user_id=current_user['sub'], code=payload.code)
    return MessageOut(message="Email successfully verified.")


@router.get("/settings", response_model=SettingsOut, summary="Get User Settings")
async def get_settings(current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    from models.users import User
    user = db.query(User).filter(User.user_id ==parse_uuid(parse_uuid(current_user.get('sub')))).first()
    return SettingsOut(
        allow_ai_training=user.allow_ai_training if user else True,
        two_factor_enabled=user.two_factor_enabled if user else False,
        two_factor_channel=user.two_factor_channel if user else None
    )

@router.post("/settings", response_model=MessageOut, summary="Update User Settings")
async def update_settings(payload: SettingsIn, current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    from models.users import User
    user = db.query(User).filter(User.user_id == parse_uuid(current_user.get('sub'))).first()
    if user:
        if payload.allow_ai_training is not None:
            user.allow_ai_training = payload.allow_ai_training
        if payload.two_factor_enabled is not None:
            user.two_factor_enabled = payload.two_factor_enabled
        if payload.two_factor_channel is not None:
            user.two_factor_channel = payload.two_factor_channel
        db.commit()
    return MessageOut(message="Settings updated successfully.")
