# 4. Module: AI Parsing Engine (Deep Dive)

The AI Parsing Engine is the core intelligence layer of KapuLetu. It is responsible for ingesting unstructured text messages (e.g., M-Pesa SMS forwards via Meta WhatsApp Cloud API) and transforming them into structured, verifiable financial data.

## 4.1 Ingestion Architecture & Data Flow (`services/ingestion/`)
*   **The Gateway (`handler.py`):** The primary entry point is a Meta WhatsApp Webhook (`POST /webhook`).
    *   *Security:* Authenticates payloads using `hub.verify_token`.
    *   *Normalization:* Handles base64 decoding if required and normalizes sender phone numbers by prepending the `+` prefix to ensure database compatibility.
*   **Asynchronous Decoupling:** The handler intelligently attempts to push incoming payloads to an AWS SQS queue (`SQS_QUEUE_URL`). This decoupling prevents API timeout failures during heavy Natural Language Processing (NLP) loads. If SQS is not configured, it falls back to synchronous processing.
*   **Idempotency & Duplicate Prevention (`service.py`):** To prevent catastrophic double-billing, the service relies on the unique M-Pesa/Bank transaction code extracted from the text. 
    *   *Fallback Logic:* If no transaction code is found (e.g., manual entries), it dynamically generates a deterministic hash: `MD5(user_id + message_body)`.
    *   The `check_duplicate_transaction_code` repository function enforces uniqueness before creating a `PendingTransaction`.

## 4.2 The AI Core & Heuristics (`parser_engine.py`)
*   **Hybrid Intelligence:** KapuLetu uses a two-tiered NLP pipeline based on `spaCy`:
    1.  **Named Entity Recognition (NER):** Attempts to load custom, proprietary weights from `models/kapuletu_ai_v1`. It searches for entities labeled `SENDER`, `AMOUNT`, `CODE`, `PURPOSE`, `PROVIDER`, `DATE`, and `ACCOUNT`.
    2.  **Heuristic Safeguard (Regex):** If the NLP model fails or misses critical data (common with highly unstructured SMS), deterministic regex heuristics act as a safety net (e.g., matching `Ksh` and extracting 10+ character alphanumeric strings for codes).
*   **Confidence Scoring:** Transactions are assigned a `confidence_score`. A score of `1.0` indicates the trained model successfully processed the data, while `0.7` indicates the system had to rely on regex fallbacks.
*   **Data Normalization:** The `_clean_amount` utility function aggressively strips currency symbols, letters, and commas to convert strings like `"Ksh 1,500.00"` into machine-readable floats (`1500.0`).

## 4.3 The Active Learning Loop (Feedback Systems)
The engine is designed to continuously improve based on human feedback from Treasurers.
*   **The Feedback Model (`models/ai_feedback.py`):** When a Treasurer corrects an AI mistake in the dashboard, the system logs the `original_parsed_data` against the `corrected_data`. Admins review these deltas.
*   **Data Labeling (`active_learner.py`):** When a correction is made, this script calculates the exact character start and end offsets of the corrected entity within the raw message text. It compiles this into highly valuable ground-truth training samples (e.g., `{"text": "...", "entities": [(10, 15, "AMOUNT")]}`).
*   **Permanent Memory (`models/parser_knowledge.py`):** This model acts as a structural fingerprint database. If a specific message format is parsed successfully and repeatedly confirmed by Treasurers, its structural logic is saved in a JSON column to bypass heavy NLP on future identical messages.

---

## 4.4 Architectural Flaws, Gaps & Security Risks
*(Audited strictly for Serverless Enterprise Deployment)*

1.  **Ephemeral State Loss (Active Learning):**
    *   *Flaw:* `active_learner.py` writes the expensive ground-truth training data to a local filesystem path (`data/active_learning_pool.json`).
    *   *Risk:* KapuLetu is deployed on AWS Lambda. The local filesystem is ephemeral. When the Lambda container spins down, all active learning training data is permanently deleted. This must be migrated to AWS S3 or a PostgreSQL JSONB column immediately.
2.  **Concurrency & Data Corruption:**
    *   *Flaw:* Even if deployed on a persistent server, `active_learner.py` uses `json.load()` and `json.dump()` sequentially without implementing OS-level file locks.
    *   *Risk:* High-volume concurrent WhatsApp messages will cause race conditions, resulting in corrupted JSON files and completely broken model retraining.
3.  **Synchronous Webhook Timeout Risk:**
    *   *Flaw:* If the SQS decoupling is bypassed or fails, `handler.py` runs the DB queries, SpaCy NLP pipeline, and outgoing Meta API HTTP requests *synchronously* before returning a `200 OK`.
    *   *Risk:* Meta requires webhooks to be acknowledged within seconds. Heavy NLP tasks easily exceed this, causing Meta to retry the webhook repeatedly. This creates massive database load and duplicate processing logs.
4.  **Database Denial of Service (No Spam Protection):**
    *   *Risk:* A malicious actor spamming the WhatsApp bot will cause thousands of un-cached DB queries per minute, effectively executing a Denial of Service (DoS) attack on the RDS instance.

---

## Adjustments, Corrections, and Resolutions
*(End-to-End fixes applied based on the audit)*

### 1. Ephemeral State Loss & Concurrency Fixed (Active Learning)
*   **Fix:** Created the `ActiveLearningSample` PostgreSQL model (`models/ai_feedback.py`) and updated `active_learner.py` to write directly to the database transactionally.
*   **Implementation:** Ground-truth training samples are no longer lost when the AWS Lambda container dies. Furthermore, the Admin dashboard endpoint `POST /admin/v1/ai/parser/train` now fetches these unconsumed SQL records and safely triggers the AI retraining in an isolated background thread.

### 2. Database DoS Protection (TTL Circuit Breaker)
*   **Fix:** Implemented an in-memory TTL dictionary cache inside `repositories/transaction_repo.py` (`resolve_owner_by_phone`).
*   **Implementation:** If an unregistered number messages the WhatsApp bot, it is queried against the DB *once*. The failure is then cached for 5 minutes. Subsequent spam messages from that bot bypass the database entirely and are instantly rejected from memory, preventing RDS exhaustion.

### 3. Synchronous Webhook Timeout Risks Patched
*   **Fix:** Updated the primary Meta Webhook entry point (`services/ingestion/handler.py`).
*   **Implementation:** If the SQS decoupling queue is bypassed or offline, the handler will now automatically spin up a detached Python `threading.Thread` to execute the heavy NLP parsing. The webhook returns a `200 OK` instantly, completely neutralizing the risk of Meta timeout retries.
