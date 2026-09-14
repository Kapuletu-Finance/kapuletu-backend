# KapuLetu: Authentication Module Audit & User Flow

This document provides a deep-dive audit of the Identity and Authentication architecture for KapuLetu, mapping the interaction between AWS Cognito and our internal PostgreSQL database.

## 1. Module Audit Summary

The Authentication module is built on a **Hybrid-Cloud Identity Model**, using AWS Cognito as the primary OIDC provider and PostgreSQL as the secondary user profile storage.

### A. Endpoint Registry (`services/auth/api_handler.py`)
| Endpoint | Method | Role | Backend Interaction |
| :--- | :--- | :--- | :--- |
| `/auth/register` | `POST` | User Enrollment | `SignUp` in Cognito |
| `/auth/verify` | `POST` | Account Confirmation | `ConfirmSignUp` in Cognito |
| `/auth/login` | `POST` | Credential Exchange | `InitiateAuth` (returns JWTs) |
| `/auth/refresh` | `POST` | Session Extension | `REFRESH_TOKEN_AUTH` flow |
| `/auth/me` | `GET` | Profile Retrieval | Fetches from Cognito + RDS |
| `/auth/change-password` | `POST` | Security Update | Authenticated `ChangePassword` |

### B. Trigger Integrity
- **Post-Confirmation Hook**: Successfully synchronizes every verified user into the PostgreSQL `users` table. This ensures that foreign key relationships in the finance and campaign modules never break.
- **Custom Message Hook**: Seamlessly replaces standard AWS notification logic with professional HTML emails and WhatsApp delivery (Twilio).

---

## 2. The Detailed User Journey (Step-by-Step)

### Step 1: Registration
1.  **User Action**: Enters Email, First Name, Last Name, and Phone Number.
2.  **Process**: `auth/register` is called. 
3.  **Result**: A "User Entity" is created in Cognito in a `UNCONFIRMED` state.

### Step 2: Verification & Custom Messaging
1.  **Trigger**: Cognito detects a new signup and triggers `custom_sender.py`.
2.  **System Action**: 
    - A professional HTML email is sent with a 6-digit code.
    - A **WhatsApp Message** is sent to the user's phone via Twilio for convenience.
3.  **User Action**: Enters the code into the UI. Calls `auth/verify`.
4.  **Result**: User status in Cognito moves to `CONFIRMED`.

### Step 3: Database Synchronization (Seamless RDS Integration)
1.  **Trigger**: The moment the user is confirmed, `handler.py (post_confirmation)` is triggered.
2.  **Process**: 
    - The Lambda connects to PostgreSQL.
    - It creates a new `User` record with the `cognito_user_id` as the primary key.
    - It assigns the default role of **Treasurer**.
3.  **Result**: The user is now "known" to the entire backend ecosystem.

### Step 4: Login & JWT Acquisition
1.  **User Action**: Enters credentials. Calls `auth/login`.
2.  **Result**: Cognito returns three tokens:
    - **ID Token**: Contains user claims (email, name).
    - **Access Token**: Used for API calls.
    - **Refresh Token**: Used to stay logged in without re-entering password.

### Step 5: Authenticated Usage
1.  **User Action**: Makes a request (e.g., `POST /finance/checkout`).
2.  **Process**: 
    - The API Gateway Authorizer validates the JWT signature against AWS Cognito's public keys.
    - The `user_id` is extracted from the `sub` claim and passed to the finance handler.
    - The handler uses this `user_id` to query their organization and campaigns in PostgreSQL.

---

## 3. Security Posture Analysis

- **Password Policy**: Enforced by Cognito (Default: 8+ chars, requires symbols/numbers).
- **Session Security**: JWTs are signed (RS256). The backend validates expiration and issuer.
- **Data Privacy**: No passwords are ever stored in our PostgreSQL database; only the Cognito `sub` identifier is kept.
- **Notification Security**: Codes are delivered via secure, encrypted channels (HTTPS to Twilio/SES).

## 4. Verification Verdict

**Status: ✅ Production Ready**
The Auth module is successfully integrated with the RDS-only architecture. The user sync logic is robust, and the communication layer provides a premium experience that builds trust with Treasurers immediately upon signup.
