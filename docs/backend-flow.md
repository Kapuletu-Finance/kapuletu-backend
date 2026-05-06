KAPULETU BACKEND FLOW — COMPLETE SYSTEM DOCUMENTATION
1. SYSTEM OVERVIEW (BIG PICTURE)

This  backend is a pipeline of financial events:

Message → Parse → Store → Review → Approve → Ledger → Report

Each stage:

runs independently
is triggered by an event
uses a dedicated service
 2. CORE SYSTEM COMPONENTS
Messaging Layer
Twilio
Receives SMS / WhatsApp → sends webhook to backend
API Entry Layer
Amazon API Gateway
Receives HTTP request → triggers backend functions
Compute Layer
AWS Lambda
Runs your backend logic (ingestion, approval, reporting)
Data Layer
Amazon RDS → operational data
Amazon QLDB → immutable financial records
Amazon S3 → reports/files

 3. FLOW 1 — TRANSACTION INGESTION (CRITICAL ENTRY POINT)
🔹 Step 1: User Sends Payment Message

Example:

"John sent 1,000 via M-Pesa TX123"
🔹 Step 2: Twilio Receives Message
Message hits Twilio
Twilio forwards it to your webhook URL
🔹 Step 3: API Gateway Receives Webhook
Endpoint: /webhook/ingest
Amazon API Gateway triggers Lambda
🔹 Step 4: Ingestion Lambda Executes

File:

services/ingestion/handler.py
Responsibilities:
extract raw message
normalize input
pass to parser
🔹 Step 5: Parsing Engine Runs

File:

parser_engine.py

Uses:

spaCy
regex rules
Output (structured JSON):
{
  "sender": "John",
  "amount": 1000,
  "transaction_code": "TX123",
  "method": "M-Pesa"
}
🔹 Step 6: Validation Layer

File:

validators.py

Checks:

required fields exist
amount is valid
format is correct
🔹 Step 7: Store as Pending Transaction

Stored in:

Amazon RDS

Table:

transactions (status = "PENDING")
🔹 Step 8: Evidence Preservation

Also store:

raw message text
metadata (timestamp, sender phone)

This is critical for audits

RESULT OF INGESTION FLOW

You now have:

structured transaction
stored safely
awaiting human review
 4. FLOW 2 — TREASURER REVIEW & APPROVAL
🔹 Step 1: Frontend Fetches Pending Transactions

Frontend (Next.js) calls:

GET /transactions/pending
🔹 Step 2: Treasurer Reviews

UI shows:

amount
sender
message evidence
🔹 Step 3: Treasurer Takes Action

Actions:

Approve
Reject
Edit
Split
🔹 Step 4: Approval API Call

Endpoint:

POST /transactions/{id}/approve

Triggers:

services/approval/handler.py
🔹 Step 5: Validation Before Approval

File:

validator.py

Checks:

duplicate transaction codes
suspicious patterns
missing fields
🔹 Step 6: Optional Editing / Splitting

Example:

KES 5000 → split into 5 members

System creates:

multiple linked records
🔹 Step 7: Move to Ledger (CRITICAL STEP)

Approved transaction is written to:

Amazon QLDB
Why QLDB?
immutable (cannot be deleted)
full history
cryptographic verification
🔹 Step 8: Update Status in Postgres

Transaction becomes:

status = APPROVED
🔹 Step 9: Trigger Internal Event

Example:

transaction_approved

Used by:

reporting service
notifications (future)
RESULT OF APPROVAL FLOW

You now have:

verified transaction
immutable record
audit trail

 5. FLOW 3 — REPORTING ENGINE
🔹 Step 1: Trigger Reporting

Triggered by:

scheduled job OR
manual request
🔹 Step 2: Reporting Lambda Executes

File:

services/reporting/handler.py
🔹 Step 3: Fetch Data

From:

Amazon RDS (current state)
Amazon QLDB (verified records)
🔹 Step 4: Generate Summary

File:

daily_summary.py

Output:

Total: KES 25,000
Contributors: 12
Campaign Progress: 60%
🔹 Step 5: Generate Files
Excel
excel_gen.py
PDF
pdf_gen.py
🔹 Step 6: Store Reports

Saved in:

Amazon S3
🔹 Step 7: Deliver Output
download link
WhatsApp-ready message (future)
RESULT OF REPORTING FLOW
automatic summaries
downloadable reports
real-time visibility

 6. FLOW 4 — MEMBERS MANAGEMENT
Actions:
create member
update member
assign to group
Backend:
services/members/
Data stored in:
Amazon RDS

 7. FLOW 5 — CAMPAIGNS MANAGEMENT
Actions:
create campaign
assign transactions
track progress
Example:
Church Roof Fund
Target: 100,000
Current: 62,000

 8. INTERNAL SYSTEM EVENTS

Your system communicates internally using events.

Examples:

transaction_received
transaction_approved
report_generated

Used for:

decoupling services
triggering workflows

 9. SECURITY & CONTROL FLOW
Authentication

Handled in:

common/auth.py
Authorization

Roles:

admin
treasurer
IAM (AWS Layer)
frontend cannot access ledger directly
only backend writes to QLDB


 10. DATA FLOW SUMMARY
Before Approval:
stored in Postgres (editable)
After Approval:
stored in QLDB (immutable)

 11. FAILURE HANDLING FLOW
If parsing fails:
mark transaction as "FAILED"
log error in Amazon CloudWatch
If validation fails:
reject transaction
notify treasurer
If Lambda fails:
automatic retry (AWS)
error logged


Therefore  this  backend is:

👉 A financial processing engine
👉 Built on event triggers
👉 Structured into independent flows
👉 Designed for audit, scale, and automation

💡 THE MOST IMPORTANT INSIGHT

Everything revolves around:

“A transaction moving from unstructured → verified → immutable → reported”