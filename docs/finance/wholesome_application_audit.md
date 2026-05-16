# KapuLetu: Wholesome Application Technical Audit

This audit provides a comprehensive overview of the KapuLetu Treasury Management platform, detailing the flow of data, business logic, and security across all modules.

## 1. System Philosophy
KapuLetu is built on the principle of **Financial Verifiability**. Every transaction must be auditable, immutable once finalized, and parsed with high precision using AI to reduce manual entry errors for treasurers.

---

## 2. Module Breakdown & Interaction

### A. Identity & Access (The Foundation)
- **Tech Stack**: AWS Cognito + PostgreSQL.
- **Workflow**:
  - Users register via Cognito.
  - A **Post-Confirmation Lambda** trigger (`services/auth/handler.py`) synchronizes the user into our PostgreSQL `users` table.
  - **RBAC**: Access is governed by roles (Treasurer, Admin) and verified via JWT tokens in the `authorizer` layer of API Gateway.

### B. Ingestion & AI Intelligence (The Gateway)
- **Role**: Converting raw unstructured data (SMS/M-Pesa) into structured financial events.
- **Workflow**:
  - Webhooks (e.g., Twilio) hit `POST /ingestion`.
  - The **AI Parser Module** (built on Spacy/Custom Models) extracts: `Transaction Code`, `Amount`, `Sender Name`, and `Date`.
  - Data is stored in `PendingTransaction` (`models/pending_transaction.py`) awaiting human review.

### C. Approval & Allocation (The Governance)
- **Role**: Ensuring the Treasurer has full control over what enters the ledger.
- **Features**:
  - **Review**: Treasurer can edit AI-extracted details if necessary.
  - **Splitting**: A single transaction can be allocated to multiple members or campaigns using `ReviewAllocation`.
  - **Audit**: Every approval action is logged in `audit_log.py`.

### D. The Verifiable Ledger (PostgreSQL Seal)
- **Role**: Permanent, tamper-proof record keeping within RDS.
- **Tech Stack**: **PostgreSQL (RDS)** with Application-Level Hashing.
- **Security**: Once a transaction is approved, the system generates a **SHA-256 Integrity Seal** (ledger_hash) stored alongside the record. This ensures any manual tampering with historical data can be mathematically detected.

### E. Reporting & Communication (The Output)
- **Role**: Transparency for group members.
- **Output Channels**:
  - **WhatsApp**: Automated summaries sent via Twilio.
  - **Exports**: Professional PDF/Excel reports for formal meetings.
  - **Dashboards**: Real-time progress tracking for campaigns.

---

## 3. End-to-End Data Lifecycle

1.  **Trigger**: An M-Pesa message is received on the Treasurer's phone and forwarded to our webhook.
2.  **Ingestion**: The message is parsed by the AI model. A "Pending" record appears in the Treasurer's inbox.
3.  **Review**: The Treasurer opens the app, verifies the amount, and assigns it to the "Building Fund" campaign.
4.  **Finalization**: The Treasurer clicks "Approve".
5.  **Persistence**: 
    - The record is moved to the **Ledger** (PostgreSQL) and cryptographically sealed with a SHA-256 hash.
    - The **Campaign Balance** is incremented.
    - An **Audit Log** entry is created.
6.  **Notification**: The sender receives a confirmation message, and the Campaign Progress bar updates for all members.

---

## 4. Operational Oversight (Admin Suite)

The **Admin Governance Suite** (`services/admin`) allows platform owners to:
- Monitor **AI Accuracy** and retrain models based on user feedback.
- Manage **Subscription Tiers** and global revenue.
- Handle **Support Tickets** and platform-wide maintenance broadcasts.

---

## 5. Security & Compliance Architecture

- **Data Encryption**: AES-256 at rest (RDS/QLDB).
- **Network**: All internal Lambda-to-DB traffic is within a private VPC.
- **Identity**: Multi-Factor Authentication (MFA) supported via Cognito.
- **Auditability**: Forensic-level logging of every administrative and financial action.
