# KapuLetu Authentication & Verification Flow

This document outlines the standard user journey for authentication, from initial registration through to full account verification (Phone and Email) in the KapuLetu system.

---

## Phase 1: Registration & Phone Verification (Public Flow)

This phase occurs entirely on the public-facing side of the application. The user **does not** need a JWT Bearer token to access these endpoints. The primary goal here is to establish the account and verify the user's mobile device.

### 1. Account Creation
* **Endpoint:** `POST /auth/register`
* **Payload:** `{ email, password, first_name, last_name, phone_number }`
* **Action:** The system creates the user record in the database. An OTP is instantly generated (purpose: `registration`) and dispatched to the provided `phone_number` via WhatsApp (or SMS Fallback).
* **State:** Account exists, but `phone_number_verified` is `False`. The user cannot log in yet.

### 2. Confirm Phone Number
* **Endpoint:** `POST /auth/verify`
* **Payload:** `{ identifier: "+254700...", code: "123456" }`
* **Action:** The user enters the 6-digit code they received on their phone. The system validates the code against the database.
* **State:** `phone_number_verified` becomes `True`. The user is now fully registered and permitted to log in.

*(Optional)* **Resend Code**
* **Endpoint:** `POST /auth/resend-code`
* **Action:** If the user did not receive the initial WhatsApp/SMS message, this endpoint generates a new code and attempts delivery again.

---

## Phase 2: Application Access (Login)

Once the phone number is verified, the user is authorized to enter the secure application dashboard.

### 1. Login
* **Endpoint:** `POST /auth/login`
* **Payload:** `{ identifier: "treasurer@example.com" OR "+254700...", password: "..." }`
* **Action:** The system checks the identifier against both registered emails and phone numbers. It then verifies credentials and ensures `phone_number_verified` is `True`. 
* **Response:** Returns a standard JWT payload containing `AccessToken` and `RefreshToken`.

*(Note: For testing in Swagger UI, you can use the `Authorize` button which triggers the internal `POST /auth/token` endpoint).*

---

## Phase 3: Dashboard & Email Verification (Protected Flow)

This phase occurs inside the secure application. The frontend must attach the JWT Bearer token (`Authorization: Bearer <token>`) to all requests.

### 1. Request Email Verification
* **Endpoint:** `POST /auth/verify-email/request`
* **Headers:** `Authorization: Bearer <AccessToken>`
* **Action:** The system extracts the user ID from the token, generates a 6-digit code (purpose: `verify_email`), and emails it to the user's registered email address.

### 2. Confirm Email
* **Endpoint:** `POST /auth/verify-email/confirm`
* **Headers:** `Authorization: Bearer <AccessToken>`
* **Payload:** `{ code: "123456" }`
* **Action:** The system validates the code.
* **State:** `email_verified` becomes `True`. The user's profile is now 100% verified.

---

## Additional Flows

### Password Reset (Public)
1. **Request:** `POST /auth/forgot-password` 
   * **Payload:** `{ identifier: "treasurer@example.com" OR "+254700..." }`
   * **Action:** Dynamically routes an OTP to either the email or the phone depending on what the user typed as their identifier.
2. **Reset:** `POST /auth/reset-password` 
   * **Payload:** `{ identifier, code, new_password }`
   * **Action:** Validates the OTP against the provided identifier (email or phone) and updates the password.

### Profile Management (Protected)
* **View Profile:** `GET /auth/me` (Returns current user details and verification statuses).
* **Update Profile:** `PATCH /auth/me` (Allows changing name and phone number).
* **Change Password:** `POST /auth/change-password` (Requires current password and new password).
* **Logout:** `POST /auth/logout` (Client-side token invalidation).
