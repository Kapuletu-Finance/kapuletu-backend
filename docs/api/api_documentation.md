KapuLetu Treasury API — Complete Specification
Version: v1
Architecture: REST + Event-Driven (Serverless)
Base URL:
https://api.kapuletu.com/v1

1. Core Design Principles
1.1 System Rules 
A Group belongs to exactly ONE Treasurer (creator)
A Campaign belongs to ONE Group
A Transaction MUST go through Pending → Review → Ledger
Ledger is immutable (NO update/delete)
All approvals must be auditable
Every action creates an audit log
Transaction code must be unique (deduplication enforced)
2. Authentication & Authorization (Complete)
2.1 Auth Model
JWT (Access + Refresh Tokens)
RBAC enforced via roles & permissions
2.2 Authentication Endpoints
Register Treasurer
POST /auth/register
Body
{
 "full_name": "John Doe",
 "email": "john@example.com",
 "phone_number": "2547XXXXXXXX",
 "password": "securePassword"
}

Login
POST /auth/login
Response
{
 "access_token": "...",
 "refresh_token": "...",
 "expires_in": 3600
}

Refresh Token
POST /auth/refresh

Logout
POST /auth/logout

Get Current User
GET /auth/me

Update Profile
PATCH /auth/me

Change Password
POST /auth/change-password

Request Password Reset
POST /auth/forgot-password

Reset Password
POST /auth/reset-password

Verify Phone / Email
POST /auth/verify

3. Groups Management
Create Group
POST /groups
Get All My Groups
GET /groups
Get Single Group
GET /groups/{group_id}
Update Group
PATCH /groups/{group_id}
Archive Group
DELETE /groups/{group_id}













4. Campaigns Management
Create Campaign
POST /groups/{group_id}/campaigns
List Campaigns
GET /groups/{group_id}/campaigns
Get Campaign
GET /campaigns/{campaign_id}
Update Campaign
PATCH /campaigns/{campaign_id}
Change Campaign Status
POST /campaigns/{campaign_id}/status

5. Transaction Ingestion (Input Gateway)
Webhook (Twilio / External)
POST /ingestion/webhook
Manual Entry
POST /transactions/manual

Get Pending Transactions (Inbox)
GET /transactions/pending
Get Single Pending
GET /transactions/pending/{pending_id}




6. Parsing & Validation
Re-parse Message
POST /transactions/{pending_id}/reparse
Validate Transaction
POST /transactions/{pending_id}/validate

7. Review & Approval Workflow
Approve Transaction
POST /transactions/{pending_id}/approve
Reject Transaction
POST /transactions/{pending_id}/reject
Edit Transaction
PATCH /transactions/{pending_id}
Add Note
POST /transactions/{pending_id}/note
Split Transaction
POST /transactions/{pending_id}/split
Body
{
 "allocations": [
   { "name": "John", "amount": 1000 },
   { "name": "Mary", "amount": 1000 }
 ]
}




Bulk Approval
POST /transactions/bulk/approve
Bulk Reject
POST /transactions/bulk/reject

8. Ledger (Immutable)
Get Ledger Entries
GET /ledger
Get Ledger by Campaign
GET /ledger/campaign/{campaign_id}
Get Ledger Entry
GET /ledger/{ledger_id}

9. Members (Optional / Future-Proof)
Auto-Suggest Members
GET /members/suggestions
Create Member (Optional)
POST /members
Get Members
GET /groups/{group_id}/members



10. Reporting Service
Daily Summary
GET /reports/daily
Campaign Progress
GET /reports/campaign/{campaign_id}
Contributor List
GET /reports/contributors/{campaign_id}

Export Excel
GET /reports/export/excel
Export PDF
GET /reports/export/pdf

WhatsApp Summary Format
GET /reports/whatsapp-summary




11. Evidence Management
Get Transaction Evidence
GET /transactions/{pending_id}/evidence
Upload Evidence (Future)
POST /transactions/{pending_id}/evidence

12. Audit Logs
Get Audit Logs
GET /audit/logs
Get Logs by Entity
GET /audit/logs/{entity_type}/{entity_id}

13. Notifications - to be implemented later to send notifications
Send Confirmation (After Approval)
POST /notifications/send


14. System Health & Admin
Health Check
GET /health
Metrics
GET /metrics

15. Event-Driven Internal Triggers
These are NOT public APIs but MUST exist:
transaction.received
transaction.parsed
transaction.approved
transaction.rejected
ledger.updated
report.generated
16. Critical Validation Rules
Transaction Rules
transaction_code MUST be unique
amount MUST be > 0
campaign MUST belong to group
approval REQUIRED before ledger write

Approval Rules
cannot approve twice
split total MUST equal original amount
rejected transactions CANNOT go to ledger


Ledger Rules
NO update
NO delete
only append

17. Error Handling Standard
{
 "error": {
   "code": "TRANSACTION_DUPLICATE",
   "message": "Transaction code already exists",
   "details": {}
 }
}


18. Status Lifecycle
Pending Transaction Flow
pending → under_review → approved → ledger
                          ↘ rejected
                          ↘ needs_clarification

19. Security
JWT required on all endpoints
Role-based permission checks
Rate limiting on ingestion
Webhook signature validation (Twilio)




20. What This API Guarantees
If implemented correctly, there will be - 
Zero duplicate financial entries
Full audit traceability
Immutable financial history
Scalable ingestion pipeline
Clean frontend-backend contract
Extensibility for Phase 2 (payments, AI, etc.)

