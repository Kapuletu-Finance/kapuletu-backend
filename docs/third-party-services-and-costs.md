# KapuLetu: Third-Party Integrations & Operational Cost Breakdown

## 1. Executive Summary
This document outlines all external third-party services, hosting platforms, and integrations required to run the KapuLetu application in production. It also provides a comprehensive breakdown of the "secondary costs"—the recurring operational and infrastructural expenses required to maintain the system, excluding initial development and marketing costs.

---

## 2. Infrastructure & Hosting Services

### A. Backend Compute (AWS Serverless)
The backend architecture is serverless, meaning you pay purely for what you use rather than paying for idle servers.
- **Service**: **AWS Lambda** & **Amazon API Gateway**
- **Purpose**: Executes backend Python code (Ingestion, Approval, Reporting services) and routes HTTP requests.
- **Cost Structure**: Pay-per-request and compute time (milliseconds).
  - *Estimated Cost*: $0 to $5/month for low-to-medium volume (first 1 million requests per month are free on AWS Free Tier).

### B. Frontend Hosting (Next.js)
- **Service**: **Vercel** or **AWS Amplify**
- **Purpose**: Hosts the Next.js Treasurer Dashboard application, providing global CDN edge-caching, SSL, and server-side rendering.
- **Cost Structure**: Free for hobbyists, but for commercial production, a Pro plan is required.
  - *Estimated Cost*: $20/month per developer seat (Vercel Pro) or strictly usage-based (AWS Amplify).

---

## 3. Database & Storage Services

### A. Operational Database (PostgreSQL)
- **Service**: **Supabase** (or **Amazon RDS**)
- **Purpose**: Stores active system state, user data, pending transactions, and campaigns.
- **Cost Structure**: Supabase offers a generous free tier (which requires a keep-alive mechanism to prevent pausing) and a Pro tier. Amazon RDS charges for instance uptime and storage.
  - *Estimated Cost*: $25/month (Supabase Pro Tier - Highly recommended for production to avoid sleeping databases).

### B. Immutable Financial Ledger
- **Service**: **Amazon QLDB** (Quantum Ledger Database)
- **Purpose**: Cryptographically verifies and permanently stores the final approved financial transactions.
- **Cost Structure**: Pay-per-read/write IOs and storage.
  - *Estimated Cost*: $5 to $15/month for typical transaction volumes.

### C. File Storage (Receipts & Reports)
- **Service**: **Amazon S3**
- **Purpose**: Stores generated PDF reports, Excel summaries, and uploaded receipts.
- **Cost Structure**: Pay for storage (per GB) and data transfer out.
  - *Estimated Cost*: $1 to $5/month.

---

## 4. Communication & Integrations

### A. SMS & WhatsApp Ingestion
- **Service**: **Twilio**
- **Purpose**: Receives incoming financial transaction messages from WhatsApp and SMS, and routes them via webhook to the AWS backend.
- **Cost Structure**: Pay-per-message.
  - *WhatsApp*: ~ $0.005 to $0.015 per conversation/message (varies by region).
  - *SMS*: ~$0.0079 per message.
  - *Phone Number Lease*: ~$1.15 to $2.00/month per number.
  - *Estimated Cost*: $15 to $50/month (depending heavily on user transaction volume).

### B. Transaction Emails & Receipts
- **Service**: **Postmark**
- **Purpose**: Sends highly reliable, professionally designed payment receipts to customers and alert emails to treasurers.
- **Cost Structure**: Pay per block of emails.
  - *Estimated Cost*: $15/month for up to 10,000 emails.

---

## 5. Security, Auth & Operations

### A. Authentication
- **Service**: **Supabase Auth** or **Amazon Cognito**
- **Purpose**: Manages user logins, session tokens, and Role-Based Access Control (RBAC) for Treasurers.
- **Cost Structure**: Supabase Auth is included in the $25/mo Pro plan. Cognito is free for the first 50,000 MAUs.
  - *Estimated Cost*: $0 (Covered by DB or AWS Free Tier).

### B. Domain Name & DNS
- **Service**: **Route 53**, **Namecheap**, or **GoDaddy**
- **Purpose**: Custom domain mapping (e.g., `app.kapuletu.com`).
- **Cost Structure**: Annual renewal fee.
  - *Estimated Cost*: $10 to $20/year (approx. $1.50/month).

### C. Logging & Monitoring
- **Service**: **Amazon CloudWatch**
- **Purpose**: Centralized logging for tracking system errors and audit trails.
- **Cost Structure**: Pay per GB ingested.
  - *Estimated Cost*: $2 to $10/month.

### D. CI/CD (Continuous Integration)
- **Service**: **GitHub Actions**
- **Purpose**: Automates linting, testing, and deployment to AWS.
- **Cost Structure**: First 2,000 minutes/month are free.
  - *Estimated Cost*: $0 (Unless massive development scale is reached, then $4/month for GitHub Pro).

---

## 6. Estimated Monthly Operating Costs Summary

To help with financial planning, here are three projected monthly cost brackets based on application scale:

### Phase 1: Launch / Beta (0 - 1,000 Transactions/mo)
*Leveraging free tiers where possible, focusing on essential stability.*
- Frontend Hosting (Vercel Pro): $20
- Database (Supabase Pro): $25
- Twilio (1 Number + low volume): $10
- Emails (Postmark): $15
- AWS Infrastructure (Lambda, QLDB, S3): $5
- **Total Estimated Cost: ~$75 / month**

### Phase 2: Growth Stage (1,000 - 10,000 Transactions/mo)
*Scaling up communication usage and database storage.*
- Frontend Hosting: $20
- Database (Supabase Pro): $25
- Twilio (Higher volume WhatsApp/SMS): $40
- Emails (Postmark): $15
- AWS Infrastructure (Lambda, QLDB, S3, CloudWatch): $20
- **Total Estimated Cost: ~$120 / month**

### Phase 3: Scale (10,000+ Transactions/mo)
*Costs grow linearly mainly with Twilio messages and AWS compute.*
- Frontend Hosting: $20 - $40
- Database: $25 - $50
- Twilio: $100+ (Strictly usage-based)
- Emails: $15 - $50
- AWS Infrastructure: $50+
- **Total Estimated Cost: ~$250+ / month**

---

### Conclusion
The architecture is designed to be highly capital-efficient. Because the compute layer is **Serverless**, you do not pay for idle servers overnight. The primary variable costs as you scale will be **Twilio messaging** and **Amazon QLDB read/writes**. Fixing the database layer to Supabase Pro ($25/mo) is a required baseline to prevent "cold starts" or database pausing during critical financial operations.
