# Module: Security & Identity

## 1. Overview
This module ensures the platform remains secure and that the identities of its users are verified and protected. It manages the authentication infrastructure and security-related preferences.

## 2. Key Functionalities

### 2.1 Multi-Step Verification (MFA) Management
Hardening account access for both users and admins.
- **MFA Configuration**: Setting the default MFA method (SMS, Email, or Authenticator App).
- **Enforcement Policies**: Requiring MFA for all administrative roles and high-value treasurer actions (e.g., bulk exports).
- **Recovery Workflows**: Managing the process for resetting MFA when a user loses their device.

### 2.2 Identity Verification Workflows
Managing the "Trust" layer of the platform.
- **Verification Status**: Tracking the status of email and phone confirmations.
- **Re-Verification**: Triggering a new verification request if suspicious activity is detected.
- **Multi-Step Onboarding**: Ensuring all steps of the treasurer's registration (Confirm Email -> Verify Phone -> Setup MFA) are completed successfully.

### 2.3 User Preferences & Privacy Settings
Admins manage the "Global Defaults" for user settings.
- **Notification Preferences**: Configuring default channels (WhatsApp vs. SMS vs. Email).
- **UI/UX Themes**: Managing platform-wide theme settings.
- **Privacy Controls**: Setting defaults for data sharing and visibility within the platform.

## 3. Data Captured for Auditing
- **Action**: (e.g., `MFA_RESET`, `IDENTITY_VERIFIED`).
- **Entity ID**: User ID.
- **Payload**: Security events (e.g., `{"method": "SMS", "action": "challenged"}`).
- **Success/Failure**: Recording failed authentication attempts to detect brute-force attacks.

## 4. Administrative Security
- **Role-Based Access Control (RBAC)**: Detailed mapping of admin roles to specific permissions.
- **Session Management**: Admins can view and terminate active sessions for any user if security is compromised.
- **Security Challenges**: Forcing a password change or MFA challenge on next login.

---
**Next Steps**: For the forensic tracking of these security events, see the **[Audit & Forensics](audit-forensics.md)** module.
