# KapuLetu Frontend Authentication Integration Guide

Welcome to the KapuLetu Authentication API! This document provides a comprehensive guide for frontend engineers to integrate the secure AWS Cognito-backed authentication system into the KapuLetu web and mobile clients.

## Core Concepts

1. **Email as Username:** The system uses the user's `email` as their unique identifier for login and account recovery.
2. **JWT Tokens:** All protected routes require an `Authorization: Bearer <access_token>` header.
3. **Automated Syncing:** Once an account is verified, the backend automatically provisions their local Postgres database profile. The frontend never needs to manually sync users.

---

##  1. The Onboarding Flow

### Step 1.1: Registration
The user fills out the registration form.

**Endpoint:** `POST /auth/register`
**Security:** Public

**Request Payload:**
```json
{
  "email": "user@example.com",
  "password": "StrongPassword123!",
  "first_name": "Jane",
  "last_name": "Doe",
  "phone_number": "+254700000000"
}
```

**Success Response (200 OK):**
```json
{
  "message": "User registered. Please check email/WhatsApp for verification code.",
  "user_id": "uuid-string"
}
```
*Note: Cognito will automatically text or email a 6-digit code to the user based on delivery algorithms. The user only needs to provide this code.*

### Step 1.2: Account Verification
The user inputs the 6-digit code they received.

**Endpoint:** `POST /auth/verify`
**Security:** Public

**Request Payload:**
```json
{
  "email": "user@example.com",
  "code": "123456"
}
```

**Success Response (200 OK):**
```json
{
  "message": "Account successfully verified. You can now log in."
}
```
*(Behind the scenes: The backend automatically sends a gorgeous HTML welcome email to the user!)*

### Step 1.3: (Optional) Resend Code
If the user didn't receive the initial verification code, provide a "Resend Code" button.

**Endpoint:** `POST /auth/resend-code`
**Security:** Public

**Request Payload:**
```json
{
  "email": "user@example.com"
}
```

**Success Response (200 OK):**
```json
{
  "message": "Verification code resent successfully to SMS (+********0000)."
}
```

---

##  2. Authentication & Session Management

### Step 2.1: Login
Authenticate the user and retrieve their JWT tokens.

**Endpoint:** `POST /auth/login`
**Security:** Public

**Request Payload:**
```json
{
  "email": "user@example.com",
  "password": "StrongPassword123!"
}
```

**Success Response (200 OK):**
```json
{
  "access_token": "eyJraWQi...",
  "refresh_token": "eyJjdHki...",
  "id_token": "eyJraWQi...",
  "expires_in": 3600
}
```
*Frontend Action: Securely store `access_token` and `refresh_token` (e.g., Secure HttpOnly Cookies or Encrypted Local Storage).*

### Step 2.2: Using Protected Routes
For any protected API endpoint, attach the `access_token` in the HTTP headers:
```http
Authorization: Bearer {access_token}
```

### Step 2.3: Refresh Token
When the `access_token` expires (after 3600 seconds/1 hour), silently fetch a new one without forcing the user to log in again.

**Endpoint:** `POST /auth/refresh`
**Security:** Public

**Request Payload:**
```json
{
  "refresh_token": "eyJjdHki..."
}
```

**Success Response (200 OK):**
```json
{
  "access_token": "eyJraWQi...",
  "id_token": "eyJraWQi...",
  "expires_in": 3600
}
```

### Step 2.4: Logout
Invalidates the token globally across all devices.

**Endpoint:** `POST /auth/logout`
**Security:** Protected (Requires Bearer Token)

**Success Response (200 OK):**
```json
{
  "message": "Logged out successfully."
}
```

---

## 3. Profile Management

### Step 3.1: Get Current User
Fetch the logged-in user's profile details. Useful for populating the navigation bar.

**Endpoint:** `GET /auth/me`
**Security:** Protected (Requires Bearer Token)

**Success Response (200 OK):**
```json
{
  "user_id": "uuid-string",
  "email": "user@example.com",
  "first_name": "Jane",
  "last_name": "Doe",
  "phone_number": "+254700000000",
  "email_verified": true,
  "phone_number_verified": false
}
```

### Step 3.2: Update Profile
Update user attributes. Any field omitted will be ignored.

**Endpoint:** `PATCH /auth/me`
**Security:** Protected (Requires Bearer Token)

**Request Payload (All fields optional):**
```json
{
  "first_name": "Janet",
  "last_name": "Doe",
  "phone_number": "+254711111111"
}
```

> [!WARNING]
> **Important Cognito Behavior:** If a user updates their `phone_number` or `email`, AWS Cognito immediately marks that attribute as **unverified** and automatically fires off a new verification code to the new destination.

---

##  4. Explicit Attribute Verification
If a user updates their email/phone or logs in with an unverified attribute, you can explicitly force a verification flow.

### Phone Verification Flow
**Endpoint 1: Request Code** -> `POST /auth/verify-phone/request`
- **Security:** Protected
- **Payload:** None.
- **Action:** Triggers an SMS containing a 6-digit code.

**Endpoint 2: Confirm Code** -> `POST /auth/verify-phone/confirm`
- **Security:** Protected
- **Payload:** `{"code": "123456"}`
- **Action:** Marks the phone number as fully verified.

### Email Verification Flow
**Endpoint 1: Request Code** -> `POST /auth/verify-email/request`
- **Security:** Protected
- **Payload:** None.
- **Action:** Triggers an Email containing a 6-digit code.

**Endpoint 2: Confirm Code** -> `POST /auth/verify-email/confirm`
- **Security:** Protected
- **Payload:** `{"code": "123456"}`
- **Action:** Marks the email address as fully verified.

---

## 🔑 5. Password Recovery Flow

### Step 5.1: Forgot Password
User forgot their password and requests a reset code.

**Endpoint:** `POST /auth/forgot-password`
**Security:** Public

**Request Payload:**
```json
{
  "email": "user@example.com"
}
```

### Step 5.2: Reset Password
User submits the code they received along with their new password.

**Endpoint:** `POST /auth/reset-password`
**Security:** Public

**Request Payload:**
```json
{
  "email": "user@example.com",
  "code": "123456",
  "new_password": "NewStrongPassword123!"
}
```

---

##  Standard Error Responses (400 / 401 / 403)
If the frontend sends invalid data (e.g., wrong password, expired token, weak password), the backend returns a clean JSON error response that you can directly display to the user.

**Example 400 Bad Request:**
```json
{
  "detail": "Incorrect username or password."
}
```

**Example 401 Unauthorized (Expired Token):**
```json
{
  "detail": "Could not validate credentials"
}
```
