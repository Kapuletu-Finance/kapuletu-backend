# 🏗️ Kapuletu Treasury Application: Architectural Strategy

## 1. Current State & Architectural Analysis

### Folder Purpose & Distribution
| Folder | Responsibility | Current State |
| :--- | :--- | :--- |
| `alembic/` | Database migrations & versioning | Skeleton |
| `common/` | Shared utilities (DB, Config, Logger, QLDB) | Placeholder logic |
| `events/` | Async event handlers (Task orchestration) | Empty |
| `models/` | Domain Entities (SQLAlchemy) | Incomplete (missing imports) |
| `repositories/` | Data Access Layer | Placeholder logic |
| `schemas/` | Pydantic DTOs (Request/Response) | Skeleton |
| `services/` | Business Logic / Workflows | Entry points defined, logic missing |
| `serverless.yml` | AWS Deployment Manifest | Basic routing defined |

### Architectural Evaluation: "The Clean Skeleton"
The system is logically structured according to **Clean Architecture** principles. It separates domain logic (models) from infrastructure (common) and application workflows (services). However, the implementation is currently in a "draft" phase:
- **Clean Structure**: Excellent separation of concerns.
- **Skeletal Implementation**: Repositories and Services lack functional code.
- **Gaps**: No multi-tenant enforcement, missing Auth/Authz implementation, and incomplete billing logic.

---

## 2. Updated System Architecture (SaaS Ready)

To support Multi-tenancy and Billing, we will expand the structure as follows:

```text
kapuletu-backend/
├── common/
│   ├── middleware/        # NEW: Auth & Tenant isolation
│   ├── database.py        # Centralized SQLAlchemy setup
│   └── exceptions.py      # Domain-specific exceptions
├── models/
│   ├── tenant.py          # NEW: Group/Organization models
│   ├── subscription.py    # NEW: Plans and Usage tracking
│   └── users.py           # Updated: Roles and Permissions
├── repositories/
│   ├── base_repo.py       # NEW: Generic logic + Tenancy filters
│   └── subscription_repo.py
├── services/
│   ├── auth/              # JWT, Hashing, Registration
│   ├── billing/           # Plan validation & Usage tracking
│   └── ledger/            # AWS QLDB Orchestration
└── ... (existing)
```

---

## 3. Database Design Extension

### New SaaS Tables
| Table | Description | Key Columns |
| :--- | :--- | :--- |
| `users` | Primary identities | `user_id`, `email`, `role`, `password_hash` |
| `groups` | Tenancy unit | `group_id`, `owner_id`, `name`, `status` |
| `plans` | Subscription tiers | `plan_id`, `name`, `max_groups`, `max_txns` |
| `subscriptions` | Active user plans | `sub_id`, `user_id`, `plan_id`, `status`, `expiry` |
| `usage_tracking` | Feature consumption | `user_id`, `metric_name`, `current_value` |

### Tenant Isolation Logic
Every repository query for `Transactions`, `Campaigns`, or `Members` **must** include:
- `WHERE group_id = :active_group_id`
- `AND owner_id = :current_user_id`

---

## 4. Full System Flow (Multi-Tenant Financial Lifecycle)

1.  **Onboarding**: User registers via `auth_service` and is assigned a 'Free Trial' plan.
2.  **Tenant Setup**: User creates a 'Group'. The `user_id` becomes the `owner_id`.
3.  **Ingestion**:
    - Twilio message arrives.
    - `ingestion_service` parses the message.
    - System resolves the `owner_id` via the phone number mapping.
    - `pending_transaction` is created with associated `owner_id`.
4.  **Treasurer Review**:
    - Treasurer logs in (JWT issued).
    - Middleware verifies `subscription_status`.
    - Dashboard fetches only transactions where `owner_id == JWT.sub`.
5.  **Finalization**:
    - Treasurer approves/splits.
    - `approval_service` persists to PostgreSQL.
    - `ledger_service` writes to **AWS QLDB** (The "Immutability Event").
    - `billing_service` increments transaction usage count.
6.  **Audit**: Every state change is recorded in the `audit_logs` table with the actor's identity.

---

## 5. Technology Implementation Requirements

- **Auth**: JWT (HS256) with `bcrypt` password hashing.
- **Tenancy**: Identity-based filtering at the Repository level.
- **Ledger**: Synchronous write to QLDB on approval to ensure financial atomicity.
- **Serverless**: Each service is a Lambda function; shared logic resides in the `common/` layer.

> [!IMPORTANT]
> To ensure scalability, the system must use **Database Pooling** sparingly within Lambda or use AWS RDS Proxy, as frequent connections can exhaust Postgres limits during ingestion spikes.
