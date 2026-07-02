from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any
from sqlalchemy.orm import Session

from common.database import get_db
from services.auth.schemas import (
    RegisterIn, RegisterOut, LoginIn, VerifyIn, VerifyEmailIn, ResendCodeIn, RefreshIn,
    ForgotPasswordIn, ResetPasswordIn, ChangePasswordIn, UpdateProfileIn,
    TokenOut, UserOut, MessageOut, SettingsIn, SettingsOut, format_phone
)
from services.auth.auth_service import auth_service
from common.auth_dependencies import get_current_user
from common.enums import UserRole

router = APIRouter(prefix="/auth", tags=["2. Authentication"])

# ==========================================
# PUBLIC ENDPOINTS
# ==========================================

@router.post("/register", response_model=RegisterOut, summary="Register Treasurer")
async def register(payload: RegisterIn, db: Session = Depends(get_db)):
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
async def verify(payload: VerifyIn, db: Session = Depends(get_db)):
    auth_service.verify_account(db=db, username=payload.identifier, code=payload.code)
    return MessageOut(message="Account successfully verified. You can now log in.")

@router.post("/resend-code", response_model=MessageOut, summary="Resend Registration Code - Public")
async def resend_code(payload: ResendCodeIn, db: Session = Depends(get_db)):
    details = auth_service.resend_confirmation_code(db=db, username=payload.identifier)
    medium = details.get('DeliveryMedium', 'your contact method')
    destination = details.get('Destination', '')
    return MessageOut(message=f"Verification code resent successfully to {medium} ({destination}).")

@router.post("/login", response_model=TokenOut, summary="Login (JSON payload)")
async def login(payload: LoginIn, db: Session = Depends(get_db)):
    """Standard JSON login endpoint for frontend convenience."""
    auth_result = auth_service.login(db=db, username=payload.identifier, password=payload.password)
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        refresh_token=auth_result.get('RefreshToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600)
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

@router.post("/refresh", response_model=TokenOut, summary="Refresh Token")
async def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    auth_result = auth_service.refresh_token(db=db, refresh_token=payload.refresh_token)
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600)
    )

@router.post("/forgot-password", response_model=MessageOut, summary="Request Password Reset")
async def forgot_password(payload: ForgotPasswordIn, db: Session = Depends(get_db)):
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
async def logout(current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    """Logs out globally from all devices using the current token."""
    auth_service.logout(db=db, access_token=current_user['access_token'])
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
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Returns the profile of the currently authenticated user."""
    return UserOut(
        user_id=current_user.get('sub', ''),
        email=current_user.get('email', ''),
        first_name=current_user.get('given_name', ''),
        last_name=current_user.get('family_name', ''),
        phone_number=current_user.get('phone_number', ''),
        email_verified=current_user.get('email_verified') == 'true',
        phone_number_verified=current_user.get('phone_number_verified') == 'true',
        role=current_user.get('role', UserRole.TREASURER.value)
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
    user = db.query(User).filter(User.user_id == current_user.get('sub')).first()
    return SettingsOut(allow_ai_training=user.allow_ai_training if user else True)

@router.post("/settings", response_model=MessageOut, summary="Update User Settings")
async def update_settings(payload: SettingsIn, current_user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    from models.users import User
    user = db.query(User).filter(User.user_id == current_user.get('sub')).first()
    if user:
        user.allow_ai_training = payload.allow_ai_training
        db.commit()
    return MessageOut(message="Settings updated successfully.")
