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
from services.notifications.providers.resend_client import ResendClient

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

        try:
            import jinja2
            import datetime
            from common.config import get_config
            env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))
            template = env.get_template('email_base.html')
            
            body_content = f"""
            <p>Hello {name},</p>
            <p>To {action_text}, please use the following secure verification code:</p>
            <div style="background-color: #f8fafd; border: 1px dashed #cbd5e0; border-radius: 8px; padding: 20px; text-align: center; margin: 30px 0;">
                <span style="font-family: 'Courier New', monospace; font-size: 32px; font-weight: bold; color: #097255; letter-spacing: 5px;">{code}</span>
            </div>
            <p style="font-size: 14px; color: #718096;">This code will expire in 10 minutes.</p>
            """
            
            html_body = template.render(
                subject=subject,
                frontend_url=get_config().FRONTEND_URL.rstrip('/'),
                body=body_content,
                current_year=datetime.datetime.utcnow().year
            )
        except Exception as e:
            logger.error(f"Failed to load Jinja2 template: {e}")
            html_body = f"<p>Your verification code is: <b>{code}</b></p>"
        
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

    def register(self, db: Session, email: str, password: str, first_name: str, last_name: str, phone_number: str, marketing_consent: bool = False) -> str:
        # Check existing
        if db.query(User).filter(User.phone_number == phone_number, User.deleted_at.is_(None)).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This phone number is already registered.")
            
        if db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already registered.")
            
        hashed_pw = get_password_hash(password)
        
        from common.utils import generate_slug
        import random
        base_slug = generate_slug(f"{first_name} {last_name}") if first_name else "user"
        slug = base_slug
        while db.query(User).filter(User.slug == slug).first():
            slug = f"{base_slug}-{random.randint(1000, 9999)}"

        # Check Waitlist Logic
        from common.system_config_service import get_system_config
        from models.waitlist_whitelist import WaitlistWhitelist
        
        is_waitlisted = False
        waitlist_mode = get_system_config(db, "WAITLIST_MODE_ENABLED", default=False)
        if str(waitlist_mode).lower() == "true":
            # Check if phone is whitelisted (phone is the primary identifier for signup/OTP)
            whitelisted = db.query(WaitlistWhitelist).filter(
                WaitlistWhitelist.phone_number == phone_number
            ).first()
            if not whitelisted:
                is_waitlisted = True

        new_user = User(
            email=email,
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            slug=slug,
            hashed_password=hashed_pw,
            marketing_consent=marketing_consent,
            is_waitlisted=is_waitlisted
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Issue Registration OTP to Phone Number (per user's flow)
        code = self._save_otp(db, new_user.user_id, new_user.phone_number, "registration")
        import threading
        threading.Thread(target=self._send_whatsapp_with_fallback, args=(new_user.phone_number, code)).start()
        
        # Give the user an indefinite Basic Subscription
        from models.subscription import Plan, Subscription
        basic_plan = db.query(Plan).filter(Plan.name == "Basic").first()
            
        if basic_plan:
            sub = Subscription(
                user_id=new_user.user_id,
                plan_id=basic_plan.plan_id,
                status="active",
                start_date=datetime.datetime.utcnow(),
                is_auto_renew=False
            )
            db.add(sub)
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
            
        from common.system_config_service import get_system_config
        force_2fa = get_system_config(db, "force_2fa", default="none")
        session_timeout = int(get_system_config(db, "session_timeout_minutes", default=60))
        
        # Determine if 2FA is required based on global settings or user preference
        requires_2fa = getattr(user, 'two_factor_enabled', False)
        if force_2fa == "all":
            requires_2fa = True
        elif force_2fa == "admins" and getattr(user, "role", "") == "admin":
            requires_2fa = True

        if requires_2fa:
            # Generate 2FA token
            two_fa_token = create_access_token({"sub": str(user.user_id), "purpose": "2fa"}, expires_delta=datetime.timedelta(minutes=10))
            
            # Send OTP based on preferred channel
            channel = getattr(user, 'two_factor_channel', 'whatsapp')
            identifier = user.email if channel == 'email' else user.phone_number
            code = self._save_otp(db, user.user_id, identifier, "2fa_login")
            
            if channel == 'email':
                self._send_resend_email(user.email, "Your 2FA Verification Code", code, "verify your login", user.first_name)
            else:
                self._send_whatsapp_with_fallback(user.phone_number, code)
                
            return {
                "Requires2FA": True,
                "2FAToken": two_fa_token,
                "SessionTimeoutMinutes": session_timeout # pass down to caller if needed
            }
            
        access_token = create_access_token({"sub": str(user.user_id), "role": user.role}, expires_delta=datetime.timedelta(minutes=session_timeout))
        refresh_token = create_refresh_token({"sub": str(user.user_id), "role": user.role})
        
        AuditService(db).log_action(
            actor_id=str(user.user_id),
            action="USER_LOGIN",
            entity_type="USER",
            entity_id=str(user.user_id),
            details={"message": "You successfully logged in."}
        )
        
        return {
            "Requires2FA": False,
            "AccessToken": access_token,
            "RefreshToken": refresh_token,
            "IdToken": access_token, # Simplified, using access token as id token
            "ExpiresIn": session_timeout * 60,
            "Role": user.role,
            "IsWaitlisted": user.is_waitlisted
        }

    def resend_2fa(self, db: Session, two_fa_token: str) -> Dict[str, Any]:
        payload = decode_token(two_fa_token)
        if payload.get("purpose") != "2fa":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token purpose")
            
        user_id = payload.get("sub")
        user = db.query(User).filter(User.user_id == parse_uuid(user_id)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        channel = getattr(user, 'two_factor_channel', 'whatsapp')
        identifier = user.email if channel == 'email' else user.phone_number
        
        # Delete existing OTP if any
        db.query(OTP).filter(
            OTP.user_id == parse_uuid(user.user_id), 
            OTP.purpose == "2fa_login"
        ).delete()
        db.commit()

        code = self._save_otp(db, user.user_id, identifier, "2fa_login")
        
        if channel == 'email':
            self._send_resend_email(user.email, "Your 2FA Verification Code", code, "verify your login", user.first_name)
        else:
            self._send_whatsapp_with_fallback(user.phone_number, code)
            
        return {"Destination": identifier, "DeliveryMedium": channel}

    def verify_2fa(self, db: Session, two_fa_token: str, code: str) -> Dict[str, Any]:
        payload = decode_token(two_fa_token)
        if payload.get("purpose") != "2fa":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token purpose")
            
        user_id = payload.get("sub")
        user = db.query(User).filter(User.user_id == parse_uuid(user_id)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        otp = db.query(OTP).filter(
            OTP.user_id == parse_uuid(user.user_id), 
            OTP.purpose == "2fa_login",
            OTP.code == code
        ).first()
        
        if not otp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")
            
        if otp.expires_at < datetime.datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired.")
            
        db.delete(otp)
        db.commit()
        
        from common.system_config_service import get_system_config
        session_timeout = int(get_system_config(db, "session_timeout_minutes", default=60))
        
        access_token = create_access_token({"sub": str(user.user_id), "role": user.role}, expires_delta=datetime.timedelta(minutes=session_timeout))
        refresh_token = create_refresh_token({"sub": str(user.user_id), "role": user.role})
        
        AuditService(db).log_action(
            actor_id=str(user.user_id),
            action="USER_LOGIN",
            entity_type="USER",
            entity_id=str(user.user_id),
            details={"message": "You successfully logged in with 2FA."}
        )
        
        return {
            "Requires2FA": False,
            "AccessToken": access_token,
            "RefreshToken": refresh_token,
            "IdToken": access_token,
            "ExpiresIn": session_timeout * 60,
            "Role": user.role,
            "IsWaitlisted": user.is_waitlisted
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
                template_name = "kapuletu_waitlist_welcome" if user.is_waitlisted else "kapuletu_welcome"
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": user.phone_number.replace("+", ""),
                    "type": "template",
                    "template": {
                        "name": template_name,
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
        
        if user.is_waitlisted:
            email_subject = "Welcome to KapuLetu! You're on the Waitlist"
            email_title = f"Welcome to KapuLetu, {user.first_name}."
            email_body = """
            <p>You have successfully created your account. We are currently in a controlled testing phase to ensure the best experience, so we have added you to our waitlist.</p>
            <p>We will notify you the moment your workspace is ready. In the meantime, feel free to check out our resources.</p>
            """
            button_html = f'<a href="{dashboard_url}/waitlist" class="button">View Status</a>'
        else:
            email_subject = "Welcome to KapuLetu! Your account is ready."
            email_title = f"Welcome to KapuLetu, {user.first_name}."
            email_body = """
            <p>Your account is verified and ready to go. You can now easily track contributions, manage your campaigns, and generate official reports.</p>
            <p>To begin managing your community's finances, please log in to your dashboard and invite your members.</p>
            """
            button_html = f'<a href="{dashboard_url}" class="button">Access Dashboard</a>'

        try:
            import jinja2
            import datetime
            from common.config import get_config
            env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))
            template = env.get_template('email_base.html')
            
            body_content = f"""
            <h2>{email_title}</h2>
            {email_body}
            <div style="text-align: center; margin: 40px 0;">
                {button_html}
            </div>
            """
            
            html_body = template.render(
                subject=email_subject,
                frontend_url=get_config().FRONTEND_URL.rstrip('/'),
                body=body_content,
                current_year=datetime.datetime.utcnow().year
            )
        except Exception as e:
            logger.error(f"Failed to load Jinja2 template for welcome email: {e}")
            html_body = email_body + button_html
        
        # Use Resend directly via urllib to avoid extra dependencies, matching the rest of auth_service
        resend_api_key = os.environ.get('RESEND_API_KEY')
        if resend_api_key and user.email:
            url = "https://api.resend.com/emails"
            payload = {
                "from": "KapuLetu <no-reply@kapuletu.co.ke>",
                "to": [user.email],
                "subject": email_subject,
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

        create_notification(
            db=db,
            user_id=str(user.user_id),
            title="Security Alert: Password Changed",
            message="Your password was recently changed successfully. If you did not make this change, please contact support immediately.",
            type="security_alert"
        )
        
        if user.email:
            try:
                resend_client = ResendClient()
                resend_client.send_email(
                    to_email=user.email,
                    subject="Kapuletu Security: Password Changed",
                    html_body=(
                        "<h3>Security Alert</h3>"
                        "<p>Your Kapuletu account password was recently changed.</p>"
                        "<p>If you made this change, no further action is required.</p>"
                        "<p><strong>If you did not make this change, please contact support immediately.</strong></p>"
                    )
                )
            except Exception as e:
                logger.error(f"Failed to send password change email to {user.email}: {e}")

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
