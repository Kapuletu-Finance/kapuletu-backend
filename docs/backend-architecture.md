KapuLetu Treasury Backend Architecture & System Design
1. Introduction
This document provides a comprehensive overview of the KapuLetu Treasury Application backend architecture. It explains the system design, technology stack, AWS Lambda concept, event-driven architecture, and the full backend folder structure.
2. Problem Overview
The KapuLetu system addresses inefficiencies in managing community financial contributions. Current systems rely on manual processes such as WhatsApp messages, SMS confirmations, spreadsheets, and memory, leading to errors, duplication, and lack of auditability.
3. Solution Overview
KapuLetu is designed as an intelligent assistant for treasurers. It captures transactions, structures them, enables verification workflows, stores immutable records, and automates reporting.
4. Key Architecture Principles
• Event-Driven System: The system reacts automatically to incoming payment messages.
• Serverless Architecture: No servers are managed manually; compute runs on demand.
• Modular Services: The system is divided into ingestion, approval, and reporting services.
• Auditability: All approved transactions are stored in an immutable ledger.
5. AWS Lambda Explanation
AWS Lambda is a serverless compute service that runs code in response to events. Instead of running a server continuously, Lambda functions execute only when triggered (e.g., by a webhook). This reduces cost and simplifies scaling.
6. Event Flow
1. A user sends a payment confirmation via WhatsApp/SMS.
2. Twilio forwards the message to an API endpoint.
3. AWS API Gateway triggers a Lambda function.
4. The ingestion service parses and stores the transaction.
5. The treasurer reviews and approves the transaction.
6. Approved transactions are written to the ledger.
7. Reports are generated automatically.
7. Technology Stack
Backend: Python 3.11
Framework Style: FastAPI principles
Compute: AWS Lambda
API Layer: API Gateway
Database: PostgreSQL (RDS)
Ledger: QLDB
Storage: S3
Messaging: Twilio
NLP: spaCy
Linting: Ruff
8. Backend Folder Structure
The backend follows a modular structure with separate services and shared utilities.

kapuletu-backend/
├── serverless.yml
├── requirements.txt
├── common/
├── services/
│   ├── ingestion/
│   ├── approval/
│   ├── reporting/
├── models/
├── repositories/
├── events/
├── tests/
├── scripts/


9. Services Explanation
Ingestion Service: Handles incoming messages and parses them into structured data.
Approval Service: Allows treasurer to approve/reject transactions and ensures validation.
Reporting Service: Generates summaries, Excel, and PDF reports.
10. Database Design
PostgreSQL stores pending and operational data.
QLDB stores immutable approved transactions.
This separation ensures both flexibility and audit integrity.
11. System Benefits
• Reduced manual workload
• Improved accuracy
• Strong audit trail
• Scalable architecture
• Real-time reporting
12. Conclusion
The KapuLetu backend leverages modern serverless architecture and event-driven design to build a scalable, reliable, and auditable treasury management system suitable for community financial operations.
