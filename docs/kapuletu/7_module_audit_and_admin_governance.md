# 7. Module: Audit & Admin Governance

This module acts as the "Super Admin" layer of KapuLetu. It governs the platform's immutable forensic logs and provides system administrators with tools to oversee users, subscriptions, and AI retraining.

## 7.1 The Central Admin Gateway (`services/admin/handler.py`)
Unlike the rest of the KapuLetu application which utilizes FastAPI and Mangum, the Admin module is built as a raw AWS Lambda handler function. It acts as a single gateway that parses incoming API Gateway events and dispatches them to six sub-modules:

*   **Module A (Analytics):** Global platform intelligence and metrics.
*   **Module B (User Lifecycle):** Suspending, activating, or querying Treasurer profiles.
*   **Module C (AI Governance):** Reviewing Treasurer feedback and triggering AI retraining.
*   **Module D (Finance):** Managing subscription plans and manual billing overrides.
*   **Module E (CRM):** Dispatching bulk SMS broadcasts via Africa's Talking.
*   **Module F (Audit):** Searching the immutable forensic database logs.

## 7.2 The Immutable Audit Trail (`services/audit/service.py`)
KapuLetu requires strict tracking of critical actions (e.g., transaction approvals, profile changes, login events) for forensic and compliance purposes.

*   **Data Captured (`AuditLog`):** The system records the `actor_id` (who did it), `action` (e.g., `TXN_APPROVED`), `entity_type`, `entity_id`, and a JSON diff of the `details`.
*   **Decoupled Hooking:** This service is imported and triggered dynamically across all other routers (Auth, Workspace, Finance) whenever a state-changing action occurs.

## 7.3 AI Governance & Feedback Loops (`ai_governance_service.py`)
This service manages the Continuous Integration of the NLP Parser.
*   **The Feedback Queue:** Admins can view a queue of all `AIFeedback` records (corrections made by Treasurers).
*   **Training Sandbox:** Admins can manually inject perfect, synthetic ground-truth samples into the training pool to teach the AI new formats.
*   **Model Deployment:** The system supports a trigger to spawn a retraining script (`train_model.py`) to fine-tune the SpaCy weights.

---

## 7.4 Architectural Flaws, Gaps & Severe Risks
*(Audited strictly for Enterprise Scaling & Security)*

1.  **Serverless Subprocess Failure (AI Governance):**
    *   *Flaw:* To trigger AI retraining, the code attempts to launch a background Python script using `subprocess.Popen(["python", "scripts/train_model.py"])`.
    *   *Risk:* KapuLetu runs on AWS Lambda. When the Lambda function returns the API response, any background subprocesses are immediately frozen or killed by AWS. Furthermore, the Lambda filesystem is mostly read-only. AI retraining will permanently fail in production unless migrated to AWS SageMaker or an asynchronous ECS worker.
2.  **Denial of Service via Continuous Training:**
    *   *Flaw:* If the global config is set to `training_mode == "continuous"`, the system automatically triggers an AI retraining job *every single time* a Treasurer corrects a typo.
    *   *Risk:* In a large platform, this will spawn hundreds of overlapping, CPU-intensive training scripts per hour, crashing the infrastructure and causing massive AWS billing spikes.
3.  **Silent Forensic Failures (Audit Logs):**
    *   *Flaw:* Inside `services/audit/service.py`, if the database write to the `AuditLog` table fails, the code catches the exception, logs it to the terminal, and returns `None`. It **does not re-raise** the exception.
    *   *Risk:* If the audit database is full or offline, a Treasurer can still approve a transaction or change a password, but there will be zero forensic record of it. In a financial system, if the audit trail fails, the business action must gracefully abort to guarantee compliance.
4.  **Brittle, Legacy Routing Logic:**
    *   *Flaw:* The `admin/handler.py` relies on manual, string-based path extraction (e.g., `parts = path.split("/")`, `user_id = parts[parts.index("treasurers") + 1]`).
    *   *Risk:* This is extremely prone to `IndexError` bugs and security bypasses if trailing slashes or URL paths change slightly. It is highly irregular and insecure that this module abandons the robust FastAPI routers used flawlessly in the rest of the application.
