KapuLetu Treasury API — Complete Specification
Version: v1
Architecture: REST + Event-Driven (Serverless)
Base URL: https://api.kapuletu.com/v1

1. Core Design Principles
1.1 System Rules 
- A Group belongs to exactly ONE Treasurer (creator)
- A Campaign belongs to ONE Group
- A Transaction MUST go through Pending → Review → Ledger
- Ledger is immutable (NO update/delete)
- Every action creates an audit log
- Transaction code must be unique (deduplication enforced)

2. Authentication & Authorization
2.1 Auth Model
- JWT (Access + Refresh Tokens)
- RBAC enforced via roles (treasurer, admin, super_admin)

2.2 Authentication Endpoints
- POST /auth/register: Register Treasurer
- POST /auth/login: returns JWT tokens
- POST /auth/refresh: session extension
- POST /auth/logout: global sign-out
- GET /auth/me: get current profile
- PATCH /auth/me: update profile details
- POST /auth/change-password: authenticated update
- POST /auth/forgot-password: triggers recovery code
- POST /auth/reset-password: consumes recovery code
- POST /auth/verify: verify phone/email via OTP
- GET /auth/settings: retrieve user preferences (AI Training Opt-in)
- POST /auth/settings: update user preferences

3. Groups Management
- POST /groups: Create Chama/Organization
- GET /groups: List my groups
- GET /groups/{group_id}: Details
- PATCH /groups/{group_id}: Update
- DELETE /groups/{group_id}: Archive

4. Campaigns Management
- POST /groups/{group_id}/campaigns: Create fundraising goal
- GET /groups/{group_id}/campaigns: List goals
- GET /campaigns/{campaign_id}: Details
- PATCH /campaigns/{campaign_id}: Update
- POST /campaigns/{campaign_id}/status: Change status (Active/Closed)

5. Transaction Ingestion (Input Gateway)
- POST /ingestion/webhook: Twilio/WhatsApp message receiver
- POST /transactions/manual: Manual data entry
- GET /transactions/pending: Treasurer's Inbox
- GET /transactions/pending/{pending_id}: Single record

6. Parsing & Validation
- POST /transactions/{pending_id}/reparse: Force AI re-analysis
- POST /transactions/{pending_id}/validate: Pre-approval check

7. Review & Approval Workflow
- POST /transactions/{pending_id}/approve: Commit to ledger
- POST /transactions/{pending_id}/reject: Dismiss from inbox
- PATCH /transactions/{pending_id}: Edit amount/name before approval
- POST /transactions/{pending_id}/split: Multi-member allocation
- POST /transactions/bulk/approve: Approve multiple IDs at once
- POST /transactions/bulk/reject: Reject multiple IDs at once

8. Ledger (Immutable Source of Truth)
- GET /ledger: All group transactions
- GET /ledger/campaign/{campaign_id}: Goal-specific list
- GET /ledger/{ledger_id}: Audit single record (includes SHA-256 seal)

9. Members Management (Virtual Contributors)
- GET /members?group_id={group_id}: List unique contributors
- GET /members?group_id={group_id}&phone={phone}: Contributor history

10. Reporting Service
- GET /reports/daily: Real-time dashboard stats
- GET /reports/campaign/{campaign_id}: Official WhatsApp-formatted report
- GET /reports/export/excel: CSV/XLSX export for audits
- GET /reports/export/pdf: PDF document generation
- GET /reports/whatsapp-summary: Formatted summary for group sharing

11. Evidence Management
- GET /transactions/{pending_id}/evidence: Retrieve M-Pesa/Bank screenshot link
- POST /transactions/{pending_id}/evidence: Upload verification image

12. Audit Logs
- GET /audit/logs: All activity in the treasurer's context
- GET /audit/logs/{entity_type}/{entity_id}: History of a specific record

13. Admin Governance Suite (Admin Only)
13.1 User & AI Control
- GET /admin/v1/users/treasurers: List platform users
- GET /admin/v1/users/treasurers/{user_id}: Details
- POST /admin/v1/users/treasurers/{user_id}/status: Suspend/Activate
- GET /admin/v1/ai/parser/feedback-queue: Review AI corrections
- POST /admin/v1/ai/parser/feedback-queue/{id}/approve: Add to training set
- GET /admin/v1/ai/parser/config: Toggle Training Mode (Continuous/Periodic)
- POST /admin/v1/ai/parser/config: Update AI system settings

13.2 Finance & CRM
- GET /admin/v1/finance/plans: List all subscription tiers
- POST /admin/v1/finance/plans: Create new tier
- GET /admin/v1/finance/payments: Global revenue logs
- POST /admin/v1/finance/payments/override: Manual subscription management
- POST /admin/v1/crm/broadcast: Platform-wide SMS/WhatsApp notices
- GET /admin/v1/crm/tickets: Manage support requests
- PATCH /admin/v1/crm/tickets/{id}: Update ticket status

13.3 Advanced Auditing & Forensics
- GET /admin/v1/audit/logs: Search platform-wide forensic trail
- POST /admin/v1/audit/export: Export logs for compliance

14. Finance & Subscriptions (User Facing)
- GET /finance/available-plans: Pricing tiers
- POST /finance/checkout: Initiate M-Pesa STK or Flutterwave checkout
- GET /finance/status/{checkout_id}: Poll payment state
- GET /finance/my-subscription: Current feature access

15. Status Lifecycle
- Pending Transaction Flow: pending → under_review → approved → ledger
- Outcome States: rejected, split_approved, voided

16. Critical Validation Rules
- transaction_code MUST be unique across the platform.
- amount MUST be > 0.
- split total MUST equal original amount.
- NO update or delete allowed on the Ledger.
