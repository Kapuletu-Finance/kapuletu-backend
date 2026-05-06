1. MIGRATIONS (DATABASE TRUTH LAYER)

📍 kapuletu-backend/migrations/

These define your actual PostgreSQL tables
(what physically exists in the database)

📄 001_users.sql
CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) CHECK (role IN ('treasurer','admin','super_admin')),
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
📄 002_groups.sql
CREATE TABLE groups (
    group_id UUID PRIMARY KEY,
    owner_id UUID REFERENCES users(user_id),
    group_name VARCHAR(255),
    currency VARCHAR(3) DEFAULT 'KES',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
📄 003_campaigns.sql
CREATE TABLE campaigns (
    campaign_id UUID PRIMARY KEY,
    group_id UUID REFERENCES groups(group_id),
    title VARCHAR(255),
    target_amount DECIMAL(15,2),
    start_date DATE,
    end_date DATE,
    status VARCHAR(20) CHECK (status IN ('active','completed','archived')),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
📄 004_pending_transactions.sql
CREATE TABLE pending_transactions (
    pending_id UUID PRIMARY KEY,
    owner_id UUID REFERENCES users(user_id),
    group_id UUID REFERENCES groups(group_id),
    campaign_id UUID NULL,

    raw_message TEXT,
    message_attachments JSONB,

    source_channel VARCHAR(20),

    source_reference_id VARCHAR(100),
    idempotency_key VARCHAR(100) UNIQUE,

    extracted_code VARCHAR(50),
    extracted_sender_name TEXT,
    extracted_amount DECIMAL(15,2),
    extracted_phone VARCHAR(20),
    extracted_date TIMESTAMP,

    parsing_status VARCHAR(20),
    parser_warning_flag TEXT,
    confidence_score DECIMAL(5,2),

    workflow_status VARCHAR(30),
    assigned_treasurer_id UUID,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
📄 005_review_actions.sql
CREATE TABLE review_actions (
    action_id UUID PRIMARY KEY,
    pending_id UUID REFERENCES pending_transactions(pending_id),
    action_type VARCHAR(20),
    action_by UUID REFERENCES users(user_id),
    internal_note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
📄 006_review_allocations.sql
CREATE TABLE review_allocations (
    allocation_id UUID PRIMARY KEY,
    pending_id UUID REFERENCES pending_transactions(pending_id),
    action_id UUID REFERENCES review_actions(action_id),

    member_name VARCHAR(150),
    member_phone VARCHAR(20),

    allocated_amount DECIMAL(15,2),

    allocation_mode VARCHAR(30),

    allocation_sequence INTEGER,

    created_at TIMESTAMP DEFAULT NOW()
);
📄 007_transactions.sql
CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY,
    pending_id UUID,
    owner_id UUID REFERENCES users(user_id),
    group_id UUID REFERENCES groups(group_id),
    campaign_id UUID REFERENCES campaigns(campaign_id),

    transaction_code VARCHAR(100),
    total_amount DECIMAL(15,2),

    status VARCHAR(20),

    ledger_id VARCHAR(100),

    created_at TIMESTAMP DEFAULT NOW()
);
📄 008_audit_logs.sql
CREATE TABLE audit_logs (
    log_id BIGSERIAL PRIMARY KEY,
    actor_id UUID REFERENCES users(user_id),
    action VARCHAR(50),
    entity_type VARCHAR(50),
    entity_id UUID,

    previous_values JSONB,
    new_values JSONB,

    ip_address VARCHAR(45),

    created_at TIMESTAMP DEFAULT NOW()
);
🟡 2. MODELS (BACKEND ORM LAYER)

📍 kapuletu-backend/models/

These are Python representations of your tables

(usually using SQLAlchemy)

📄 user.py
class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID, primary_key=True)
    full_name = Column(String)
    email = Column(String)
    phone_number = Column(String)
    password_hash = Column(String)
    role = Column(String)
    is_active = Column(Boolean)
📄 group.py
class Group(Base):
    __tablename__ = "groups"

    group_id = Column(UUID, primary_key=True)
    owner_id = Column(UUID)
    group_name = Column(String)
    currency = Column(String)
📄 campaign.py
class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id = Column(UUID, primary_key=True)
    group_id = Column(UUID)
    title = Column(String)
    target_amount = Column(Numeric)
📄 pending_transaction.py
class PendingTransaction(Base):
    __tablename__ = "pending_transactions"

    pending_id = Column(UUID, primary_key=True)
    owner_id = Column(UUID)
    group_id = Column(UUID)

    raw_message = Column(Text)
    extracted_amount = Column(Numeric)

    workflow_status = Column(String)
📄 review_action.py
class ReviewAction(Base):
    __tablename__ = "review_actions"

    action_id = Column(UUID, primary_key=True)
    pending_id = Column(UUID)
    action_type = Column(String)
📄 review_allocation.py
class ReviewAllocation(Base):
    __tablename__ = "review_allocations"

    allocation_id = Column(UUID, primary_key=True)
    pending_id = Column(UUID)
    member_name = Column(String)
    allocated_amount = Column(Numeric)
📄 transaction.py
class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(UUID, primary_key=True)
    transaction_code = Column(String)
    total_amount = Column(Numeric)
    status = Column(String)
📄 audit_log.py
class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id = Column(Integer, primary_key=True)
    action = Column(String)
    entity_type = Column(String)
🔵 3. SCHEMAS (API VALIDATION LAYER)

📍 kapuletu-backend/schemas/

Built using Pydantic

📄 transaction_schema.py
class TransactionIn(BaseModel):
    sender_name: str
    amount: float
    transaction_code: str
    phone: str
📄 approval_schema.py
class ApprovalRequest(BaseModel):
    pending_id: str
    action_type: str  # approve, reject, split
    notes: Optional[str]
📄 allocation_schema.py
class Allocation(BaseModel):
    member_name: str
    amount: float
    mode: str
📄 campaign_schema.py
class CampaignCreate(BaseModel):
    title: str
    target_amount: float
    group_id: str
📄 group_schema.py
class GroupCreate(BaseModel):
    group_name: str
    currency: str = "KES"
📄 user_schema.py
class UserLogin(BaseModel):
    phone_number: str
    password: str
🧠 FINAL ARCHITECTURE UNDERSTANDING
🔁 FULL DATA FLOW
Schema (Pydantic)
    ↓ validates input
Model (SQLAlchemy)
    ↓ backend logic
Migration (SQL)
    ↓ database storage