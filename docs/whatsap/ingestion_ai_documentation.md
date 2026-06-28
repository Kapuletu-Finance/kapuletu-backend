# KapuLetu Ingestion & AI Module Documentation

## 1. Overview

The KapuLetu Ingestion and AI modules act as the primary gateway for processing incoming transaction notifications (e.g., via SMS or WhatsApp). When a treasurer receives a payment message, this system catches the webhook, verifies the sender, parses the unstructured text using an AI model (with regex fallbacks), checks for duplicates, and creates a "Pending Transaction" for review. Additionally, an Active Learning loop continuously gathers treasurer corrections to improve future AI parsing accuracy.

---

## 2. API Endpoints

The ingestion and validation process is exposed through a set of API endpoints defined in [`local_server.py`](file:///c:/Users/josep/kapuletu-backend/local_server.py).

### Transaction Ingestion Endpoints
- **`POST /ingestion/webhook`**
  - **Purpose**: The primary webhook entry point for Twilio or external SMS/WhatsApp providers. It receives the raw text messages.
  - **Handler**: `services.ingestion.handler.handler`
- **`POST /transactions/manual`**
  - **Purpose**: Allows treasurers to manually log a transaction without relying on automated SMS parsing.
  - **Handler**: `services.ingestion.manual_handler.handler`
- **`GET /transactions/pending`** & **`GET /transactions/pending/{pending_id}`**
  - **Purpose**: Fetches the list of parsed transactions currently awaiting the treasurer's review/approval.
  - **Handler**: `services.approval.handler.handler`

### Parsing & Validation Endpoints
- **`POST /transactions/{pending_id}/reparse`**
  - **Purpose**: Forces the system to re-run the AI parser on a pending transaction (useful if the system was updated or failed the first time).
- **`POST /transactions/{pending_id}/validate`**
  - **Purpose**: Runs validation checks on the transaction data.

---

## 3. The Ingestion Workflow

When a webhook hits `POST /ingestion/webhook`, the following workflow is executed:

1. **Payload Normalization ([`handler.py`](file:///c:/Users/josep/kapuletu-backend/services/ingestion/handler.py))**:
   - The AWS Lambda handler receives the traffic.
   - It decodes the payload (handling Base64, JSON, or Form-Encoded data).
   - It normalizes the phone number (e.g., stripping the `whatsapp:` prefix if the message came from the Twilio WhatsApp API).
   - It initializes the database session and routes the data to the `IngestionService`.

2. **Owner Resolution ([`service.py`](file:///c:/Users/josep/kapuletu-backend/services/ingestion/service.py))**:
   - The `IngestionService` queries the database to ensure the sender's phone number belongs to a registered KapuLetu Treasurer. If no match is found, the request is rejected as unauthorized.

3. **Intelligent Parsing ([`parser_engine.py`](file:///c:/Users/josep/kapuletu-backend/services/ingestion/parser_engine.py))**:
   - The raw message body is passed to the AI Core (`ModelBasedParser`). It extracts structured financial data (Amount, Sender Name, Transaction Code, etc.). 

4. **Idempotency & Duplicate Check**:
   - The system checks if the extracted transaction code (e.g., M-Pesa code) already exists.
   - If no code is present (e.g., a manual entry), it generates a deterministic hash using the Treasurer's ID and the message body.
   - If a duplicate is detected, it is ignored to prevent double-counting.

5. **Persistence**:
   - The successfully parsed message is saved to PostgreSQL as a `PendingTransaction` with a `workflow_status` of "pending". It stores both the parsed fields and the original AI output for audit and feedback loops.

6. **Response**:
   - The handler returns standard TwiML XML to reply to the user via Twilio (e.g., "✅ Success! We received KES 1,500.00 from Jane Doe. It is now pending your approval...").

---

## 4. The AI Parsing Core (`ModelBasedParser`)

The AI module is located in [`parser_engine.py`](file:///c:/Users/josep/kapuletu-backend/services/ingestion/parser_engine.py). It uses a 'Safety-First' hybrid architecture:

1. **Named Entity Recognition (NER)**:
   - The engine uses SpaCy. It attempts to load a proprietary trained model from `models/kapuletu_ai_v1`. 
   - If found, the model identifies contextual entities labeled as `SENDER`, `AMOUNT`, `CODE`, `PURPOSE`, `PROVIDER`, `DATE`, and `ACCOUNT`.
   - If the custom weights are missing or fail to load, it falls back to a blank English SpaCy model.

2. **Heuristic Safeguard (Regex Fallback)**:
   - Because unstructured SMS can be messy and ML models can miss data, a deterministic fallback runs if critical data (Amount, Sender Name, Transaction Code) is missing.
   - It uses common Kenyan financial patterns (e.g., capturing "Ksh 1,500.00" and matching alpha-numeric 10+ character M-Pesa codes).

3. **Data Normalization**:
   - The extracted amounts are sent through a `_clean_amount` utility that removes currency symbols, commas, and errant characters, outputting a clean machine-readable float.

4. **Confidence Scoring**:
   - The output includes a `confidence_score`. Currently, it assigns `1.0` if the trained custom model was used, and `0.7` if it had to rely primarily on heuristic fallbacks.

---

## 5. Active Learning Loop

The AI module gets smarter over time via the **Continuous Learning Module** found in [`active_learner.py`](file:///c:/Users/josep/kapuletu-backend/services/ingestion/active_learner.py).

- When a Treasurer reviews a pending transaction and manually edits a field (for example, correcting a misspelled name or fixing the amount), the system captures this "ground-truth" correction.
- The `log_for_active_learning` function computes the exact character start and end offsets of these corrected values within the original raw text message.
- It formats these as standard NER training samples and appends them to a local JSON pool (`data/active_learning_pool.json`).
- This pool is subsequently used by background workers or admins (via the `POST /admin/v1/ai/parser/train` endpoint) to incrementally fine-tune and retrain the SpaCy AI model weights, creating a powerful self-improving feedback loop.
