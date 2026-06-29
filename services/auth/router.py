from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any

from services.auth.schemas import (
    RegisterIn, RegisterOut, LoginIn, VerifyIn, VerifyEmailIn, VerifyPhoneIn, ResendCodeIn, RefreshIn,
    ForgotPasswordIn, ResetPasswordIn, ChangePasswordIn, UpdateProfileIn,
    TokenOut, UserOut, MessageOut, SettingsIn, SettingsOut
)
from services.auth.cognito_service import cognito_service
from common.auth_dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["2. Authentication"])

# ==========================================
# PUBLIC ENDPOINTS
# ==========================================

@router.post("/register", response_model=RegisterOut, summary="Register Treasurer")
async def register(payload: RegisterIn):
    user_sub = cognito_service.register(
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone_number=payload.phone_number
    )
    return RegisterOut(message="User registered. Please check email/WhatsApp for verification code.", user_id=user_sub)

@router.post("/verify", response_model=MessageOut, summary="Verify Phone / Email")
async def verify(payload: VerifyIn):
    cognito_service.verify_account(email=payload.email, code=payload.code)
    # The Cognito PostConfirmation hook will automatically sync the verified user to Postgres!
    return MessageOut(message="Account successfully verified. You can now log in.")

@router.post("/resend-code", response_model=MessageOut, summary="Resend Verification Code")
async def resend_code(payload: ResendCodeIn):
    details = cognito_service.resend_confirmation_code(email=payload.email)
    medium = details.get('DeliveryMedium', 'your contact method')
    destination = details.get('Destination', '')
    return MessageOut(message=f"Verification code resent successfully to {medium} ({destination}).")

@router.post("/login", response_model=TokenOut, summary="Login (JSON payload)")
async def login(payload: LoginIn):
    """Standard JSON login endpoint for frontend convenience."""
    auth_result = cognito_service.login(email=payload.email, password=payload.password)
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        refresh_token=auth_result.get('RefreshToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600)
    )

@router.post("/token", response_model=TokenOut, include_in_schema=False)
async def login_for_swagger(form_data: OAuth2PasswordRequestForm = Depends()):
    """Hidden endpoint exclusively for Swagger UI Authorize button (expects form-data)."""
    auth_result = cognito_service.login(email=form_data.username, password=form_data.password)
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        refresh_token=auth_result.get('RefreshToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600)
    )

@router.post("/refresh", response_model=TokenOut, summary="Refresh Token")
async def refresh(payload: RefreshIn):
    auth_result = cognito_service.refresh_token(refresh_token=payload.refresh_token)
    return TokenOut(
        access_token=auth_result.get('AccessToken'),
        id_token=auth_result.get('IdToken'),
        expires_in=auth_result.get('ExpiresIn', 3600)
    )

@router.post("/forgot-password", response_model=MessageOut, summary="Request Password Reset")
async def forgot_password(payload: ForgotPasswordIn):
    cognito_service.forgot_password(email=payload.email)
    return MessageOut(message="Password reset code sent to your email/phone.")

@router.post("/reset-password", response_model=MessageOut, summary="Reset Password")
async def reset_password(payload: ResetPasswordIn):
    cognito_service.reset_password(email=payload.email, code=payload.code, new_password=payload.new_password)
    return MessageOut(message="Password successfully reset. You can now log in.")

# ==========================================
# PROTECTED ENDPOINTS (Requires valid Token)
# ==========================================

@router.post("/logout", response_model=MessageOut, summary="Logout")
async def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Logs out globally from all devices using the current token."""
    cognito_service.logout(access_token=current_user['access_token'])
    return MessageOut(message="Logged out successfully.")

@router.post("/change-password", response_model=MessageOut, summary="Change Password")
async def change_password(payload: ChangePasswordIn, current_user: Dict[str, Any] = Depends(get_current_user)):
    cognito_service.change_password(
        access_token=current_user['access_token'],
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
        phone_number_verified=current_user.get('phone_number_verified') == 'true'
    )

@router.patch("/me", response_model=MessageOut, summary="Update Profile")
async def update_profile(payload: UpdateProfileIn, current_user: Dict[str, Any] = Depends(get_current_user)):
    updates = []
    if payload.first_name: updates.append({'Name': 'given_name', 'Value': payload.first_name})
    if payload.last_name: updates.append({'Name': 'family_name', 'Value': payload.last_name})
    if payload.phone_number: updates.append({'Name': 'phone_number', 'Value': payload.phone_number})
    
    if updates:
        cognito_service.update_profile(access_token=current_user['access_token'], updates=updates)
    
    return MessageOut(message="Profile updated successfully.")

@router.post("/verify-email/request", summary="Request Email Verification Code")
async def request_email_verification(current_user: dict = Depends(get_current_user)):
    try:
        import boto3
        import os
        client = boto3.client('cognito-idp')
        pool_id = os.environ.get('COGNITO_USER_POOL_ID')
        
        # Diagnostic check to see if CustomEmailSender is actually attached!
        pool_info = client.describe_user_pool(UserPoolId=pool_id)['UserPool']
        lambda_config = pool_info.get('LambdaConfig', {})
        
        cognito_service.request_email_verification(access_token=current_user['access_token'])
        
        return {
            "message": "Email verification code sent successfully.",
            "diagnostic_lambda_config": lambda_config
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/verify-email/confirm", response_model=MessageOut, summary="Confirm Email Verification")
async def confirm_email_verification(payload: VerifyEmailIn, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Submits the 6-digit email verification code."""
    cognito_service.confirm_email_verification(access_token=current_user['access_token'], code=payload.code)
    return MessageOut(message="Email successfully verified.")

@router.post("/verify-phone/request", response_model=MessageOut, summary="Request Phone Verification Code")
async def request_phone_verification(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Triggers Cognito to send a 6-digit verification code to the user's phone."""
    if current_user.get('phone_number_verified') == 'true':
        raise HTTPException(status_code=400, detail="Phone number is already verified.")
    
    cognito_service.request_phone_verification(access_token=current_user['access_token'])
    return MessageOut(message="Phone verification code sent successfully.")

@router.post("/verify-phone/confirm", response_model=MessageOut, summary="Confirm Phone Verification")
async def confirm_phone_verification(payload: VerifyPhoneIn, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Submits the 6-digit phone verification code."""
    cognito_service.confirm_phone_verification(access_token=current_user['access_token'], code=payload.code)
    return MessageOut(message="Phone number successfully verified.")

@router.get("/settings", response_model=SettingsOut, summary="Get User Settings")
async def get_settings(current_user: Dict[str, Any] = Depends(get_current_user)):
    # Local database logic
    from common.database import SessionLocal
    from models.users import User
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == current_user.get('sub')).first()
        return SettingsOut(allow_ai_training=user.allow_ai_training if user else True)
    finally:
        db.close()

@router.post("/settings", response_model=MessageOut, summary="Update User Settings")
async def update_settings(payload: SettingsIn, current_user: Dict[str, Any] = Depends(get_current_user)):
    # Local database logic
    from common.database import SessionLocal
    from models.users import User
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == current_user.get('sub')).first()
        if user:
            user.allow_ai_training = payload.allow_ai_training
            db.commit()
        return MessageOut(message="Settings updated successfully.")
    finally:
        db.close()
