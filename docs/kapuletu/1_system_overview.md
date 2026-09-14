# 1. System Overview

## 1.1 Core Architecture & Principles
The KapuLetu Treasury Backend is designed to act as an intelligent, secure, and auditable assistant for community treasurers. The architecture is primarily built on an **Event-Driven, Serverless** model.

### Key Tenets
1.  **Treasurer-First:** The system does not assume autonomous control over finances. Instead, it extracts data, organizes it, and relies entirely on human validation (the Treasurer) before any financial record is committed.
2.  **Serverless Scaling:** The backend is written in Python (using FastAPI for structure) but runs on AWS Lambda triggered by API Gateway and SQS. This ensures it scales cost-effectively based on incoming transaction volume.
3.  **Self-Hashed Immutable Ledger:** Instead of relying on external managed ledgers, KapuLetu utilizes cryptographic self-hashing to ensure that once a transaction is approved, its record is immutable and fully auditable.

## 1.2 The 4-Stage Transaction Lifecycle
Every transaction moving through KapuLetu follows a strict, traceable pipeline:

1.  **Ingestion (Data Capture):** 
    *   Triggered primarily via webhooks from the **WhatsApp Cloud API (Meta)**, capturing unstructured payment confirmation messages.
    *   The system can also accept manual entry.
2.  **Intelligence Layer (Parsing):**
    *   An NLP/Regex-powered engine extracts vital entities (Sender Name, Phone Number, Amount, Transaction Code).
    *   This data is stored as a "Pending Transaction".
3.  **Review & Approval:**
    *   The Treasurer reviews the parsed data in their Pending Inbox.
    *   They can approve, reject, edit, or split the amount among multiple members. This stage is fully audited (every click/action is recorded).
4.  **Ledger Finalization:**
    *   Approved transactions are written to the final `transactions` table.
    *   A cryptographic hash is generated for the entry to ensure historical integrity and immutability.

## 1.3 Database Architecture (The 4 Layers)
The PostgreSQL database schema is logically divided into four distinct layers to separate identity, state, and immutable truth.

### Layer 1: Identity & Ownership
*   **Users:** System access is managed via the `users` table, which holds Treasurers and Admins.
*   *Critical Rule:* The Treasurer's phone number is the primary routing key that maps incoming Meta WhatsApp messages to the correct workspace.

### Layer 2: Context (Groups & Campaigns)
*   **Groups:** A single Treasurer can manage multiple distinct groups (e.g., Church Fund, Welfare Group).
*   **Campaigns:** Specific fundraising goals within a group. If only one campaign is active, transactions are auto-routed to it; otherwise, the treasurer allocates them.

### Layer 3: Transaction Pipeline
*   **pending_transactions:** The noisy inbox holding raw messages and AI predictions.
*   **review_actions & review_allocations:** The audit trail of human intervention (edits, splits).
*   **transactions:** The finalized, clean snapshot of financial facts.

### Layer 4: Immutable Ledger & Reporting
*   **Self-Hashed Ledger:** The ultimate source of truth, enforcing append-only financial records via hashing.
*   **Reporting:** A presentation layer that queries the clean transaction table to generate PDF, Excel, and WhatsApp-ready summaries.

## 1.4 Flexibility Over Rigidity
A defining feature of KapuLetu is its avoidance of strict pre-requisites for member management. There is no forced "Members Table" that blocks transactions. When a payment arrives from an unknown person, the NLP engine parses the name from the message, and the Treasurer confirms it. This flexibility perfectly mirrors the chaotic reality of community finance.
