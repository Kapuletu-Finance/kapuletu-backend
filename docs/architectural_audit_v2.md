# 🏗️ Kapuletu Treasury Backend: Architectural Audit & Clean Design

## STEP 1 — ARCHITECTURAL AUDIT

### Folder Responsibilities (Current State)
| Folder | Purpose | Quality Assessment |
| :--- | :--- | :--- |
| `alembic/` | DB schema evolution | Essential. Well-standardized. |
| `common/` | Shared kernel (DB, Auth, Config, Middleware) | **Well-designed**: The recent addition of Lambda decorators (`decorators.py`) and a centralized `database.py` session factory provides a solid foundation for serverless scalability. |
| `events/` | Async event dispatching | **Incomplete**: Placeholder for post-approval tasks (e.g., QLDB writes triggered by SNS/SQS). |
| `models/` | Domain Entities (SQLAlchemy) | **Well-designed**: Recent unification of tables (`users`, `groups`, `transactions`) with common `Base` and `owner_id` scoping is correct. |
| `repositories/` | Data Access Layer | **Hybrid**: `base_repo.py` correctly enforces tenancy. Specific repos (member, transaction) are still skeletal. |
| `schemas/` | Pydantic Request/Response validation | **Incomplete**: Only basic skeletons exist. Lacks complex validation for "split" allocations. |
| `services/` | Business Workflows | **Incomplete**: Entry points exist, but the "Allocation Engine" and "Idempotency Layer" are missing. |
| `serverless.yml` | AWS Lambda Orchestration | **Well-designed**: Standard and maps logically to service folders. |

### Gaps & Risks
- **Idempotency**: No mechanism to prevent duplicate MPESA/Twilio messages from creating double entries.
- **Identity Resolution**: The mapping between Twilio's `From` number and the `owner_id` (Treasurer) needs a formal lookup strategy (likely in `users` or a dedicated `treasurer_phones` table).
- **Member Inference**: The system currently has a `Member` model. We must ensure this is used as a *lookup index* for financial records, not a login-able entity.

---

## STEP 2 — FINAL CLEAN ARCHITECTURE DESIGN

### Refined Folder Structure
We will stick to the current layout but enforce strict **Unidirectional Dependency**:
`Handlers -> Services -> Repositories -> Models`

```text
kapuletu-backend/
├── common/
│   ├── auth.py            # Phone-based JWT resolution
│   ├── decorators.py      # @with_auth, @idempotent
│   └── qldb.py            # QLDB Driver management
├── services/
│   ├── ingestion/         # TWILIO Entry (Stateless, Idempotent)
│   ├── approval/          # TREASURER Decision engine
│   ├── allocation/        # NEW: Logic for splitting txns
│   └── reporting/         # Aggregation engine
├── repositories/
│   ├── base_repo.py       # Scoped by owner_id
│   ├── transaction_repo.py
│   └── ledger_repo.py     # QLDB-specific repo logic
└── ... (existing)
```

---

## STEP 3 — CORE SYSTEM FLOW (DETAILED)

| Phase | Actor / Trigger | Action | Storage Touched |
| :--- | :--- | :--- | :--- |
| **Ingestion** | Twilio Webhook (HTTP POST) | 1. Resolve Treasurer via Phone<br>2. Check MPESA Code Idempotency<br>3. Parse Message | PostgreSQL (`pending_transactions`) |
| **Queue** | Background | Transaction sits in Treasurer's Inbox | PostgreSQL |
| **Review**| Treasurer (Dashboard) | Treasurer edits, rejects, or splits the record | PostgreSQL (`review_actions`) |
| **Allocation**| Allocation Engine | Logic calculates split amounts and targets (Members) | PostgreSQL (`review_allocations`) |
| **Finalization**| Approval Service | **The Atomic Event**: Write final state to DB and Ledger | Postgres (`transactions`) + **AWS QLDB** |
| **Audit** | Interceptor | Log: `Treasury X approved Txn Y at T` | PostgreSQL (`audit_logs`) |

- **Lambda Service**: Each `service/` handler runs as its own Lambda.
- **Triggers**: Ingestion is triggered by Twilio; Approval/Reporting by Dashboard API calls.

---

## STEP 4 — IMPLEMENTATION PLAN

1.  **Identity & Security**: Implement `phone_number` lookup in `auth_service`. Ensure JWT `sub` is always the `owner_id`.
2.  **Idempotency Layer**: Implement a check against `transaction_code` in `pending_transactions` to drop duplicates.
3.  **The Inference Engine**: Update `MemberRepository` to `get_or_create` members based on phone/name found in messages (Inferred context).
4.  **Allocation Service**: Build service to handle 1:N splits (1 Payment -> Multiple Members/Campaigns).
5.  **Ledger Pipeline**: Formalize the synchronous write to Amazon QLDB upon approval success.
6.  **Reporting**: Build aggregate views for "Total by Campaign" and "Total by Member".

---

## STEP 5 — CODE STRUCTURE REFINEMENT (Rules)

- **Repositories**: All queries MUST use `BaseRepository.get_all(owner_id=...)`. **Total tenant isolation.**
- **Services**: Services must be **Stateless Helpers**. They take a `db` session and `data`, perform logic, and return models.
- **Audit**: Every service call that modifies state must call `AuditService.log(action, owner_id)`.

---

## STEP 6 — DESIGN ENFORCEMENT RULES

1.  **Idempotency**: Use the unique Transaction ID from the message (e.g., MPESA Code) as an idempotency key.
2.  **No Direct Access**: `handler.py` NEVER touches the DB. It calls `service.py`, which uses a `repository`.
3.  **Financial Immutability**: Once `status == 'approved'`, the record in PostgreSQL is read-only (enforced by code/triggers), and the source of truth is the **QLDB Ledger**.
