**Kapuletu Treasury Backend**

Intelligent Financial Ingestion & Approval System for Community Treasuries

Kapuletu is a serverless backend system designed to automate and structure community financial management workflows for treasurers. It transforms unstructured payment messages (WhatsApp, SMS, manual entries) into validated, auditable, and immutable financial records.

**Overview**

Community treasuries currently rely on fragmented tools such as WhatsApp messages, SMS confirmations, spreadsheets, and manual bookkeeping.

Kapuletu replaces this with a structured, intelligent backend system that:

Captures incoming payment messages automatically
Extracts structured financial data using parsing logic
Routes transactions into a treasurer approval queue
Supports split allocations across multiple contributors
Maintains an immutable financial ledger for audit integrity
Generates automated reports and summaries


**System Architecture**

The backend follows a serverless event-driven microservices architecture deployed on AWS.

Core Components
AWS Lambda (compute layer)
Amazon RDS (PostgreSQL) – operational database
Amazon QLDB – immutable ledger
API Gateway – request routing
Twilio Webhooks – message ingestion


**Backend Codebase Structure**

```text
kapuletu-backend/
│
├── services/
│   ├── ingestion/        # Entry point (Twilio SMS/WhatsApp processing)
│   ├── approval/         # Treasurer review & decision engine
│   └── reporting/        # Summary reports & exports
│
├── common/
│   ├── database.py       # DB connections (Postgres + QLDB)
│   ├── logger.py         # Central logging system
│
├── models/               # ORM models (SQLAlchemy)
├── schemas/              # API validation (Pydantic)
├── migrations/           # SQL database definitions
│
├── tests/                # NLP + workflow tests
└── serverless.yml        # AWS Lambda deployment config

```


**End-to-End System Flow**

**1. Ingestion Layer**
Twilio receives SMS/WhatsApp messages
Message is forwarded to AWS Lambda (ingestion service)
NLP parser extracts:
sender name
amount
transaction code
timestamp
Data stored in pending_transactions


**2.  Treasurer Review Layer**
Treasurer views inbox (dashboard frontend)
Transactions are:
approved
rejected
edited
split across multiple members

All actions are logged in review_actions.

**3.  Allocation Engine**

If a transaction is split:

system creates multiple allocation records
each allocation maps a portion of the payment to a contributor

Stored in:
review_allocations

**4. Ledger Commitment (Final State)**

Once approved:

transaction is written to immutable ledger (QLDB)
cannot be modified or deleted

This becomes the official financial truth


**5.  Reporting Layer**

System generates:

daily summaries
campaign reports
contribution breakdowns
downloadable Excel/PDF reports
 Core Database Design
PostgreSQL (Operational Layer)

Handles mutable system state:

users (treasurers/admins)
groups
campaigns
pending transactions
review actions
allocations
audit logs
 QLDB (Immutable Ledger)

Stores final approved transactions:

immutable financial records
cryptographic audit trail
tamper-proof history
 Key Domain Models
 Users

Treasurer and admin identities controlling the system.

 Groups

Treasurer-owned financial organizations.

 Campaigns

Specific fundraising or contribution goals within groups.

 Pending Transactions

Raw parsed messages awaiting treasurer review.

 Review Actions

All human decisions (approve, reject, split, edit).

 Review Allocations

Split distribution of payments across contributors.

 Ledger Entries

Final immutable financial records.

**Security & Integrity Principles**
Phone number acts as primary routing identity for messages
Idempotency keys prevent duplicate transaction ingestion
Immutable ledger ensures financial audit safety
Role-based access control (RBAC)
Full audit trail of all system actions


**Technology Stack**
- Layer	Technology
- Backend Runtime	Python 3.11
- Serverless Compute	AWS Lambda
- API Layer	API Gateway
- Database (Operational)	PostgreSQL (RDS)
- Ledger	Amazon QLDB
- Message Ingestion	Twilio API
- Validation	Pydantic
- ORM	SQLAlchemy
- Logging	Custom Logger
- Linting	Ruff

**Transaction Lifecycle**
Incoming Message
      ↓
Parsing Engine (NLP)
      ↓
Pending Transaction (Postgres)
      ↓
Treasurer Review
      ↓
Approval / Split / Edit
      ↓
Final Transaction Table
      ↓
Immutable Ledger (QLDB)

**Key Features**
✔ Intelligent Parsing

Extracts structured data from unstructured messages.

✔ Treasurer-Controlled Workflow

Human approval is required before financial finalization.

✔ Flexible Contribution Handling

Supports:

single contributions
split payments
manual cash entries
✔ Immutable Financial Ledger

Ensures full audit integrity using QLDB.

✔ Multi-Group Support

Each treasurer can manage multiple independent groups.

✔ Campaign-Based Tracking

All transactions are tied to specific fundraising goals.

**Design Philosophy**

Kapuletu is built on four core principles:

1. Treasurer-first system

The treasurer is the central operator of the system.

2. Structured flexibility

Handles unstructured real-world financial data.

3. Auditability by design

Every action is traceable and logged.

4. Immutable financial truth

Approved data cannot be modified.

**Future Enhancements**
- Direct M-Pesa integration API
- Member self-service portal
- Payment links per campaign
- AI-driven financial insights
- Contribution prediction models
- Fraud detection layer

**Testing Strategy**
- NLP extraction accuracy tests
- transaction duplication prevention tests
- approval workflow validation tests
- ledger consistency checks

**Environment Setup (Dev)**
pip install -r requirements.txt

serverless deploy

alembic upgrade head

**System Roles**
- Role	Description
- Treasurer	Core system user, manages groups and approvals
- Admin	System-wide monitoring
- Super Admin	Infrastructure and platform control


**Final Summary**

Kapuletu Backend is a serverless, event-driven financial orchestration system that transforms unstructured communication into structured, auditable, and immutable financial records—centered entirely around treasurer workflows.

---

## CI/CD Pipeline

The project uses **GitHub Actions** for automated testing, linting, and deployment.

### Branch Strategy & Environments

```text
| Branch | Environment | AWS Role | Deployment Stage |
| :--- | :--- | :--- | :--- |
| `dev` | Development | `kapuletu-ci-cd-role-dev` | `dev` |
| `staging` | Staging | `kapuletu-ci-cd-role-staging` | `staging` |
| `production` | Production | `kapuletu-ci-cd-role-prod` | `prod` |
| `feature/*` | CI Only | N/A | No Deploy |

```

### Pipeline Steps
1. **Linting**: Uses `ruff` to ensure code quality and style consistency.
2. **Testing**: Runs `pytest` for all service and common logic.
3. **Packaging**: Validates the serverless package using `serverless package`.
4. **Deployment**: Deploys to AWS Lambda using `serverless deploy`.

### Security (AWS OIDC)
The pipeline uses **OpenID Connect (OIDC)** to authenticate with AWS. No long-lived AWS Access Keys are stored in GitHub Secrets. 
Ensure the following secrets are configured in GitHub:
- `AWS_ACCOUNT_ID`: Your AWS Account ID.

### Manual Triggers
You can manually trigger any deployment from the **Actions** tab in GitHub by selecting the workflow and clicking **Run workflow**.

### Failure Handling
The pipeline will fail and block deployment if:
- Ruff finds linting issues.
- Any Pytest cases fail.
- `serverless package` validation fails.
- AWS deployment fails.