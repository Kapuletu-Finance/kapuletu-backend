FULL BACKEND STRUCTURE (kapuletu-backend)
kapuletu-backend/
│
├── serverless.yml
├── requirements.txt
├── .env
├── .gitignore
├── README.md
├── pyproject.toml
│
├── common/
│   ├── __init__.py
│   ├── database.py
│   ├── qldb.py
│   ├── config.py
│   ├── logger.py
│   ├── auth.py
│   ├── utils.py
│
├── services/
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   ├── parser_engine.py
│   │   ├── schemas.py
│   │   ├── validators.py
│   │
│   ├── approval/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   ├── validator.py
│   │   ├── service.py
│   │   ├── schemas.py
│   │
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   ├── daily_summary.py
│   │   ├── excel_gen.py
│   │   ├── pdf_gen.py
│   │
│   ├── members/
│   │   ├── handler.py
│   │   ├── service.py
│   │   ├── schemas.py
│   │
│   ├── campaigns/
│   │   ├── handler.py
│   │   ├── service.py
│   │   ├── schemas.py
│
├── models/
│   ├── __init__.py
│   ├── transaction.py
│   ├── member.py
│   ├── campaign.py
│   ├── ledger_entry.py
│
├── repositories/
│   ├── __init__.py
│   ├── transaction_repo.py
│   ├── member_repo.py
│   ├── campaign_repo.py
│
├── events/
│   ├── __init__.py
│   ├── event_bus.py
│   ├── transaction_events.py
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_approval.py
│   ├── test_reporting.py
│
└── scripts/
    ├── seed_data.py
    ├── migrate.py
🧠 ROOT FILES (Top Level)
📄 serverless.yml

Defines your entire backend in AWS.

connects routes → Lambda functions
defines API endpoints
sets environment variables

👉 This is what deploys everything to AWS Lambda

📄 requirements.txt

Python dependencies:

spaCy
boto3 (AWS SDK)
fastapi (optional utilities)
📄 .env

Local development secrets:

DATABASE_URL=
TWILIO_SECRET=
📄 pyproject.toml

Used by:

Ruff
formatting + linting config
📄 README.md

Explains:

how to run
how to deploy
architecture overview
🧩 common/ (Shared Core Utilities)

This is your foundation layer.

📄 database.py

Handles connection to:

Amazon RDS

Responsibilities:

open/close DB connections
execute queries safely
📄 qldb.py

Handles connection to:

Amazon QLDB

Responsibilities:

write immutable records
query ledger history
📄 config.py

Central config loader:

environment variables
app settings
📄 logger.py

Central logging system:

sends logs to Amazon CloudWatch
📄 auth.py

Handles:

authentication checks
role validation (treasurer, admin)
📄 utils.py

Reusable helpers:

date formatting
currency formatting
ID generation
🔵 services/ (Business Logic Layer)

Each folder = a mini-application (Lambda service)

📥 ingestion/ (ENTRY POINT OF THE SYSTEM)
📄 handler.py

Triggered by:

Twilio webhook

Responsibilities:

receive raw message
call parser
save to DB (pending)
📄 parser_engine.py

Core intelligence:

Uses:

spaCy
regex

Extracts:

name
amount
transaction code
timestamp
📄 schemas.py

Defines data structure:

TransactionSchema:
  name
  amount
  phone
📄 validators.py

Checks:

message format
required fields present
🟡 approval/ (TREASURER DECISION ENGINE)
📄 handler.py

Triggered when treasurer clicks:

approve
reject
📄 service.py

Main business logic:

move data from pending → ledger
update status
📄 validator.py

Checks:

duplicate transactions
fraud patterns
📄 schemas.py

Defines:

approval request format
🟢 reporting/ (OUTPUT ENGINE)
📄 handler.py

Entry point for:

generating reports
📄 daily_summary.py

Generates:

totals
contributors list
📄 excel_gen.py

Creates Excel files:

uploads to Amazon S3
📄 pdf_gen.py

Creates PDF reports (optional but powerful)

👥 members/ (USER MANAGEMENT)
📄 handler.py

API endpoints:

create member
list members
📄 service.py

Business rules:

register member
assign to group
📄 schemas.py

Defines member structure

🎯 campaigns/ (FUND MANAGEMENT)
📄 handler.py

Endpoints:

create campaign
list campaigns
📄 service.py

Logic:

assign transactions to campaigns
📄 schemas.py

Campaign data structure

🧬 models/ (DATA STRUCTURE)

Represents database tables.

📄 transaction.py

Fields:

amount
sender
status (pending/approved)
📄 member.py

Fields:

name
phone
📄 campaign.py

Fields:

name
goal
📄 ledger_entry.py

Immutable record for QLDB

🗄 repositories/ (DATABASE ACCESS LAYER)

This separates DB logic from business logic.

📄 transaction_repo.py

Handles:

insert transaction
fetch pending transactions
📄 member_repo.py

Handles:

CRUD for members
📄 campaign_repo.py

Handles:

campaign queries
🔁 events/ (SYSTEM COMMUNICATION)

Optional but powerful.

📄 event_bus.py

Handles:

internal system events

Example:

“transaction_approved”
📄 transaction_events.py

Defines:

events triggered after approval
🧪 tests/ (QUALITY CONTROL)
test ingestion parsing
test approval logic
test reporting outputs
⚙️ scripts/ (UTILITY TASKS)
📄 seed_data.py

Adds:

test users
sample campaigns
📄 migrate.py

Handles:

DB schema updates
🔁 HOW EVERYTHING FLOWS (FINAL CONNECTION)
Message → Twilio
→ ingestion/handler.py
→ parser_engine.py
→ transaction saved (Postgres)
→ frontend fetches pending
→ approval/handler.py triggered
→ validator checks
→ saved to QLDB
→ reporting generates summary