1. WHERE THE SCHEMA LIVES (BIG PICTURE)

The  schema is implemented in three physical places:

🟢 1. Database Migration Files (SOURCE OF TRUTH)
📍 Location:
kapuletu-backend/
└── migrations/
    ├── 001_users.sql
    ├── 002_groups.sql
    ├── 003_campaigns.sql
    ├── 004_transactions.sql
    └── ...

OR (if using Python tooling):

kapuletu-backend/
└── alembic/
    └── versions/
💡 What goes here:

This is where your actual SQL schema lives

Example:

CREATE TABLE users (
  user_id UUID PRIMARY KEY,
  full_name VARCHAR(255),
  phone_number VARCHAR(20) UNIQUE
);
Why this matters:

This is the real database blueprint

👉 If you delete everything else, THIS still defines your system

🧠 2. BACKEND DOMAIN MODELS (APPLICATION LAYER)
📍 Location:
kapuletu-backend/
└── models/
    ├── user.py
    ├── group.py
    ├── campaign.py
    ├── transaction.py
💡 What this is:

These are Python representations of your schema

If using ORM (recommended):

👉 SQLAlchemy

Example:
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID, primary_key=True)
    amount = Column(DECIMAL)
    status = Column(String)
🔥 Purpose:
backend logic uses these objects
API reads/writes through them
avoids raw SQL everywhere

3. SCHEMA CONTRACTS (API / VALIDATION LAYER)
 Location:
kapuletu-backend/
└── schemas/
    ├── transaction_schema.py
    ├── approval_schema.py
    ├── campaign_schema.py
 What this is:

These define:
👉 what data is allowed in/out of the system

Usually built with:

👉 Pydantic

Example:
class TransactionCreate(BaseModel):
    amount: float
    sender_name: str
    transaction_code: str
🔥 Purpose:
validate incoming messages
ensure API safety
enforce structure BEFORE DB
 4. HOW THESE 3 WORK TOGETHER

This is the MOST important part:

🔁 FLOW OF DATA
1. Schema (Pydantic)
        ↓ validates input
2. Model (ORM)
        ↓ represents object in backend
3. Migration (SQL)
        ↓ stores in database
 Example: Incoming transaction
Step 1: API receives message

→ validated by schema

Step 2: backend converts it to model

→ Transaction object created

Step 3: model is saved to DB

→ migration-defined table is used

 5. WHERE YOUR CURRENT SCHEMA FITS

Now mapping your entire design:
 Migration Layer (SQL DEFINITIONS)

This includes:

users
groups
campaigns
pending_transactions
review_actions
review_allocations
transactions
audit_logs

 ALL OF THESE GO HERE:

migrations/*.sql
🟡 Models Layer (Python ORM)

You will have:

models/

Mapping:

SQL Table	Python Model
users	User
groups	Group
campaigns	Campaign
transactions	Transaction
pending_transactions	PendingTransaction
 Schemas Layer (API contracts)
schemas/

Used for:

ingestion input
approval requests
reporting outputs
 6. IMPORTANT DESIGN TRUTH

Your schema is NOT just one thing.

It is:

🧠 A contract split across DB + backend + API


 Migration = “Where data lives”
actual database tables
🧠 Models = “How backend thinks about data”
Python objects
📡 Schemas = “What is allowed in/out”
validation layer
