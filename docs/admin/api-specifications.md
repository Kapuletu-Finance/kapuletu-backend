# Kapuletu Admin Panel: API Specifications

## 1. Introduction
This document defines the RESTful API endpoints for the KapuLetu Admin Panel. All endpoints listed here require a Bearer token with `admin` or `super_admin` roles.

**Base URL**: `https://api.kapuletu.com/admin/v1`

---

## 2. Platform Overview & Dashboard APIs

### 2.0 Platform Overview Statistics
`GET /admin/v1/overview`
- **Description**: High-level statistical snapshot of the entire platform's health. Used for the Admin Dashboard home screen.
- **Response**: `200 OK`
  ```json
  {
    "total_treasurers": 1250,
    "total_revenue_kes": 450000.0,
    "active_subscriptions": 890,
    "pending_tickets": 12,
    "ai_accuracy_rate": 0.94
  }
  ```

---

## 3. User & Support Governance APIs

### 2.1 List Treasurers
`GET /users/treasurers`
- **Description**: Returns a paginated list of all self-signed-up treasurers.
- **Query Parameters**: `page`, `limit`, `status` (active/suspended), `search` (name/phone).
- **Response**: `200 OK` with `{"users": [...], "total": 100}`.

### 2.2 Get Treasurer Details
`GET /users/treasurers/{user_id}`
- **Description**: Full profile and activity history for a specific treasurer.
- **Response**: `200 OK` with profile, active groups, and subscription status.

### 2.3 Escalated Profile Update
`PATCH /users/treasurers/{user_id}`
- **Description**: Allows admins to correct user data or override verification status.
- **Input**: `{"email": "...", "phone_number": "...", "is_verified": true}`.
- **Response**: `200 OK` with updated profile.

### 2.4 Update Account Status
`POST /users/treasurers/{user_id}/status`
- **Description**: Suspend or reactivate an account.
- **Input**: `{"status": "suspended", "reason": "Suspicious activity detected"}`.
- **Response**: `200 OK`.

### 2.5 View User Groups & Campaigns
`GET /users/treasurers/{user_id}/groups`
- **Description**: Lists all community groups owned and managed by the treasurer.
- **Response**: `200 OK` with a list of group objects.

`GET /groups/{group_id}/campaigns`
- **Description**: Lists all fundraising campaigns within a specific group.
- **Response**: `200 OK` with a list of campaign objects.

### 2.6 View Group Transaction Records
`GET /groups/{group_id}/transactions`
- **Description**: Provides full visibility into the finalized financial records of a specific group.
- **Query Parameters**: `campaign_id`, `start_date`, `end_date`, `min_amount`.
- **Response**: `200 OK` with the transaction history.

---

## 3. AI Parser Governance APIs

### 3.1 Trigger Model Training
`POST /ai/parser/train`
- **Description**: Initiates the `train_model.py` pipeline.
- **Input**: `{"epochs": 10, "dropout": 0.2, "version_tag": "v1.2.0"}`.
- **Response**: `202 Accepted` with `{"job_id": "job-123", "status": "training"}`.

### 3.2 Knowledge Base Oversight
`GET /ai/parser/knowledge`
- **Description**: Lists message fingerprints and their reliability scores.
- **Response**: `200 OK` with `{"fingerprints": [...]}`.

### 3.3 Manage Correction Feedback
`GET /ai/parser/feedback-queue`
- **Description**: Lists treasurer corrections that are pending review for inclusion in the training set.
- **POST /ai/parser/feedback-queue/{id}/approve**: Commits correction to the training dataset.

---

## 4. Subscriptions & Plan Management APIs

### 4.1 Global Revenue Summary
`GET /finance/revenue/summary`
- **Description**: Platform-wide cashflow and subscription revenue metrics.
- **Query Parameters**: `start_date`, `end_date`.
- **Response**: `200 OK` with daily revenue nodes.

