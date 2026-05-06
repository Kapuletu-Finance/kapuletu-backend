# Local Database Infrastructure Documentation

This document provides a comprehensive technical breakdown of how the local database environment for the KapuLetu Backend was established, the tools used, and the commands involved in maintaining it.

---

##  1. Infrastructure: Docker & PostgreSQL

We utilize **Docker Compose** to provision a consistent, isolated PostgreSQL environment. This ensures that every developer has the exact same database version and configuration without manual installation.

### Configuration (`docker-compose.yml`)
The database is configured to run on a non-standard port to avoid conflicts with other PostgreSQL instances that might be running on the host machine.

- **Image**: `postgres:15-alpine` (Lightweight and stable)
- **Container Name**: `kapuletu_db`
- **Host Port**: `5433`
- **Container Port**: `5432`
- **Credentials**:
  - `POSTGRES_USER`: `postgres`
  - `POSTGRES_PASSWORD`: `password`
  - `POSTGRES_DB`: `kapuletu`

### Docker Commands
- **Start the database**:
  ```powershell
  docker-compose up -d
  ```
- **Stop the database**:
  ```powershell
  docker-compose down
  ```
- **Stop and wipe all data (Reset)**:
  ```powershell
  docker-compose down -v
  ```
- **Check logs**:
  ```powershell
  docker logs kapuletu_db
  ```

---

##  2. Migration Management: Alembic

**Alembic** is our database migration tool for SQLAlchemy. It tracks changes to our Python models and applies them to the PostgreSQL schema.

### Setup & Configuration
1.  **Initialization**: `alembic init alembic` was run to create the migration environment.
2.  **Environment Integration**: `alembic/env.py` was modified to:
    - Load connection strings directly from our `common/config.py`.
    - Import the centralized SQLAlchemy `Base.metadata` to enable **autogenerate** support.
3.  **Connection Logic**: We use `127.0.0.1` instead of `localhost` in the connection string to prevent IPv6 authentication failures common on Windows/Docker environments.

### Alembic Commands
- **Create a new migration (Autogenerate)**:
  ```powershell
  .\venv\Scripts\alembic revision --autogenerate -m "Description of changes"
  ```
- **Apply migrations to the database**:
  ```powershell
  .\venv\Scripts\alembic upgrade head
  ```
- **Check current migration status**:
  ```powershell
  .\venv\Scripts\alembic current
  ```

---

##  3. Architectural Improvements

To make the database work reliably, several changes were made to the core application structure:

### Centralized SQLAlchemy Base
We moved the `Base = declarative_base()` definition to a dedicated file: `models/base.py`.
- **Reason**: This prevents circular import errors (e.g., between `User` and `Group`) and ensures that Alembic can "see" all tables through a single metadata object.

### Model Fixes
Several models were missing explicit ForeignKeys and relationships required for complex queries:
- **Campaign**: Added `ForeignKey("groups.group_id")` and `relationship("Group")`.
- **ReviewAllocation**: Added `ForeignKey("transactions.transaction_id")` and `relationship("Transaction")`.
- **Transaction**: Added `ForeignKey("campaigns.campaign_id")` and fixed duplicate imports.

### SSL Handling
Updated `common/database.py` to allow non-SSL connections specifically for local development:
```python
connect_args={"sslmode": "require"} if all(h not in config.DATABASE_URL for h in ["localhost", "127.0.0.1"]) else {}
```

---

##  4. Data Seeding

We use a custom script to populate the database with essential data required for the application to function.

- **Command**:
  ```powershell
  $env:PYTHONPATH="."
  .\venv\Scripts\python scripts\seed_data.py
  ```
- **What it does**:
  1.  Creates default **Subscription Plans** (`Basic` and `Pro`).
  2.  Creates a **System Administrator** user.
  3.  Assigns the administrator a default subscription.

---

##  5. Summary of Environment Variables

Current `.env` configuration for local development:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://postgres:password@127.0.0.1:5433/kapuletu` | Main DB connection string |
| `APP_ENV` | `development` | Switches app logic to dev mode |
| `SECRET_KEY` | `supersecret` | JWT/Session security key |
| `QLDB_LEDGER_NAME` | `kapuletu-ledger` | Local mock/dev ledger name |

---

## Troubleshooting
- **Authentication Failed**: Ensure you are using port `5433`. A local Postgres installation might be "squatting" on port `5432`.
- **ModuleNotFoundError**: Always set `$env:PYTHONPATH="."` when running scripts from the root directory so Python can find the `common` and `models` packages.
