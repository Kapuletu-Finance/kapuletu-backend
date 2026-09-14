# Module: Audit & Forensics

## 1. Overview
In a "Professional Grade" fintech application, every action must be accountable. This module specifies the forensic tracking system that records every interaction within the Admin Panel and critical user actions on the platform.

## 2. Key Functionalities

### 2.1 The "Forensic Payload" (Audit Log Structure)
Every logged action must contain a standardized payload for forensic analysis.
- **Actor Context**: `user_id`, `role` (Admin/Treasurer), `source_ip`, and `user_agent`.
- **Action Context**: `timestamp`, `action_type` (CREATE, UPDATE, DELETE, EXECUTE), and `severity_level` (INFO, WARNING, CRITICAL).
- **Data Context**: 
    - `entity_id` & `entity_type` (e.g., `TRANSACTION`, `USER_PROFILE`).
    - **Delta Tracking**: Capturing `old_values` (JSON) and `new_values` (JSON).
- **Outcome Context**: `status` (SUCCESS, FAILURE) and any associated `error_code`.

### 2.2 Administrative Action Tracking
Full transparency on what platform employees are doing.
- **Support Logs**: Tracking when an admin views or edits a treasurer's profile.
- **System Configuration**: Logging changes to platform-wide settings (e.g., fee changes, maintenance mode).
- **Model Training**: Recording every AI model update and who initiated it.

### 2.3 User Action Tracking (Critical Events)
Monitoring the high-stakes actions taken by treasurers.
- **Financial Commitments**: Finalizing a transaction into the ledger.
- **Group Management**: Creating or deleting groups.
- **Security Changes**: MFA activation, password changes, and phone number updates.

## 3. Data Storage & Integrity
- **Immutability**: Audit logs should ideally be stored in a write-once, read-many (WORM) environment or mirrored in a ledger database (like Amazon QLDB).
- **Retention Policy**: Defining how long logs are kept (e.g., 7 years for financial records).
- **Search & Filter**: Admin tools to quickly find actions based on Actor, Entity, or Date range.

## 4. Example Audit Entry (JSON)
```json
{
  "log_id": "aud-12345",
  "timestamp": "2024-05-14T10:00:00Z",
  "actor": {
    "user_id": "admin-001",
    "role": "super_admin",
    "ip": "192.168.1.1"
  },
  "action": "USER_PROFILE_UPDATE",
  "entity": {
    "type": "USER",
    "id": "treasurer-789"
  },
  "changes": {
    "old": {"phone_number": "+254700111222"},
    "new": {"phone_number": "+254799888777"}
  },
  "reason": "Treasurer requested phone update via ticket #456",
  "status": "SUCCESS"
}
```

---
**Technical Note**: The implementation uses the `AuditLog` model defined in `models/audit_log.py`.