### 4.2 Create Subscription Plan
`POST /finance/plans`
- **Description**: Defines a new subscription tier for treasurers.
- **Input**: 
  ```json
  {
    "name": "Gold Tier",
    "price": 2500,
    "currency": "KES",
    "period": "monthly",
    "features": ["AI Parsing", "Unlimited Groups", "Priority Support"],
    "limits": {
      "max_transactions": 1000,
      "max_campaigns": 50
    }
  }
  ```
- **Response**: `201 Created` with the new Plan ID.

### 4.3 List & Manage Plans
`GET /finance/plans`
- **Description**: Retrieves all available subscription tiers.
- **PATCH /finance/plans/{plan_id}`: Updates pricing, features, or status of an existing plan.
- **DELETE /finance/plans/{plan_id}`: Deactivates a plan (prevents new signups).

### 4.4 Manage Subscription Overrides
`POST /finance/subscriptions/{subscription_id}/override`
- **Description**: Grants trial periods or manually extends a treasurer's plan.
- **Input**: `{"extend_days": 30, "reason": "Support compensation"}`.
- **Response**: `200 OK`.

### 4.5 Global Payment Records
`GET /finance/payments`
- **Description**: Detailed history of every subscription payment received by the platform.
- **Query Parameters**: `status` (success/failed), `user_id`, `plan_id`, `start_date`, `end_date`.
- **Response**: `200 OK` with a list of payment objects.

### 4.6 User Payment History
`GET /users/treasurers/{user_id}/payments`
- **Description**: Dedicated payment history for a specific treasurer.
- **Response**: `200 OK` with all payment attempts and successful subscription renewals.

---

## 5. CRM & Engagement APIs

### 5.1 Ticket Management
`GET /crm/tickets`
- **Description**: List all support tickets.
- **PATCH /crm/tickets/{id}`: Update ticket status or assign to admin.
- **POST /crm/tickets/{id}/reply`: Send a message/email to the user.

### 5.2 System Broadcast
`POST /crm/broadcast`
- **Description**: Sends a message to all treasurers or a filtered subset.
- **Input**: `{"message": "Maintenance tonight...", "channel": "whatsapp", "filters": {"role": "treasurer"}}`.
- **Response**: `200 OK` with `{"sent_count": 500}`.

---

## 6. Security & Identity APIs

### 6.1 Force MFA Reset
`POST /security/users/{user_id}/mfa-reset`
- **Description**: Disables MFA for a user who has lost their device, allowing them to re-setup.
- **Response**: `200 OK`.

### 6.2 Global Security Policy
`PATCH /security/config`
- **Description**: Updates platform-wide security settings.
- **Input**: `{"mfa_required": true, "session_timeout_minutes": 60}`.

---

## 7. Audit & Forensic APIs

### 7.1 Search Audit Logs
`GET /audit/logs`
- **Description**: Advanced search through the forensic audit trail.
- **Query Parameters**: `actor_id`, `entity_type`, `action`, `start_date`, `end_date`.
- **Response**: `200 OK` with detailed forensic payloads.

### 7.2 Export Logs
`POST /audit/export`
- **Description**: Generates a CSV/PDF export of logs for a specific timeframe.
- **Response**: `200 OK` with download link.

---

## 8. Standard Error Responses

| Code | Meaning | Payload Example |
| :--- | :--- | :--- |
| `401` | Unauthorized | `{"error": "Missing or invalid token"}` |
| `403` | Forbidden | `{"error": "Insufficient permissions (Admin role required)"}` |
| `404` | Not Found | `{"error": "Entity not found"}` |
| `422` | Validation Error | `{"error": "Invalid input parameters", "details": [...]}` |
| `500` | System Error | `{"error": "Internal server error", "trace_id": "abc-123"}` |

### 4.3 Manual Subscription Override
POST /finance/payments/override
- **Description**: Manually grants or extends a subscription for a user.
- **Input**: {"user_id": "...", "plan_id": "...", "duration": 30}
- **Response**: 200 OK.
