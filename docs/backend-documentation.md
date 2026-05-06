KapuLetu Treasury System - Comprehensive Backend Documentation
1. Problem Statement
Community finance groups rely on fragmented tools such as WhatsApp, SMS, spreadsheets, and manual record keeping.
This creates inefficiencies, errors, duplication, lack of auditability, and high treasurer workload.

Key challenges:
- Scattered transaction records
- High risk of missing transactions
- Duplicate entries
- No structured approval workflow
- Weak audit trail
- Poor handling of group contributions
- Reporting fatigue


2. Solution Overview
KapuLetu is an intelligent treasury assistant system designed to:
- Capture transactions automatically
- Structure financial records
- Enable approval workflows
- Maintain immutable ledgers
- Automate reporting


3. Backend Architecture Overview
The backend is designed using a serverless, event-driven architecture.

Core principles:
- Event-driven processing
- Modular services
- Serverless execution
- Strong audit and data integrity


4. AWS Lambda Explanation
AWS Lambda is a serverless compute service that runs code only when triggered by an event.
It eliminates the need to manage servers.

Flow:
1. Event occurs (e.g., message received)
2. Lambda function executes
3. Function completes and stops

Benefits:
- No server management
- Auto scaling
- Pay per execution


5. End-to-End System Flow
1. User sends payment confirmation via WhatsApp/SMS
2. Twilio forwards message to backend
3. API Gateway triggers ingestion Lambda
4. Message is parsed into structured data
5. Transaction stored as Pending
6. Treasurer reviews via frontend
7. Approval Lambda validates and processes transaction
8. Approved transaction stored in immutable ledger
9. Reporting service generates summaries and exports


6. Backend Folder Structure Overview
kapuletu-backend/
- serverless.yml: Deployment configuration
- requirements.txt: Dependencies
- common/: Shared utilities
- services/: Core business services
- models/: Data structures
- repositories/: Database access
- events/: Event handling
- tests/: Testing
- scripts/: Utility scripts


7. Common Layer
database.py: Handles PostgreSQL connections
qldb.py: Handles ledger database operations
config.py: Loads environment configuration
logger.py: Central logging system
auth.py: Authentication and role management
utils.py: Helper utilities


8. Services Layer
8.1 Ingestion Service
Responsible for receiving and parsing incoming messages.

Files:
- handler.py: Entry point triggered by webhook
- parser_engine.py: Extracts structured data
- schemas.py: Defines data structures
- validators.py: Validates input


8.2 Approval Service
Handles treasurer decisions and validation.

Files:
- handler.py: Triggered on approval/rejection
- service.py: Core business logic
- validator.py: Fraud and duplicate checks
- schemas.py: Request structure


8.3 Reporting Service
Generates financial outputs.

Files:
- handler.py: Entry point
- daily_summary.py: Summary generation
- excel_gen.py: Excel exports
- pdf_gen.py: PDF generation


8.4 Members Service
Manages contributors.

Files:
- handler.py: API endpoints
- service.py: Logic
- schemas.py: Data structure


8.5 Campaigns Service
Manages fundraising campaigns.

Files:
- handler.py
- service.py
- schemas.py


9. Models Layer
Defines core entities:
- transaction.py
- member.py
- campaign.py
- ledger_entry.py


10. Repository Layer
Handles database interactions:
- transaction_repo.py
- member_repo.py
- campaign_repo.py


11. Events Layer
Handles internal system communication:
- event_bus.py
- transaction_events.py


12. Testing
Ensures system reliability:
- test_ingestion.py
- test_approval.py
- test_reporting.py


14. CI/CD Pipeline
The system uses GitHub Actions for automated quality assurance and deployment.

Key Features:
- **Multi-environment support**: Dev, Staging, and Production stages.
- **Automated Testing**: Runs pytest on every push and PR.
- **Linting**: Uses Ruff to maintain high code quality standards.
- **Secure Authentication**: Uses AWS OIDC (OpenID Connect) for secure, keyless deployments.
- **Branch Protection**: Enforces quality checks before merging into main branches.

Deployment Flow:
- `dev` branch -> Deploys to AWS `dev` stage.
- `staging` branch -> Deploys to AWS `staging` stage.
- `production` branch -> Deploys to AWS `prod` stage.
- `feature/*` branches -> Runs CI tests only.

15. System Benefits
- Reduced manual work
- Improved accuracy
- Strong auditability
- Scalable architecture
- Real-time reporting


