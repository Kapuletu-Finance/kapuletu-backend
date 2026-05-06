KapuLetu Treasury System - Constraints & Scope Definition
1. System Constraints (Non-Negotiable Rules)
These are hard boundaries that must never be violated, regardless of feature changes or scaling.
1.1 Financial Integrity Constraints
Immutable Ledger
Once a transaction is written to the ledger:
 Cannot be updated
 Cannot be deleted
 Only append new correcting entries
Reason:
 Prevents fraud, ensures auditability, and builds trust.
Single Source of Truth
Only the ledger represents official financial state
Pending and review tables are non-authoritative
Transaction Uniqueness
transaction_code must be globally unique (indexed)
Duplicate detection must occur:
at ingestion
at approval
Atomic Approval Operation
Approval must:
Validate transaction
Create ledger entries
Record audit log
Store allocations (if split)
→ Must succeed as one logical unit or fail completely

1.2 Workflow Constraints
Mandatory Review Step
No transaction goes directly to ledger
All transactions MUST pass through:
pending → review → approved → ledger

State Transition Rules
Allowed transitions only:
pending → under_review
under_review → approved
under_review → rejected
under_review → needs_clarification
Invalid transitions must be blocked.
No Double Approval
A transaction cannot be:
approved twice
rejected after approval

1.3 Ownership Constraints
Group Ownership
A group has exactly one treasurer (creator)
That treasurer:
controls campaigns
approves transactions
owns audit trail
Campaign Isolation
A campaign:
belongs to one group
cannot share transactions across groups
1.4 Data Consistency Constraints
Split Allocation Integrity
Sum of allocations MUST equal original amount
Example:
Total: 5000
Allocations:
1000 + 1000 + 1000 + 1000 + 1000 =  valid
Currency Consistency
All transactions within a group must use same currency (e.g., KES)
Timestamp Integrity
System timestamp must always be:
server-generated
immutable in ledger
1.5 Evidence Constraints
Every transaction MUST retain:
raw message
parsed output
Evidence must:
never be overwritten
always be retrievable





1.6 Security Constraints
All endpoints require authentication (except webhook)
Webhook must be:
signed
verified (e.g., Twilio signature)
1.7 Performance Constraints
Inbox (pending transactions) must load fast:
indexed by created_at, group_id
Duplicate detection must be O(log n) via indexing

2. System Scope Definition
This defines what KapuLetu does and does NOT do (yet).
2.1 In-Scope (Phase 1)
Transaction Management
Ingest messages (SMS, WhatsApp, manual)
Parse into structured data
Store in pending queue
Enable review workflow

Treasurer Operations
Approve / reject / edit transactions
Split contributions
Assign campaigns
Add notes




Ledger Management
Write approved transactions to immutable ledger
Query ledger by:
campaign
date
contributor
Campaign Management
Create campaigns
Track targets vs contributions
Manage campaign lifecycle

Reporting
Daily summaries
Campaign progress
Contributor breakdown
Export (PDF, Excel, WhatsApp format)

Audit & Traceability
Track:
who approved
when
what changed
Maintain full action history
Evidence Management
Store raw transaction messages
Link evidence to approvals





2.2 Explicitly Out of Scope (Phase 1)
These are intentionally excluded to keep the system stable
 Direct Payment Processing
No native M-Pesa integration (yet)
No card or bank processing
Member Self-Service Portal
Members do NOT:
log in
view balances
interact directly
Multi-Treasurer Governance
No shared ownership of groups
No role conflicts
Real-Time Notifications (Optional)
SMS/WhatsApp notifications are not core
Can be added later
Advanced Analytics / AI
No prediction models yet
No behavioral insights yet





2.3 Future Scope (Phase 2)
These must NOT influence current design complexity:

Payment Integration
M-Pesa STK Push
Wallet systems

Contribution Links
Shareable payment URLs
Member Accounts
Personal dashboards
Statement downloads
AI Layer
Smart duplicate detection
Fraud detection
Contribution trends
3. Key Design Boundaries
3.1 Separation of Concerns
Layer
Responsibility
Ingestion
Receive + parse
Pending
Store unverified data
Review
Human validation
Ledger
Final truth
Reporting
Read-only aggregation


3.2 Event-Driven Boundaries
Each stage emits events:
transaction.received
transaction.parsed
transaction.approved
ledger.updated
No service should directly depend on another synchronously unless necessary.
3.3 Failure Handling Constraints
Parsing failure ≠ system failure
 → store as partial or failed
Approval failure must:
rollback everything
log error
4. Risks & Tradeoffs 
4.1 Manual Approval Dependency
Strength: accuracy, trust
Weakness: scalability bottleneck

4.2 No Member Accounts
Strength: simplicity
Weakness: limited transparency for contributors

4.3 Message Parsing Limitations
SMS formats vary
WhatsApp forwards inconsistent
→ must support partial parsing + human correction
5. What Makes This System Strong
If all constraints are respected:
No duplicate money records
Full financial traceability
Audit-ready system
Scalable ingestion pipeline
Minimal treasurer cognitive load



This document protects -
trust
money
accountability


