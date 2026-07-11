# Ledger (Immutable) - Audit Report

**Date:** July 11, 2026
**Target Module:** `services/finance` (Ledger) and `models/transaction.py`
**Status:** ✅ Fully Implemented & Cryptographically Secured 

This report covers the mechanics of the immutable ledger, focusing on what happens during transaction approval and how funds are tracked against groups and campaigns.

---

## 1. The Approval Event: Lifecycle of a Transaction

When a treasurer approves a transaction in their inbox (via `approve_transaction` or `split_transaction`), the following immutable sequence occurs:

1. **State Transition (Scratchpad to Permanent)**: 
   The system extracts data from the `PendingTransaction` and initializes a permanent `Transaction` record. The `PendingTransaction` is then marked `is_processed=True`.
2. **Assignment to Group & Campaign**:
   During initialization, the permanent `Transaction` is strictly bound to a `group_id` (required) and optionally a `campaign_id`. These foreign keys establish exactly where the funds belong.
3. **Active Learning Hook**:
   If the user has opted-in to AI training, the final, treasurer-validated amounts and names are fed back into the parsing engine as ground truth.
4. **Cryptographic Sealing (`_write_to_ledger`)**:
   A deterministic JSON payload is constructed containing the transaction details, including its assigned `group_id` and `campaign_id`. A SHA-256 hash is generated from this payload and permanently stored as `ledger_hash`. 
5. **Audit Trail Generation**:
   The `AuditService` records the exact action, actor, and timestamp of the approval.

---

## 2. Campaign & Group Allocation Mechanics

The ledger enforces fund destination rules at the database schema level (`models/transaction.py`):

- **`group_id` (Not Nullable)**: Every single transaction *must* belong to a group. There are no orphan funds.
- **`campaign_id` (Nullable)**: A transaction can optionally be assigned to a specific campaign (e.g., "Medical Fund"). If `campaign_id` is null, the funds are implicitly treated as "General Funds" for the group.

**Split Transactions:**
If a transaction is split (e.g., 1000 KES split into 500 KES for John and 500 KES for Jane), the system creates:
- One parent `Transaction` (sealed and assigned to the group/campaign).
- Multiple child `ReviewAllocation` records detailing the member-level split.

---

## 3. Ledger Retrieval & Integrity Engine

The `LedgerService` (`services/finance/ledger_service.py`) ensures that the ledger remains a source of absolute truth.

### On-The-Fly Tamper Detection
Whenever the ledger is queried (e.g., via `GET /ledger/campaign/{campaign_id}`):
1. The service fetches all transactions for the campaign.
2. It **recalculates the SHA-256 hash** for every single transaction on-the-fly.
3. It compares the recalculated hash to the stored `ledger_hash`.
4. If a record has been tampered with directly in the database (e.g., someone altered the amount), the hashes will mismatch. 

### Financial Protection
Only mathematically verified, non-tampered transactions are summed up. If a transaction is tampered with, it is flagged as `is_tampered = True` in the API response and strictly excluded from the `total_raised` campaign calculations. 

### Endpoints Verified
- `GET /ledger`: Complete global ledger.
- `GET /ledger/campaign/{campaign_id}`: Retrieves ledger filtered by `campaign_id`, computing a real-time `CampaignLedgerSummaryOut` (Target Amount vs. Total Raised).
- `GET /ledger/verify/{transaction_id}`: Performs a deep cryptographic audit on a single transaction to confirm its integrity.

---

## Conclusion
The Ledger module provides a robust, mathematically verifiable source of truth. The flow of funds into specific campaigns is securely handled via strict foreign key constraints during the approval step, and protected against post-approval tampering via SHA-256 hashing.
