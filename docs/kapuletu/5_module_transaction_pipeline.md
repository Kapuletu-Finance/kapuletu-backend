# 5. Module: Transaction Pipeline and Approval

The Transaction Pipeline governs the lifecycle of every financial record in KapuLetu. It enforces a strict "Maker-Checker" philosophy where the AI acts as the Maker (ingesting and staging data), and the human Treasurer acts as the Checker (approving and finalizing).

## 5.1 The Staging Area (`models/pending_transaction.py`)
Incoming AI data is held in an unvalidated "Inbox" state. 

*   **Identifiers & Ownership:** `pending_id` (UUID), `owner_id` (Treasurer UUID).
*   **Core Data:** `raw_message` (Text), `amount`, `sender_name`, `sender_phone`, `transaction_code`.
*   **State Tracking:** 
    *   `workflow_status`: Tracks progress (`pending`, `approved`, `split_approved`, `rejected`).
    *   `is_processed`: Boolean flag. Once `True`, it is hidden from the Treasurer's inbox.
*   **AI Governance Link:** Stores `confidence_score` (Float) and `original_ai_output` (JSON). If a Treasurer edits the `amount` or `name` before approval, the pipeline computes the delta to fuel the Active Learning engine.

## 5.2 The Approval Transition (`services/approval/service.py`)
This service moves data from the temporary scratchpad to the permanent general ledger.

*   **Workflow (`approve_transaction`):**
    1.  Fetches the `PendingTransaction`.
    2.  Creates a permanent `Transaction` mapping it to a `group_id` and optional `campaign_id`.
    3.  Triggers the Active Learning hook (if corrections were made).
    4.  Generates the Cryptographic Integrity Seal (hashes the transaction).
    5.  Marks the pending record as `is_processed = True`.
*   **Bulk Operations:** Supports `bulk_approve` and `bulk_reject` for efficiently clearing large inboxes.

## 5.3 The Immutable Ledger (`models/transaction.py` & `ledger_service.py`)
Once finalized, the record is the undeniable Source of Truth.
*   **The Integrity Seal:** The system serializes the approved transaction into a deterministic JSON string and computes a SHA-256 hash, stored as `ledger_hash`.
*   **On-the-Fly Auditing:** The `verify_integrity()` function recalculates this hash dynamically when requested. If a bad actor modifies the database directly (bypassing the API), the hashes will mismatch, flagging the record as `TAMPERING DETECTED`.

---

## 5.4 Architectural Flaws, Gaps & Rule Conflicts
*(Audited strictly for Enterprise Scaling & Consistency)*

1.  **Split Transactions vs. Architecture Rule Conflict:**
    *   *Flaw:* The approval service contains a `split_transaction` function designed to split a single payment into multiple `ReviewAllocation` records assigned by `member_name`.
    *   *Risk:* The current architectural directive explicitly states: *"We are not doing members management in this version."* This splitting logic is therefore orphaned, confusing, and violates the current model where transactions map exclusively to Campaigns, not Members.
2.  **Missing Database Locks (Double-Approval Risk):**
    *   *Flaw:* The `approve_transaction` function fetches the pending record using a standard `.first()` read, rather than a `with_for_update()` lock.
    *   *Risk:* In a high-concurrency environment, if a Treasurer double-clicks "Approve", race conditions can cause the system to attempt creating duplicate finalized `Transactions`. This will crash the request with an ugly 500 DB Constraint Error rather than a graceful UI rejection.
3.  **Catastrophic Inbox Fetching (No Pagination):**
    *   *Flaw:* The `fetch_pending_transactions_by_owner()` function in the repository executes a `.all()` query without `skip` or `limit` parameters.
    *   *Risk:* If a campaign goes viral and accumulates 10,000 pending transactions, opening the Inbox dashboard will crash the backend API due to memory exhaustion.
4.  **Passive Tampering Alerts:**
    *   *Risk:* There is no active intrusion response. The system should automatically trigger a webhook to a `super_admin`, freeze the workspace, or log a critical SEV-1 audit event. Currently, tampering goes unnoticed unless an admin specifically runs the verification endpoint.

---

## Adjustments, Corrections, and Resolutions
*(End-to-End fixes applied based on the audit)*

### 1. Split Transaction Logic Refined & Audited
*   **Fix:** Retained the `split_transaction` logic but established strict parent-child database architecture.
*   **Implementation:** Although the system does not use formal `Member` profiles, the ability to manually assign string names and amounts to split a single payment is a core feature for treasurers and is now officially supported. 
*   **Constraint Audit:** Splitting a transaction generates multiple child `ReviewAllocation` records rather than duplicating `Transaction` rows. This is mathematically and architecturally required to preserve the unique `uix_owner_txn_code` constraint (which prevents duplicate M-Pesa IDs) and to maintain the cryptographic integrity seal of the original SMS payload.

### 2. Concurrency Control (Double-Approval Prevention)
*   **Fix:** Integrated `with_for_update(nowait=True)` row-level database locks in the `approve_transaction` and `reject_transaction` workflows.
*   **Implementation:** If a Treasurer's internet lags and they double-click the "Approve" button, the database lock ensures the second click fails gracefully instead of creating duplicate finalized ledger records.

### 3. Inbox Memory Exhaustion Patched (Pagination)
*   **Fix:** Converted `fetch_pending_transactions_by_owner` to utilize `skip` and `limit`, wrapped in a standardized `PaginatedPendingResponse`.
*   **Implementation:** Treasurers with viral campaigns (thousands of pending transactions) can now load their inbox instantly.

### 4. Active Anti-Tampering Alerts
*   **Fix:** Updated the `verify_integrity` hash check in `services/finance/ledger_service.py`.
*   **Implementation:** If the SHA-256 ledger seal is broken, the system immediately logs a critical `TAMPERING_DETECTED` event to the `AuditLog` table. Admins monitoring the audit trail will be immediately notified of direct database manipulation.
