from typing import Optional
from pydantic import BaseModel, EmailStr, Field, model_validator, field_validator
import re
from common.enums import UserRole

def format_phone(v: Optional[str]) -> Optional[str]:
    if not v:
        return None if v == "" else v
    v = re.sub(r'[\s\-]', '', v)
    if not v:
        return None
    if re.match(r'^0[17]\d{8}$', v):
        return f"+254{v[1:]}"
    if re.match(r'^254[17]\d{8}$', v):
        return f"+{v}"
    return v

# --- INPUT SCHEMAS ---

class IdentifierBase(BaseModel):
    identifier: str = Field(..., json_schema_extra={"example": "treasurer@example.com (or +254700000000)"})

    @field_validator('identifier', mode='before')
    @classmethod
    def validate_identifier(cls, v):
        if not v:
            raise ValueError('identifier cannot be empty')
            
        v_stripped = re.sub(r'[\s\-]', '', str(v))
        if re.match(r'^0[17]\d{8}$', v_stripped):
            return f"+254{v_stripped[1:]}"
        if re.match(r'^254[17]\d{8}$', v_stripped):
            return f"+{v_stripped}"
            
        return v

class RegisterIn(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "treasurer@example.com"})
    password: str = Field(..., min_length=8, json_schema_extra={"example": "SecurePass123!"})
    first_name: str = Field(..., min_length=1, json_schema_extra={"example": "Joseph"})
    last_name: str = Field(..., min_length=1, json_schema_extra={"example": "Amuyunzu"})
    phone_number: str = Field(..., json_schema_extra={"example": "+254700123456"})
    marketing_consent: bool = Field(False, json_schema_extra={"example": False})
    invite_token: Optional[str] = Field(None, json_schema_extra={"example": "abc123xyz"})

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v):
        return format_phone(v)

class LoginIn(IdentifierBase):
    password: str = Field(..., json_schema_extra={"example": "SecurePass123!"})

class VerifyIn(IdentifierBase):
    code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})

class VerifyEmailIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})


class ResendCodeIn(IdentifierBase):
    pass

class Resend2FAIn(BaseModel):
    two_fa_token: str = Field(..., json_schema_extra={"example": "eyJhb..."})

class RefreshIn(BaseModel):
    refresh_token: str = Field(..., json_schema_extra={"example": "eyJhbG..."})

class ForgotPasswordIn(IdentifierBase):
    pass

class ResetPasswordIn(IdentifierBase):
    code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})
    new_password: str = Field(..., min_length=8, json_schema_extra={"example": "NewSecurePass456!"})

class ChangePasswordIn(BaseModel):
    old_password: str = Field(..., json_schema_extra={"example": "SecurePass123!"})
    new_password: str = Field(..., min_length=8, json_schema_extra={"example": "NewSecurePass456!"})

class UpdateProfileIn(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, json_schema_extra={"example": "Joseph"})
    last_name: Optional[str] = Field(None, min_length=1, json_schema_extra={"example": "Amuyunzu"})
    phone_number: Optional[str] = Field(None, json_schema_extra={"example": "+254700123456"})

    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_phone(cls, v):
        return format_phone(v)

class SettingsIn(BaseModel):
    allow_ai_training: Optional[bool] = Field(None, json_schema_extra={"example": True})
    two_factor_enabled: Optional[bool] = Field(None, json_schema_extra={"example": False})
    two_factor_channel: Optional[str] = Field(None, json_schema_extra={"example": "whatsapp"})

# --- OUTPUT SCHEMAS ---

class MessageOut(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Operation successful."})

class TokenOut(BaseModel):
    access_token: Optional[str] = Field(None, json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})
    refresh_token: Optional[str] = Field(None, json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})
    id_token: Optional[str] = Field(None, json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})
    token_type: str = Field("bearer", json_schema_extra={"example": "bearer"})
    expires_in: int = Field(3600, json_schema_extra={"example": 3600})
    requires_2fa: Optional[bool] = Field(None, json_schema_extra={"example": True})
    two_fa_token: Optional[str] = Field(None, json_schema_extra={"example": "eyJhb..."})
    role: Optional[str] = Field(None, json_schema_extra={"example": "treasurer"})
    is_waitlisted: Optional[bool] = Field(None, json_schema_extra={"example": False})

class RegisterOut(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "User registered. Please verify email/phone."})
    user_id: str = Field(..., json_schema_extra={"example": "uuid-string"})

class UserOut(BaseModel):
    user_id: str = Field(..., json_schema_extra={"example": "uuid-string"})
    email: str = Field(..., json_schema_extra={"example": "treasurer@example.com"})
    first_name: str = Field(..., json_schema_extra={"example": "Joseph"})
    last_name: str = Field(..., json_schema_extra={"example": "Amuyunzu"})
    phone_number: str = Field(..., json_schema_extra={"example": "+254700123456"})
    email_verified: bool = Field(..., json_schema_extra={"example": True})
    phone_number_verified: bool = Field(..., json_schema_extra={"example": False})
    role: UserRole = Field(..., json_schema_extra={"example": UserRole.TREASURER})
    two_factor_enabled: bool = Field(False, json_schema_extra={"example": False})
    two_factor_channel: Optional[str] = Field(None, json_schema_extra={"example": "whatsapp"})

class SettingsOut(BaseModel):
    allow_ai_training: bool = Field(..., json_schema_extra={"example": True})
    two_factor_enabled: bool = Field(..., json_schema_extra={"example": False})
    two_factor_channel: Optional[str] = Field(None, json_schema_extra={"example": "whatsapp"})
