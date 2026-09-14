# KapuLetu Authentication Module: Architecture & Flow

This document details the structure, logic, and exact workflows of the KapuLetu backend Authentication module. The module is built natively in **FastAPI**, backed entirely by **AWS Cognito**, and secured using **OAuth2 JWT Bearer tokens**.

---

## 1. Directory Structure & Responsibilities

The authentication logic is fully decoupled from the core application, encapsulated within `services/auth` and `common/auth_dependencies.py`.

```text
kapuletu-backend/
├── common/
│   └── auth_dependencies.py   <-- FastAPI Security (OAuth2) & Token validation
├── services/
│   └── auth/
│       ├── router.py          <-- Native FastAPI Endpoint definitions
│       ├── schemas.py         <-- Strict Pydantic input/output validation
│       ├── cognito_service.py <-- Python Wrapper for boto3 (AWS Cognito)
│       ├── custom_sender.py   <-- AWS Lambda hook (Sends WhatsApp & HTML Emails)
│       └── handler.py         <-- AWS Lambda hook (PostgreSQL User Sync)
```

### Component Breakdown
1. **`router.py`**: The entry point for the frontend. It maps URLs (like `/auth/register`) to Python functions. It relies heavily on `schemas.py` to automatically validate incoming JSON before the code even runs.
2. **`schemas.py`**: Defines the exact shape of data. If an email is improperly formatted, or a password is under 8 characters, Pydantic throws a `422 Unprocessable Entity` immediately.
3. **`cognito_service.py`**: The bridge to AWS. It converts standard Python arguments into raw `boto3` calls, catches ugly AWS errors (like `UserNotFoundException`), and translates them into clean FastAPI `HTTPExceptions`.
4. **`auth_dependencies.py`**: The security gatekeeper. Exposes the `get_current_user` dependency. Any endpoint that includes `Depends(get_current_user)` becomes mathematically impossible to access without a valid JWT token.
5. **AWS Lambda Triggers (`custom_sender` & `handler`)**: Asynchronous scripts that Cognito triggers automatically in the background to handle messaging and database synchronization without blocking the main API.

---

## 2. Security & Swagger UI Integration

The API utilizes the **OAuth2PasswordBearer** standard.
- When the backend starts, FastAPI detects the `auth_dependencies.py` configuration and automatically adds an **"Authorize" padlock** to the Swagger UI (`/docs`).
- The frontend (or you, testing locally) can click the padlock, log in, and Swagger will securely cache the JWT Access Token in the browser.
- Swagger then automatically injects this token into the `Authorization: Bearer <token>` header for all protected endpoints.

---

## 3. The Mandatory "Two-Step" Verification Workflow

To guarantee maximum security and verify user identities across both channels, KapuLetu enforces a strict Two-Step Verification Flow (Phone First, Email Second).

### Step 1: Registration & WhatsApp Verification
1. **Frontend Call**: `POST /auth/register`
   - Payload: Email, Password, First Name, Last Name, Phone Number.
   - Action: The user is created in AWS Cognito with an `UNCONFIRMED` status.
2. **AWS Trigger**: Cognito immediately invokes the `CustomMessage_SignUp` lambda (`custom_sender.py`).
   - Action: The script uses Twilio to send a 6-digit verification code to the user's **WhatsApp/SMS**.
3. **Frontend Call**: `POST /auth/verify`
   - Payload: Email, WhatsApp Code.
   - Action: User submits the WhatsApp code. Cognito changes their status to `CONFIRMED`.
4. **AWS Trigger**: Cognito immediately invokes the `PostConfirmation_ConfirmSignUp` lambda (`handler.py`).
   - Action: The script connects to the PostgreSQL database, creates the official `User` record in the `users` table, and sends a "Welcome" WhatsApp message and Email.

### Step 2: Login & Email Verification
At this point, the user can log in, but their email is still officially unverified.
1. **Frontend Call**: `POST /auth/login`
   - Payload: Email, Password.
   - Return: `access_token` (JWT).
2. **Frontend Check**: The frontend calls `GET /auth/me`. 
   - It sees `phone_number_verified: true` but `email_verified: false`. It prompts the user to verify their email.
3. **Frontend Call**: `POST /auth/verify-email/request` (Protected Endpoint)
   - Action: The backend tells Cognito to generate an email verification code.
4. **AWS Trigger**: Cognito invokes the `CustomMessage_VerifyUserAttribute` lambda (`custom_sender.py`).
   - Action: The script generates the KapuLetu-branded HTML Email Template and sends it via SES.
5. **Frontend Call**: `POST /auth/verify-email/confirm` (Protected Endpoint)
   - Payload: Email Code.
   - Action: The user submits the code. Cognito flips `email_verified` to `true`. The user is now 100% verified.

---

## 4. Endpoint Reference Guide

### Public Endpoints (No Token Required)
- `POST /auth/register` - Creates a new user and triggers WhatsApp verification.
- `POST /auth/verify` - Confirms the user's account using the WhatsApp code.
- `POST /auth/login` - Authenticates user and returns JWT tokens (Access, Id, Refresh).
- `POST /auth/token` - (Hidden) Form-data login endpoint exclusively used by Swagger UI.
- `POST /auth/refresh` - Issues a new access token using a refresh token.
- `POST /auth/forgot-password` - Sends a password reset code to the user.
- `POST /auth/reset-password` - Submits the reset code and new password.

### Protected Endpoints (JWT Token Required)
*These endpoints require the `Authorization: Bearer <token>` header.*
- `GET /auth/me` - Retrieves the current user's profile and verification status directly from Cognito.
- `PATCH /auth/me` - Updates user attributes (First Name, Last Name, Phone).
- `POST /auth/change-password` - Updates the password for a logged-in user.
- `POST /auth/verify-email/request` - Triggers the HTML email containing the verification code.
- `POST /auth/verify-email/confirm` - Validates the email code.
- `POST /auth/logout` - Globally invalidates the current access token.
- `GET /auth/settings` - Retrieves user settings from the PostgreSQL database (e.g., AI Opt-In).
- `POST /auth/settings` - Updates user settings in the PostgreSQL database.

---

## 5. Error Handling Architecture

Instead of returning raw AWS stack traces, the `cognito_service.py` intercepts `ClientError` exceptions and parses the `Error.Code`. 

Examples of translated errors sent to the frontend:
- `NotAuthorizedException` ➔ `401 Unauthorized: Incorrect email or password.`
- `UsernameExistsException` ➔ `409 Conflict: An account with this email already exists.`
- `ExpiredCodeException` ➔ `400 Bad Request: Verification code has expired. Please request a new one.`
- `LimitExceededException` ➔ `429 Too Many Requests: Too many attempts. Please try again later.`

This guarantees the frontend always receives predictable, standard HTTP status codes, making error handling on the UI straightforward and secure.
