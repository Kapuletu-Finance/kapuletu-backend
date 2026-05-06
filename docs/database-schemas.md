FINAL DATABASE DESIGN 

We’ll structure this into 4 layers:

Identity & Ownership (who controls what)
Context (groups & campaigns)
Transaction Pipeline (core system)
Ledger & Audit (truth & traceability)


1. IDENTITY & OWNERSHIP
🧑‍💼 users (Treasurers + System Admins)
users
Field	Type	Notes
user_id	UUID (PK)	
full_name	VARCHAR	
email	VARCHAR	unique
phone_number	VARCHAR	UNIQUE (critical for routing messages)
password_hash	TEXT	
role	ENUM	('treasurer','admin','super_admin')
is_active	BOOLEAN	
last_login	TIMESTAMP	
created_at	TIMESTAMP	
updated_at	TIMESTAMP	
🔑 KEY RULE

👉 Phone number identifies which treasurer owns incoming messages

🏢 2. GROUPS & CAMPAIGNS (TREASURER-CONTROLLED)
🏢 groups
groups
Field	Type	Notes
group_id	UUID (PK)	
owner_id	UUID (FK → users)	treasurer
group_name	VARCHAR	
currency	VARCHAR(3)	default 'KES'
is_active	BOOLEAN	
created_at	TIMESTAMP	

👉 One treasurer → many groups
👉 Group belongs to ONLY one treasurer (your rule)

🎯 campaigns
campaigns
Field	Type	Notes
campaign_id	UUID (PK)	
group_id	UUID (FK)	
title	VARCHAR	
target_amount	DECIMAL	
start_date	DATE	
end_date	DATE	
status	ENUM	('active','completed','archived')
is_default	BOOLEAN	auto-attach logic
created_at	TIMESTAMP	
🔑 IMPORTANT LOGIC

If:

only 1 campaign exists
👉 auto-assign transactions

Else:
👉 treasurer assigns manually

⚙️ 3. TRANSACTION PIPELINE (CORE SYSTEM)
📥 3.1 pending_transactions (INBOX)
pending_transactions
Field	Type	Notes
pending_id	UUID (PK)	
owner_id	UUID (FK → users)	treasurer
group_id	UUID (FK)	auto-resolved
campaign_id	UUID (FK, nullable)	
raw_message	TEXT	
message_attachments	JSONB	
source_channel	ENUM	('whatsapp','sms','manual')
source_reference_id	VARCHAR	Twilio SID
idempotency_key	VARCHAR UNIQUE	prevents duplicates
extracted_code	VARCHAR	transaction code
extracted_sender_name	TEXT	
extracted_amount	DECIMAL	
extracted_phone	VARCHAR	
extracted_date	TIMESTAMP	
parsing_status	ENUM	('success','partial','failed')
parser_warning_flag	TEXT	
confidence_score	DECIMAL(5,2)	
workflow_status	ENUM	('pending','under_review','approved','rejected','needs_clarification')
assigned_treasurer_id	UUID	
created_at	TIMESTAMP	
updated_at	TIMESTAMP	
🔒 CRITICAL CONSTRAINT
UNIQUE(extracted_code, owner_id)

👉 Prevents duplicate M-Pesa ingestion

🧠 3.2 review_actions (HUMAN DECISIONS)
review_actions
Field	Type
action_id	UUID (PK)
pending_id	UUID
action_type	ENUM ('approve','reject','edit','note','split','reassign')
action_by	UUID (treasurer)
internal_note	TEXT
created_at	TIMESTAMP

👉 Full audit of every click

✂️ 3.3 review_allocations (FINAL DISTRIBUTION LOGIC)
review_allocations
Field	Type
allocation_id	UUID
pending_id	UUID
action_id	UUID
member_name	VARCHAR (NOT FK intentionally)
member_phone	VARCHAR (optional)
allocated_amount	DECIMAL
allocation_mode	ENUM ('single','split_manual','split_equal','split_percentage')
allocation_sequence	INTEGER
created_at	TIMESTAMP

🔥 KEY DESIGN DECISION

👉 NO STRICT MEMBERS TABLE REQUIRED

Why:

names come from parsing
treasurer controls truth
flexibility > rigidity
🧾 3.4 transactions (FINAL SNAPSHOT TABLE)
transactions
Field	Type
transaction_id	UUID
owner_id	UUID
group_id	UUID
campaign_id	UUID
pending_id	UUID
transaction_code	VARCHAR
total_amount	DECIMAL
source_channel	TEXT
status	ENUM ('approved')
ledger_id	VARCHAR (QLDB reference)
created_at	TIMESTAMP

👉 This is your fast query table

📜 4. LEDGER (IMMUTABLE TRUTH)

Stored in:

Amazon QLDB
official_ledger (logical model)
{
  "ledger_id": "uuid",
  "owner_id": "treasurer",
  "group_id": "...",
  "campaign_id": "...",
  "transaction_code": "ABC123",
  "total_amount": 5000,
  "allocations": [
    {"name": "John", "amount": 1000},
    {"name": "Mary", "amount": 1000}
  ],
  "approved_by": "user_id",
  "approved_at": "timestamp",
  "source": "whatsapp",
  "raw_reference": "TwilioSID",
  "metadata_hash": "..."
}

👉 Ledger stores final truth only

📊 5. REPORTING
reports
reports
Field	Type
report_id	UUID
owner_id	UUID
group_id	UUID
campaign_id	UUID
report_type	ENUM ('daily','campaign','member')
file_url	TEXT
created_at	TIMESTAMP


In the reporting we also need a reporting of a whatsap ready message that can be directly copied to whatsap or shared directly to whatsap, this means we should have something like :

TITLE of Ksh 5000 FOR THE CONTRIBUTION OF SO AND SO  for so and so ......

1.John Wainaina - 2500
2.Mary Wanjiku - 1000
3.Peter Kamau - 500

Total Amount Contributed: 4000
Total Amount Remaining: 1000


🔐 6. AUDIT LOGGING
audit_logs
audit_logs
Field	Type
log_id	BIGINT
actor_id	UUID
action	VARCHAR
entity_type	VARCHAR
entity_id	UUID
previous_values	JSONB
new_values	JSONB
ip_address	VARCHAR
created_at	TIMESTAMP
🔁 7. COMPLETE FLOW (FINAL)
📥 Ingestion
Message → pending_transactions
🧠 Review
pending → review_actions → review_allocations
✅ Approval
pending → transactions → QLDB ledger
📊 Reporting
transactions → reports
💡 FINAL DESIGN PRINCIPLES YOU ACHIEVED
✅ Treasurer-first system
no forced member registry
full flexibility
✅ Human-controlled truth
parser suggests
treasurer decides
✅ Strong auditability
raw message stored
every action logged
immutable ledger
✅ Scalable architecture
multi-group
multi-campaign
future-ready
🧠 FINAL VERDICT

👉 This schema is now:

aligned with your real workflow
flexible enough for messy real-world data
strict enough for financial integrity
ready for production build