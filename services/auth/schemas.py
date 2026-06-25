from typing import Optional
from pydantic import BaseModel, EmailStr, Field

# --- INPUT SCHEMAS ---

class RegisterIn(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "treasurer@example.com"})
    password: str = Field(..., min_length=8, json_schema_extra={"example": "SecurePass123!"})
    first_name: str = Field(..., min_length=1, json_schema_extra={"example": "Joseph"})
    last_name: str = Field(..., min_length=1, json_schema_extra={"example": "Amuyunzu"})
    phone_number: str = Field(..., json_schema_extra={"example": "+254700123456"})

class LoginIn(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "treasurer@example.com"})
    password: str = Field(..., json_schema_extra={"example": "SecurePass123!"})

class VerifyIn(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "treasurer@example.com"})
    code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})

class VerifyEmailIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})

class VerifyPhoneIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})

class ResendCodeIn(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "treasurer@example.com"})

class RefreshIn(BaseModel):
    refresh_token: str = Field(..., json_schema_extra={"example": "eyJhbG..."})

class ForgotPasswordIn(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "treasurer@example.com"})

class ResetPasswordIn(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "treasurer@example.com"})
    code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})
    new_password: str = Field(..., min_length=8, json_schema_extra={"example": "NewSecurePass456!"})

class ChangePasswordIn(BaseModel):
    old_password: str = Field(..., json_schema_extra={"example": "SecurePass123!"})
    new_password: str = Field(..., min_length=8, json_schema_extra={"example": "NewSecurePass456!"})

class UpdateProfileIn(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, json_schema_extra={"example": "Joseph"})
    last_name: Optional[str] = Field(None, min_length=1, json_schema_extra={"example": "Amuyunzu"})
    phone_number: Optional[str] = Field(None, json_schema_extra={"example": "+254700123456"})

class SettingsIn(BaseModel):
    allow_ai_training: bool = Field(..., json_schema_extra={"example": True})

# --- OUTPUT SCHEMAS ---

class MessageOut(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Operation successful."})

class TokenOut(BaseModel):
    access_token: str = Field(..., json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})
    refresh_token: Optional[str] = Field(None, json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})
    id_token: Optional[str] = Field(None, json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})
    token_type: str = Field("bearer", json_schema_extra={"example": "bearer"})
    expires_in: int = Field(3600, json_schema_extra={"example": 3600})

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

class SettingsOut(BaseModel):
    allow_ai_training: bool = Field(..., json_schema_extra={"example": True})
