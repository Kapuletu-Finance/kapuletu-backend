# KapuLetu Finance Ledger Module: Technical Overview

## Executive Summary
The Finance Ledger Module acts as the immutable "Source of Truth" for all finalized financial transactions within the KapuLetu ecosystem. It is designed to provide treasurers with an aggregate, mathematically verifiable view of campaign funds. The core innovation of this module is its continuous, on-the-fly cryptographic auditing capability, ensuring that no internal or external party can silently modify historical financial records.

## Core Functionality

### 1. Cryptographic Integrity Verification (Anti-Tamper Mechanism)
Financial integrity is the highest priority for the Ledger Module. To achieve this, it employs a deterministic hashing algorithm:

- **Seal Generation:** When a transaction is initially approved (via the Approval Module), a deterministic JSON payload containing all vital financial data (Amount, Target Phone, Status, Timestamp) is created and passed through a SHA-256 algorithm. The resulting hash is saved as the `ledger_hash`.
- **On-The-Fly Auditing:** Whenever the Ledger API is queried, the `LedgerService` extracts the raw database row and forces it back through the identical SHA-256 algorithm. 
- **Tamper Detection:** The module compares the freshly generated hash against the original `ledger_hash`. If a database administrator or malicious actor alters an underlying record directly in PostgreSQL, the hashes will no longer match. The module will immediately flag the record via the `is_tampered` boolean flag in the API response, alerting the organization to a data breach.

### 2. Campaign-Level Aggregation
The Ledger Module provides dynamic financial summaries scoped to specific community goals (Campaigns). When a specific campaign ledger is requested, the module processes the verified transactions and calculates:
- **Total Amount Raised**
- **Total Approved Transactions**
- **Progress Percentage** (Calculated against the campaign's predefined `target_amount`)

*Note: If a transaction is flagged as tampered, it is automatically excluded from the "Total Amount Raised" calculations to prevent corrupted data from inflating the treasury balance.*

## API Endpoints & Schemas

The module exposes three primary REST endpoints, fully integrated into the OpenAPI (Swagger) documentation and protected by JWT authentication.

### `GET /ledger`
- **Purpose:** Returns the global ledger containing all approved transactions authorized by the requesting treasurer.
- **Response Schema (`LedgerResponse`):** Returns a flat list of `LedgerEntryOut` objects.

### `GET /ledger/campaign/{campaign_id}`
- **Purpose:** Filters the ledger to a specific campaign and injects the dynamic aggregations.
- **Response Schema (`LedgerResponse`):** 
  - `summary`: A `CampaignLedgerSummaryOut` object containing the `total_raised`, `target_amount`, and `progress_percentage`.
  - `entries`: A list of `LedgerEntryOut` objects specific to this campaign.

### `GET /ledger/verify/{transaction_id}`
- **Purpose:** A dedicated forensic tool for deep-auditing a single transaction.
- **Response Schema (`IntegrityCheckOut`):** Returns the transaction ID, the original hash, the freshly recalculated hash, and an `is_valid` boolean flag indicating whether the cryptographic seal remains unbroken.

## Technical Architecture (Files & Services)
- **`services/finance/schemas.py`**: Defines the strict Pydantic response models, ensuring consistent output and documentation.
- **`services/finance/ledger_service.py`**: Houses the core business logic, including the `_recalculate_hash()` engine and the SQL queries responsible for fetching and aggregating transaction data.
- **`services/finance/ledger_router.py`**: The FastAPI routing layer that connects HTTP requests to the underlying `LedgerService` logic.
