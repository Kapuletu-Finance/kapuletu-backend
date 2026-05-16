# Module: User Lifecycle & Support Governance

## 1. Overview
In KapuLetu, Treasurers are the primary actors. While they sign up autonomously, the Admin Panel provides the "Escalated Control" necessary to manage their journey, resolve their technical challenges, and ensure they adhere to platform standards.

## 2. Key Functionalities

### 2.1 Treasurer Profile Management
Admins have full visibility into Treasurer profiles to ensure data integrity and provide direct support.
- **Profile View**: Access to personal details, contact information (WhatsApp/SMS), and account history.
- **Escalated Edits**: Ability to update user attributes (e.g., corrected email or phone) when the user is locked out or unable to perform the update.
- **Role Management**: Escalating users from `treasurer` to `admin` or `super_admin` when necessary.

### 2.2 Activity Monitoring & Platform Visibility
Tracking "what users do" and managing their resources is essential for support and platform health.
- **Group Oversight**: Admins can view all community groups owned by a Treasurer, including member counts and activity levels.
- **Campaign Monitoring**: Visibility into the specific fundraising goals (Campaigns) managed by each group.
- **Financial Record Review**: Deep-dive access into the finalized transaction records of any group to assist with reconciliation issues or support requests.
- **Session Tracking**: Monitoring active sessions and login history.
- **Action Feed**: A real-time feed of user actions (e.g., "Group Created", "Campaign Started", "Transaction Approved").

### 2.3 Escalated Support & Account Challenges
Admins act as the final tier of support for account-level issues.
- **Account Verification Overrides**: Manually confirming a user's email or phone if automated verification fails.
- **Password & MFA Resets**: Assisting users who are locked out of their accounts.
- **State Correction**: Resolving "stuck" states (e.g., clearing a pending transaction that was malformed).

### 2.4 Account Status Governance
Managing the lifecycle of the account itself.
- **Suspension**: Temporarily disabling accounts for security or administrative reasons.
- **Reactivation**: Restoring accounts after resolution of issues.
- **Deactivation/Archival**: Managing the end-of-life process for user accounts.

## 3. Data Captured for Auditing
Every administrative interaction with a user account must be logged with:
- **Action**: (e.g., `USER_SUSPENDED`, `PROFILE_UPDATED`).
- **Entity ID**: The `user_id` of the treasurer.
- **Payload**: The specific changes made (e.g., `{"old_status": "active", "new_status": "suspended"}`).
- **Reason**: A mandatory field for the admin to provide context for the change.

## 4. User Support Interface
The Admin UI should provide a "Support Mode" where an admin can view the platform "through the eyes of the treasurer" (Read-only impersonation) to understand exactly what the user is seeing when they report an issue.

---
**Next Steps**: For communication with users during support events, see the **[CRM & Engagement](crm-engagement.md)** module.
