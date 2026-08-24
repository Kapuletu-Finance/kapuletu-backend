import os
import json
import logging
import time
import random
import datetime
import urllib.request
import urllib.error
import traceback
from typing import Dict, Any, Optional

import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
import africastalking
from sqlalchemy.orm import Session
from sqlalchemy import or_

from models.users import User
from models.otp import OTP
from models.token_blacklist import TokenBlacklist
from common.config import get_config
from common.utils import parse_uuid
from services.audit.service import AuditService
from services.notifications.service import create_notification

logger = logging.getLogger(__name__)
config = get_config()

# Initialize Passlib for bcrypt password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Initialize Africa's Talking for SMS Fallback
africastalking.initialize(username=config.AT_USERNAME, api_key=config.AT_API_KEY)
sms = africastalking.SMS


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: datetime.timedelta = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta if expires_delta else datetime.timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm="HS256")

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm="HS256")

def decode_token(token: str):
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


class AuthService:
    
    def _generate_otp(self) -> str:
        return str(random.randint(100000, 999999))
        
    def _save_otp(self, db: Session, user_id, identifier: str, purpose: str) -> str:
        # Delete existing OTPs for this purpose and identifier
        db.query(OTP).filter(OTP.user_id ==parse_uuid(parse_uuid(user_id)), OTP.purpose == purpose).delete()
        
        code = self._generate_otp()
        otp_entry = OTP(
            user_id=user_id,
            identifier=identifier,
            code=code,
            purpose=purpose,
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
        )
        db.add(otp_entry)
        db.commit()
        
        # DEV REQUIREMENT: Log OTP to terminal
        logger.info(f"====== OTP GENERATED ======")
        logger.info(f"Identifier: {identifier}")
        logger.info(f"Code: {code}")
        logger.info(f"Purpose: {purpose}")
        logger.info(f"===========================")
        
        return code

    def _send_whatsapp_with_fallback(self, phone_number: str, code: str):
        """Attempts Meta API first. If it fails, falls back to Africa's Talking SMS."""
        
        # --- Diagnostic Logging (Masked for Security) ---
        logger.info("====== API CREDENTIALS STATUS ======")
        logger.info(f"META_ACCESS_TOKEN: {'[SET]' if config.META_ACCESS_TOKEN and config.META_ACCESS_TOKEN.strip() else '[MISSING]'}")
        logger.info(f"META_PHONE_NUMBER_ID: {'[SET]' if config.META_PHONE_NUMBER_ID and config.META_PHONE_NUMBER_ID.strip() else '[MISSING]'}")
        logger.info(f"AT_USERNAME: {config.AT_USERNAME}")
        logger.info(f"AT_API_KEY: {'[SET]' if config.AT_API_KEY and config.AT_API_KEY.strip() else '[MISSING]'}")
        logger.info(f"AT_SENDER_ID: {'[SET]' if config.AT_SENDER_ID and config.AT_SENDER_ID.strip() else '[MISSING]'}")
        logger.info("====================================")
        
        if config.META_ACCESS_TOKEN and config.META_ACCESS_TOKEN.strip() and config.META_PHONE_NUMBER_ID and config.META_PHONE_NUMBER_ID.strip():
            try:
                logger.info(f"Attempting WhatsApp send to {phone_number}...")
                url = f"https://graph.facebook.com/v19.0/{config.META_PHONE_NUMBER_ID}/messages"
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": phone_number.replace("+", ""),
                    "type": "template",
                    "template": {
                        "name": "kapuletu_auth_otp",
                        "language": {"code": "en"},
                        "components": [
                            {
                                "type": "body",
                                "parameters": [{"type": "text", "text": str(code)}]
                            },
                            {
                                "type": "button",
                                "sub_type": "url",
                                "index": "0",
                                "parameters": [{"type": "text", "text": str(code)}]
                            }
                        ]
                    }
                }
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(url, data=data, method='POST')
                req.add_header('Authorization', f"Bearer {config.META_ACCESS_TOKEN}")
                req.add_header('Content-Type', 'application/json')
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) KapuLetuApp/1.0')
                
                with urllib.request.urlopen(req) as response:
                    logger.info(f"SUCCESS: WhatsApp code sent to {phone_number}")
                    return # Exit function on success
            except Exception as e:
                error_body = ""
                if isinstance(e, urllib.error.HTTPError):
                    try:
                        error_body = e.read().decode('utf-8')
                    except Exception:
                        pass
                logger.error(f"WhatsApp delivery failed: {str(e)} | Response: {error_body}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                logger.error("Triggering SMS Fallback...")
        else:
            logger.warning("Missing Meta Credentials. Falling back to SMS directly.")

        # --- SMS Fallback via Africa's Talking ---
        try:
            logger.info(f"Attempting SMS via Africa's Talking to {phone_number}...")
            message = f"KapuLetu: Your verification code is {code}. It expires in 10 minutes."
            
            # send(message, recipients, sender_id=...)
            if config.AT_SENDER_ID and config.AT_SENDER_ID.strip():
                response = sms.send(message, [phone_number], sender_id=config.AT_SENDER_ID)
            else:
                response = sms.send(message, [phone_number])
                
            logger.info(f"SMS Fallback successful: {response}")
        except Exception as e:
            logger.error(f"CRITICAL: Both WhatsApp and SMS failed for {phone_number}: {str(e)}")
            logger.error(f"AT SMS Traceback: {traceback.format_exc()}")

    def _send_resend_email(self, to_email: str, subject: str, code: str, action_text: str, name: str):
        resend_api_key = os.environ.get('RESEND_API_KEY')
        if not resend_api_key:
            logger.warning("Missing RESEND_API_KEY, skipping email.")
            return

        html_body = f"""
        <html>
        <body style="font-family: 'Inter', sans-serif; background-color: #f4f7f9; padding: 40px; margin: 0;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #e1e8ed;">
                <h1 style="color: #0a2540; text-align: center;">KapuLetu</h1>
                <p>Hello {name},</p>
                <p>To {action_text}, please use the following secure verification code:</p>
                <div style="background-color: #f8fafd; border: 1px dashed #cbd5e0; border-radius: 8px; padding: 20px; text-align: center; margin: 30px 0;">
                    <span style="font-family: 'Courier New', monospace; font-size: 32px; font-weight: bold; color: #0056b3; letter-spacing: 5px;">{code}</span>
                </div>
                <p style="font-size: 14px; color: #718096;">This code will expire in 10 minutes.</p>
            </div>
        </body>
        </html>
        """
        
        url = "https://api.resend.com/emails"
        payload = {
            "from": "KapuLetu <no-reply@kapuletu.co.ke>",
            "to": [to_email],
            "subject": subject,
            "html": html_body
        }
        data = json.dumps(payload).encode('utf-8')
        
        try:
            req = urllib.request.Request(url, data=data, method='POST')
            req.add_header('Authorization', f"Bearer {resend_api_key}")
            req.add_header('Content-Type', 'application/json')
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) KapuLetuApp/1.0')
            urllib.request.urlopen(req)
            logger.info(f"SUCCESS: Email sent to {to_email}")
        except Exception as e:
            error_body = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    error_body = e.read().decode('utf-8')
                except Exception:
                    pass
            logger.error(f"ERROR: Email delivery failed: {str(e)} | Response: {error_body}")
            logger.error(f"Email Traceback: {traceback.format_exc()}")

    # ------------------
    # AUTH ENDPOINTS
    # ------------------

    def register(self, db: Session, email: str, password: str, first_name: str, last_name: str, phone_number: str) -> str:
        # Check existing
        if db.query(User).filter(User.phone_number == phone_number).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This phone number is already registered.")
            
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already registered.")
            
        hashed_pw = get_password_hash(password)
        
        new_user = User(
            email=email,
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            hashed_password=hashed_pw
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Issue Registration OTP to Phone Number (per user's flow)
        code = self._save_otp(db, new_user.user_id, new_user.phone_number, "registration")
        self._send_whatsapp_with_fallback(new_user.phone_number, code)
        
        # Give the user a 21-day Trial Subscription
        from models.subscription import Plan, Subscription
        pro_plan = db.query(Plan).filter(Plan.name == "Professional").first()
        if not pro_plan:
            pro_plan = db.query(Plan).filter(Plan.name == "Free").first()
            
        if pro_plan:
            trial_sub = Subscription(
                user_id=new_user.user_id,
                plan_id=pro_plan.plan_id,
                status="active",
                start_date=datetime.datetime.utcnow(),
                end_date=datetime.datetime.utcnow() + datetime.timedelta(days=21),
                is_auto_renew=False
            )
            db.add(trial_sub)
            db.commit()
        
        create_notification(
            db=db,
            user_id=str(new_user.user_id),
            title=f"Welcome to KapuLetu, {first_name}!",
            message="Your account has been created. Please complete the verification process.",
            type="account_created"
        )
        
        return str(new_user.user_id)

    def _get_user_by_identifier(self, db: Session, identifier: str) -> User:
        user = db.query(User).filter(or_(User.email == identifier, User.phone_number == identifier)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password.")
        return user

    def login(self, db: Session, username: str, password: str) -> Dict[str, Any]:
        user = self._get_user_by_identifier(db, username)
        
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password.")
            
        access_token = create_access_token({"sub": str(user.user_id), "role": user.role})
        refresh_token = create_refresh_token({"sub": str(user.user_id), "role": user.role})
        
        AuditService(db).log_action(
            actor_id=str(user.user_id),
            action="USER_LOGIN",
            entity_type="USER",
            entity_id=str(user.user_id),
            details={"message": "You successfully logged in."}
        )
        
        return {
            "AccessToken": access_token,
            "RefreshToken": refresh_token,
            "IdToken": access_token, # Simplified, using access token as id token
            "ExpiresIn": 3600
        }

    def verify_account(self, db: Session, username: str, code: str):
        user = db.query(User).filter(or_(User.email == username, User.phone_number == username)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        otp = db.query(OTP).filter(
            OTP.user_id == parse_uuid(user.user_id), 
            OTP.purpose == "registration",
            OTP.code == code
        ).first()
        
        if not otp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")
            
        if otp.expires_at < datetime.datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired. Please request a new one.")
            
        user.phone_number_verified = True
        db.delete(otp)
        db.commit()
        
        AuditService(db).log_action(
            actor_id=str(user.user_id),
            action="ACCOUNT_VERIFIED",
            entity_type="USER",
            entity_id=str(user.user_id)
        )
        
        create_notification(
            db=db,
            user_id=str(user.user_id),
            title="Account Verified Successfully",
            message="Your account has been fully verified. You can now create campaigns and manage funds.",
            type="account_verified"
        )
        
        # Fire the post-confirmation welcome messages!
        self._send_welcome_messages(user)

    def _send_welcome_messages(self, user: User):
        """Replaces the old Cognito post_confirmation hook logic."""
        dashboard_url = config.FRONTEND_URL.rstrip('/')
        
        # 1. WhatsApp Welcome Template
        if config.META_ACCESS_TOKEN and config.META_PHONE_NUMBER_ID and user.phone_number:
            try:
                url = f"https://graph.facebook.com/v19.0/{config.META_PHONE_NUMBER_ID}/messages"
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": user.phone_number.replace("+", ""),
                    "type": "template",
                    "template": {
                        "name": "kapuletu_welcome",
                        "language": {"code": "en"},
                        "components": [
                            {
                                "type": "body",
                                "parameters": [{"type": "text", "text": user.first_name}]
                            }
                        ]
                    }
                }
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(url, data=data, method='POST')
                req.add_header('Authorization', f"Bearer {config.META_ACCESS_TOKEN}")
                req.add_header('Content-Type', 'application/json')
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) KapuLetuApp/1.0')
                urllib.request.urlopen(req)
                logger.info("SUCCESS: WhatsApp kapuletu_welcome message sent.")
            except Exception as e:
                error_body = ""
                if isinstance(e, urllib.error.HTTPError):
                    try:
                        error_body = e.read().decode('utf-8')
                    except Exception:
                        pass
                logger.error(f"Failed to send WhatsApp welcome message: {str(e)} | Response: {error_body}")
                logger.error(f"Traceback: {traceback.format_exc()}")

        # 2. Premium Email Welcome
        support_email = os.environ.get('SUPPORT_EMAIL', 'support@kapuletu.co.ke')
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; margin: 0; padding: 0; background-color: #f1f5f9; }}
                .wrapper {{ padding: 40px 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 48px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); }}
                .header {{ border-bottom: 2px solid #f1f5f9; padding-bottom: 24px; margin-bottom: 32px; text-align: center; }}
                .header h1 {{ margin: 0; color: #0f172a; font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }}
                .header p {{ margin: 8px 0 0; color: #64748b; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }}
                .content h2 {{ font-size: 22px; color: #0f172a; margin-top: 0; font-weight: 600; }}
                .content p {{ font-size: 16px; color: #334155; margin-bottom: 24px; }}
                .value-prop {{ background: linear-gradient(145deg, #f8fafc, #f1f5f9); padding: 28px; border-radius: 8px; margin: 32px 0; border: 1px solid #e2e8f0; }}
                .value-prop h3 {{ margin: 0 0 16px; color: #0f172a; font-size: 16px; font-weight: 600; }}
                .feature-list {{ padding-left: 0; list-style: none; margin: 0; }}
                .feature-list li {{ margin-bottom: 12px; font-size: 15px; color: #475569; position: relative; padding-left: 24px; }}
                .feature-list li:before {{ content: "✓"; position: absolute; left: 0; color: #2563eb; font-weight: bold; }}
                .button-container {{ text-align: center; margin: 40px 0; }}
                .button {{ background-color: #2563eb; color: #ffffff !important; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px; display: inline-block; transition: background-color 0.2s; box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2); }}
                .button:hover {{ background-color: #1d4ed8; }}
                .footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid #e2e8f0; font-size: 13px; color: #94a3b8; text-align: center; }}
                .footer strong {{ color: #64748b; }}
                .legal {{ margin-top: 16px; font-size: 11px; color: #cbd5e1; }}
            </style>
        </head>
        <body>
            <div class="wrapper">
                <div class="container">
                    <div class="header">
                        <h1>KapuLetu</h1>
                        <p>Community Financial Management</p>
                    </div>
                    <div class="content">
                        <h2>Welcome to KapuLetu, {user.first_name}.</h2>
                        <p>Your account is verified and ready to go. You can now easily track contributions, manage your campaigns, and generate official reports.</p>
                        
                        <p>To begin managing your community's finances, please log in to your dashboard and invite your members.</p>
                        
                        <div class="button-container">
                            <a href="{dashboard_url}" class="button">Access Dashboard</a>
                        </div>
                        
                        <p>Thank you for joining us!</p>
                    </div>
                    <div class="footer">
                        <p>If you require support, please reach out to our team at <strong>{support_email}</strong>.</p>
                        <p>&copy; 2026 KapuLetu. All rights reserved.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Use Resend directly via urllib to avoid extra dependencies, matching the rest of auth_service
        resend_api_key = os.environ.get('RESEND_API_KEY')
        if resend_api_key and user.email:
            url = "https://api.resend.com/emails"
            payload = {
                "from": "KapuLetu <no-reply@kapuletu.co.ke>",
                "to": [user.email],
                "subject": "Welcome to KapuLetu! Your account is ready.",
                "html": html_body
            }
            try:
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method='POST')
                req.add_header('Authorization', f"Bearer {resend_api_key}")
                req.add_header('Content-Type', 'application/json')
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) KapuLetuApp/1.0')
                urllib.request.urlopen(req)
                logger.info("SUCCESS: Premium Welcome Email sent via Resend.")
            except Exception as e:
                error_body = ""
                if isinstance(e, urllib.error.HTTPError):
                    try:
                        error_body = e.read().decode('utf-8')
                    except Exception:
                        pass
                logger.error(f"Failed to send Premium Welcome Email: {str(e)} | Response: {error_body}")
                logger.error(f"Traceback: {traceback.format_exc()}")

    def resend_confirmation_code(self, db: Session, username: str):
        user = db.query(User).filter(or_(User.email == username, User.phone_number == username)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        code = self._save_otp(db, user.user_id, user.phone_number, "registration")
        self._send_whatsapp_with_fallback(user.phone_number, code)
        return {"Destination": user.phone_number, "DeliveryMedium": "SMS/WhatsApp"}

    def refresh_token(self, db: Session, refresh_token: str) -> Dict[str, Any]:
        payload = decode_token(refresh_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
            
        user = db.query(User).filter(User.user_id ==parse_uuid(parse_uuid(user_id))).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            
        new_access = create_access_token({"sub": str(user.user_id)})
        return {
            "AccessToken": new_access,
            "IdToken": new_access,
            "ExpiresIn": 3600
        }

    def forgot_password(self, db: Session, username: str):
        user = self._get_user_by_identifier(db, username)
        
        # Send to wherever the user specified (email or phone)
        # If username matches email, send email. If it matches phone, send phone.
        code = self._save_otp(db, user.user_id, username, "password_reset")
        
        if "@" in username:
            self._send_resend_email(username, "Reset Your Password", code, "reset your password", user.first_name)
        else:
            self._send_whatsapp_with_fallback(username, code)

    def reset_password(self, db: Session, username: str, code: str, new_password: str):
        user = self._get_user_by_identifier(db, username)
        
        otp = db.query(OTP).filter(
            OTP.user_id == parse_uuid(user.user_id), 
            OTP.purpose == "password_reset",
            OTP.code == code
        ).first()
        
        if not otp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")
        if otp.expires_at < datetime.datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expired.")
            
        user.hashed_password = get_password_hash(new_password)
        db.delete(otp)
        db.commit()

        AuditService(db).log_action(
            actor_id=str(user.user_id),
            action="PASSWORD_RESET",
            entity_type="USER",
            entity_id=str(user.user_id)
        )
        
        create_notification(
            db=db,
            user_id=str(user.user_id),
            title="Password reset successful",
            message="Your password has been successfully reset. You can use your new password when logging in.",
            type="security_alert"
        )

    def change_password(self, db: Session, user_id: str, old_password: str, new_password: str):
        user = db.query(User).filter(User.user_id ==parse_uuid(parse_uuid(user_id))).first()
        if not user or not verify_password(old_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect old password.")
            
        user.hashed_password = get_password_hash(new_password)
        db.commit()

        AuditService(db).log_action(
            actor_id=user_id,
            action="PASSWORD_CHANGED",
            entity_type="USER",
            entity_id=user_id
        )

    def update_profile(self, db: Session, user_id: str, updates: dict):
        user = db.query(User).filter(User.user_id ==parse_uuid(parse_uuid(user_id))).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        for key, value in updates.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        db.commit()

        AuditService(db).log_action(
            actor_id=user_id,
            action="PROFILE_UPDATED",
            entity_type="USER",
            entity_id=user_id,
            details=updates
        )

    def request_email_verification(self, db: Session, user_id: str):
        user = db.query(User).filter(User.user_id ==parse_uuid(parse_uuid(user_id))).first()
        code = self._save_otp(db, user.user_id, user.email, "verify_email")
        self._send_resend_email(user.email, "Verify your Email", code, "verify your email", user.first_name)

    def confirm_email_verification(self, db: Session, user_id: str, code: str):
        otp = db.query(OTP).filter(
            OTP.user_id ==parse_uuid(parse_uuid(user_id)), 
            OTP.purpose == "verify_email",
            OTP.code == code
        ).first()
        if not otp or otp.expires_at < datetime.datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code.")
            
        user = db.query(User).filter(User.user_id ==parse_uuid(parse_uuid(user_id))).first()
        user.email_verified = True
        db.delete(otp)
        db.commit()

    def logout(self, db: Session, access_token: str, user_id: str) -> None:
        """
        Logout the user by blacklisting the active access token.
        """
        if access_token:
            if not db.query(TokenBlacklist).filter(TokenBlacklist.token == access_token).first():
                blacklist_entry = TokenBlacklist(token=access_token, user_id=user_id)
                db.add(blacklist_entry)
                db.commit()
                
            AuditService(db).log_action(
                actor_id=user_id,
                action="USER_LOGOUT",
                entity_type="USER",
                entity_id=user_id
            )

auth_service = AuthService()
