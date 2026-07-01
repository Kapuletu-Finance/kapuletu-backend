# KapuLetu Authentication & Verification Flow (Frontend Guide)

This document is a comprehensive guide for the frontend engineering team to seamlessly integrate with the KapuLetu Backend Authentication system. 

It covers the strict 3-phase journey every user must take:
1. **Public Registration** (Establishing the account and verifying the mobile device)
2. **Login** (Retrieving JWT tokens)
3. **Protected Dashboard** (Verifying the email address from within the app)

> [!IMPORTANT]
> **The Universal Identifier Field**
> Most authentication endpoints use a single, unified `identifier` field in the payload. The frontend should just pass whatever the user types into a single text box (e.g., `"treasurer@example.com"` OR `"0714703374"`). 
> The backend automatically formats phone numbers into standard E.164 (`+254...`) and dynamically routes OTPs to the correct medium (Email vs WhatsApp/SMS).

---

## Phase 1: Registration & Phone Verification (Public Flow)

This phase occurs entirely on the public-facing side of the application. **No JWT Bearer token is required.**

### 1. Account Creation
The user fills out the sign-up form.

* **Endpoint:** `POST /auth/register`
* **Headers:** `Content-Type: application/json`
* **Payload:**
  ```json
  {
    "email": "treasurer@example.com",
    "password": "SecurePassword123!",
    "first_name": "Joseph",
    "last_name": "Njoroge",
    "phone_number": "0700123456"
  }
  ```
* **Action:** The system creates the user, hashes the password, and instantly dispatches a 6-digit OTP to the provided phone number.
* **Response (200 OK):**
  ```json
  {
    "message": "User registered. Please check email/WhatsApp for verification code.",
    "user_id": "uuid-string"
  }
  ```
> [!WARNING]
> At this stage, `phone_number_verified` is `False`. The user **cannot** log in yet. You must immediately transition them to an OTP entry screen.

### 2. Confirm Registration (Phone Verification)
The user enters the 6-digit code they received on their phone.

* **Endpoint:** `POST /auth/verify`
* **Headers:** `Content-Type: application/json`
* **Payload:**
  ```json
  {
    "identifier": "0700123456", 
    "code": "123456"
  }
  ```
  *(Note: You can pass their email as the identifier here as well, the backend will still check the OTP sent to their phone).*
* **Response (200 OK):**
  ```json
  {
    "message": "Account successfully verified. You can now log in."
  }
  ```
* **State Change:** `phone_number_verified` is now `True`. The user is officially permitted to log in.

### 3. Resend Registration Code (Optional)
If the user did not receive the initial WhatsApp/SMS message, provide a "Resend Code" button that hits this endpoint.

* **Endpoint:** `POST /auth/resend-code`
* **Headers:** `Content-Type: application/json`
* **Payload:**
  ```json
  {
    "identifier": "0700123456"
  }
  ```

---

## Phase 2: Application Access (Login)

### 1. Login
* **Endpoint:** `POST /auth/login`
* **Headers:** `Content-Type: application/json`
* **Payload:**
  ```json
  {
    "identifier": "0700123456", 
    "password": "SecurePassword123!"
  }
  ```
* **Error Handling:** If `phone_number_verified` is still `False`, this will throw an error. The user must complete Phase 1.
* **Response (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "eyJhbGciOi...",
    "id_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 3600
  }
  ```
> [!IMPORTANT]
> The frontend should securely store the `access_token` and attach it as a Header (`Authorization: Bearer <access_token>`) to all subsequent API requests.

---

## Phase 3: Dashboard & Email Verification (Protected Flow)

This phase occurs strictly inside the secure application dashboard. **All endpoints require the JWT Bearer token.**

### 1. Request Email Verification
Provide a button in the UI (e.g., a banner saying "Please verify your email").

* **Endpoint:** `POST /auth/verify-email/request`
* **Headers:** `Authorization: Bearer <access_token>`
* **Payload:** *(None required, the backend extracts the user from the token)*
* **Action:** Generates a 6-digit code and emails it to the user.

### 2. Confirm Email
The user enters the 6-digit code from their email.

* **Endpoint:** `POST /auth/verify-email/confirm`
* **Headers:** `Authorization: Bearer <access_token>`
* **Payload:**
  ```json
  {
    "code": "123456"
  }
  ```
* **State Change:** `email_verified` becomes `True`. The user's profile is now 100% verified.

---

## Additional Flows

### Password Reset (Public)
If the user forgot their password on the login screen.

1. **Request Code:** `POST /auth/forgot-password`
   * **Payload:** `{"identifier": "treasurer@example.com"}`
   * **Action:** Dynamically routes the OTP. If they typed an email, it emails them. If they typed a phone number, it WhatsApps them.
2. **Submit New Password:** `POST /auth/reset-password`
   * **Payload:** 
     ```json
     {
       "identifier": "treasurer@example.com",
       "code": "123456",
       "new_password": "NewSecurePassword456!"
     }
     ```

### Profile Management (Protected)
All require `Authorization: Bearer <access_token>`.

* **View Profile:** `GET /auth/me`
  Returns current user details (names, contact info, and verification boolean statuses `email_verified`, `phone_number_verified`).
* **Update Profile:** `PATCH /auth/me`
  Allows updating `first_name`, `last_name`, and `phone_number`.
* **Change Password:** `POST /auth/change-password`
  Requires `old_password` and `new_password`.
* **Logout:** `POST /auth/logout`
  Invalidates the current session token on the backend.
