# Authentication API & Amazon Cognito Architecture

This document serves as the absolute source of truth for the KapuLetu Authentication API.

**Important Infrastructure Note:** 
The creation of the Amazon Cognito User Pool and App Client is managed securely in the `kapuletu-infra` repository using Terraform. Our backend code acts as a seamless REST API gateway, securely proxying authentication requests natively to Amazon Cognito while keeping your business logic clean.

---

## 1. Authentication Endpoints

The frontend application should communicate strictly with these KapuLetu backend REST endpoints. The backend securely abstracts the AWS SDK logic.

### 1.1. Registration & Verification (Public)

#### `POST /auth/register`
**What it does:** Creates a new user in the system. Triggers an email verification and a custom Twilio WhatsApp verification code.
**Receives Payload:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+254700000000"
}
```
**Gives Response:** `200 OK` 
```json
{
  "message": "User registered. Please verify email/phone.", 
  "sub": "cognito-unique-id"
}
```

#### `POST /auth/verify`
**What it does:** Confirms the user's account using the 6-digit code sent to them. Upon success, the backend automatically triggers the `PostConfirmation` hook to sync the user into the PostgreSQL database and send a welcome email/WhatsApp.
**Receives Payload:**
```json
{
  "email": "user@example.com",
  "code": "123456"
}
```
**Gives Response:** `200 OK` 
```json
{
  "message": "Verification successful."
}
```

### 1.2. Authentication Flow (Public)

#### `POST /auth/login`
**What it does:** Authenticates the user and returns secure JSON Web Tokens (JWTs).
**Receives Payload:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```
**Gives Response:** `200 OK` 
```json
{
  "AccessToken": "eyJraW...",
  "ExpiresIn": 3600,
  "TokenType": "Bearer",
  "RefreshToken": "eyJjdH...",
  "IdToken": "eyJraW..."
}
```

#### `POST /auth/refresh`
**What it does:** Exchanges a long-lived Refresh Token for a fresh Access Token to keep the user seamlessly logged in without prompting for a password.
**Receives Payload:**
```json
{
  "refresh_token": "<Cognito_Refresh_Token>"
}
```
**Gives Response:** `200 OK` containing a new `AccessToken` and `IdToken`.

### 1.3. Profile & Session Management (Protected)

*Note: All endpoints below strictly require the HTTP Header: `Authorization: Bearer <AccessToken>`*

#### `GET /auth/me`
**What it does:** Retrieves the currently authenticated user's profile information securely from Cognito using their token.
**Receives:** Header `Authorization: Bearer <token>`
**Gives Response:** `200 OK` 
```json
{
  "user": {
    "email": "user@example.com", 
    "given_name": "John", 
    "family_name": "Doe", 
    "phone_number": "+254700000000",
    "username": "user-uuid"
  }
}
```

#### `PATCH /auth/me`
**What it does:** Updates the user's profile details.
**Receives Payload:**
```json
{
  "first_name": "Jane",
  "last_name": "Doe",
  "phone_number": "+254700000001"
}
```
**Gives Response:** `200 OK` 
```json
{
  "message": "Profile updated successfully."
}
```

#### `POST /auth/change-password`
**What it does:** Allows a logged-in user to securely change their password.
**Receives Payload:**
```json
{
  "old_password": "OldPassword123!",
  "new_password": "NewStrongPassword123!"
}
```
**Gives Response:** `200 OK` 
```json
{
  "message": "Password changed successfully."
}
```

#### `POST /auth/logout`
**What it does:** Invalidates the user's Access Token globally across all devices.
**Receives:** Header `Authorization: Bearer <token>`
**Gives Response:** `200 OK` 
```json
{
  "message": "Logged out successfully."
}
```

### 1.4. Account Recovery (Public)

#### `POST /auth/forgot-password`
**What it does:** Triggers a password reset flow, sending a 6-digit recovery code to the user's verified contact method.
**Receives Payload:**
```json
{
  "email": "user@example.com"
}
```
**Gives Response:** `200 OK` 
```json
{
  "message": "Password reset code sent."
}
```

#### `POST /auth/reset-password`
**What it does:** Consumes the recovery code to assign a new password to the user.
**Receives Payload:**
```json
{
  "email": "user@example.com",
  "code": "123456",
  "new_password": "NewStrongPassword123!"
}
```
**Gives Response:** `200 OK` 
```json
{
  "message": "Password reset successful."
}
```

---

## 2. Protected Infrastructure & Authorizers

### The API Gateway Firewall
We utilize the **API Gateway Cognito Authorizer** to secure core endpoints (`/approval`, `/reporting`, `/members`, `/campaigns`, and the protected `/auth/*` endpoints). 

When a request hits a protected endpoint:
1. AWS API Gateway intercepts the `Authorization: Bearer` header.
2. It mathematically validates the token against the Terraform-provisioned Cognito User Pool.
3. If valid, the request proceeds to the Python code.
4. If missing or invalid, API Gateway instantly returns `401 Unauthorized`, completely blocking malicious requests before they even trigger your backend logic.
