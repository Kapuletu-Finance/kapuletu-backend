# KapuLetu User Settings Module Specification

This document provides a comprehensive technical and functional specification for the User Settings Module. It outlines the deep parameters, customization options, and strict workflows required to give users full autonomy over their experience while maintaining security and data integrity.

## 1. Overview
The settings module is divided into six distinct categories:
1. **Transaction & Workflow Automation**
2. **Privacy & AI Model Training**
3. **Profile & Identity**
4. **Reporting & Notifications**
5. **Security & Authentication**
6. **Display & Preferences**

---

## 2. Settings Categories & Deep Parameters

### 2.1 Transaction & Workflow Automation
Empowers users to automate the parsing and assignment of incoming transactions to minimize manual entry.

* **`default_group_id`** (UUID | Null): The ID of the Chama/Group where transactions without explicit group markers will be routed by default.
* **`default_campaign_id`** (UUID | Null): The ID of the specific campaign (within the default group) where unallocated funds should be placed.
* **`auto_approve_transactions`** (Boolean): 
    * `false` (Default): All parsed transactions go to the "Pending/Review" inbox.
    * `true`: High-confidence parsed transactions bypass the review inbox and are instantly committed to the ledger.
* **`auto_approve_confidence_threshold`** (Float, 0.0 - 1.0): If `auto_approve_transactions` is true, this dictates the AI confidence score required to auto-approve. (e.g., `0.95` means 95% certainty).

### 2.2 Privacy & AI Data Usage
Controls how user data is interacted with by KapuLetu's underlying parsing engines.

* **`allow_data_for_ai_training`** (Boolean): 
    * `true` (Default): Anonymized transaction structures can be used to improve the KapuLetu AI parser.
    * `false`: Opt-out of data collection. Strict data masking applied; data is only used for immediate parsing and then dropped from training pipelines.

### 2.3 Profile & Identity
Manages the user's core identity. 

* **`first_name`** (String): User's given name.
* **`last_name`** (String): User's family name.
* **`email_address`** (String): User's email address. Requires an email verification loop if changed.
* **`phone_number`** (String): Core identifier and primary authentication mechanism.
    > [!WARNING]
    > **Strict Phone Number Change Workflow:**
    > Changing a phone number cannot be done directly via a simple PATCH request. It requires a multi-step verification process to prevent account takeover and ledger corruption.
    > 1. **Initiation**: User requests to change phone number to `New_Number`.
    > 2. **Uniqueness Check**: System verifies `New_Number` is not attached to any other active account.
    > 3. **Primary Verification**: OTP is sent to the **OLD** phone number to authorize the change request.
    > 4. **Secondary Verification**: OTP is sent to the **NEW** phone number to verify possession.
    > 5. **Execution**: Only upon double-validation is the phone number updated in the database and Identity Provider (Cognito/Firebase).

### 2.4 Reporting & Notifications
Allows users to configure how and when they receive financial summaries.

* **`auto_receive_reports`** (Boolean): Enable or disable automated reporting.
* **`report_frequency`** (Enum): Options: `DAILY`, `WEEKLY`, `MONTHLY`, `POST_MEETING`.
* **`report_delivery_channels`** (Array of Enums): Where to send the reports. Options: `WHATSAPP`, `EMAIL`, `IN_APP`.
* **`include_zero_activity_reports`** (Boolean): If true, sends a report even if no contributions occurred during the period.
* **`report_format`** (Enum): Options: `PDF_SUMMARY`, `EXCEL_DETAILED`, `TEXT_SUMMARY` (Optimized for WhatsApp).

### 2.5 Security & Authentication
Secures the treasurer's account.

* **`two_step_verification_enabled`** (Boolean): Enable/Disable 2FA.
* **`two_step_method`** (Enum): 
    * `SMS_OTP`: Sends a code via SMS on every login from a new device.
    * `AUTHENTICATOR_APP`: Time-based One-Time Password (TOTP) via Google/Microsoft Authenticator.
    * `WHATSAPP_OTP`: Sends login codes via WhatsApp.
* **`session_timeout_minutes`** (Integer): Auto-logout after inactivity (e.g., 15, 30, 60 minutes).

### 2.6 Display & Preferences
UI/UX customizations.

* **`theme_mode`** (Enum): `LIGHT`, `DARK`, `SYSTEM_DEFAULT`.
* **`currency_display_format`** (Enum): E.g., `1,234.56` vs `1 234,56`.
* **`language`** (Enum): `en-US`, `sw-KE` (Swahili), etc.

---

## 3. Proposed Database JSON Schema (Settings Object)

To allow for flexible growth without altering database schemas continuously, it is highly recommended to store the non-relational settings in a `JSONB` column named `preferences` on the `users` table, while keeping critical items (like phone number and 2FA status) as primary relational columns.

```json
{
  "automation": {
    "default_group_id": "uuid-string-here",
    "default_campaign_id": "uuid-string-here",
    "auto_approve": false,
    "confidence_threshold": 0.90
  },
  "privacy": {
    "allow_ai_training": true
  },
  "reporting": {
    "auto_receive": true,
    "frequency": "WEEKLY",
    "channels": ["WHATSAPP", "EMAIL"],
    "format": "TEXT_SUMMARY"
  },
  "display": {
    "theme": "DARK",
    "language": "en-US"
  }
}
```

## 4. API Endpoints Required

To support this module, the following endpoints should be implemented in `services/auth/router.py` or a dedicated `services/settings/router.py`:

* `GET /settings` - Fetch all user preferences.
* `PATCH /settings` - Update standard preferences (theme, reports, automation).
* `POST /settings/phone/initiate` - Step 1 of strict phone change (generates OTP to old phone).
* `POST /settings/phone/verify-old` - Step 2 (validates OTP from old phone, triggers OTP to new phone).
* `POST /settings/phone/confirm-new` - Step 3 (validates OTP from new phone, executes change).
* `POST /settings/security/2fa/enable` - Setup TOTP or SMS 2FA.
* `POST /settings/security/2fa/disable` - Requires current password/OTP to disable.
