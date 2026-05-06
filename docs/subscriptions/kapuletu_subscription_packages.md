# Kapuletu Product Features & Subscription Packaging Strategy

## 1. Product Overview & Core Value Proposition
Kapuletu is an **Intelligent Financial Ingestion & Approval System** designed for community treasuries (chamas, religious groups, savings groups, alumni associations). It solves the problem of fragmented, manual bookkeeping by automating the ingestion of payment messages (WhatsApp, SMS), parsing them using NLP, and providing an auditable, immutable ledger.

### Key Capabilities:
- **Intelligent Parsing**: Automatically extracts sender, amount, and transaction code from unstructured texts.
- **Workflow & Allocations**: Treasurers can approve, reject, edit, or split a single payment across multiple contributors or campaigns.
- **Audit & Security**: Employs an immutable ledger (Amazon QLDB) for absolute financial truth, preventing tampering.
- **Automated Reporting**: Replaces manual spreadsheets with automated daily summaries, Excel, and PDF exports.

---

## 2. Feature Inventory
To build subscription tiers, we first categorize all current and planned features.

### A. Data Ingestion & Processing
- **SMS Integration**: Receiving transactions via Twilio SMS.
- **WhatsApp Integration**: Receiving transactions via Twilio WhatsApp.
- **NLP Parsing Engine**: Automated data extraction from messages.
- **Manual Entry**: Form-based manual transaction entry.
- **Direct M-Pesa Integration** *(Future)*: API-level integration for automated polling.

### B. Group & Member Management
- **Multi-Group Management**: Ability for one treasurer to manage multiple distinct groups.
- **Member Directory**: Storing and managing member details and historical contributions.
- **Member Limits**: Number of members allowed per group.

### C. Financial Operations & Workflows
- **Campaign Management**: Creating specific fundraising goals/pots.
- **Treasurer Approval Inbox**: Central dashboard for pending transactions.
- **Split Allocations**: Dividing a single payment across multiple campaigns/members.
- **Idempotency/Fraud Checks**: Preventing duplicate message ingestion.
- **Role-Based Access Control**: Treasurers vs. Admins vs. Viewers.

### D. Ledger & Data Integrity
- **Standard Ledger**: Standard relational database logging (PostgreSQL).
- **Immutable Ledger (QLDB)**: Cryptographically verifiable, tamper-proof audit trail.

### E. Reporting & Analytics
- **Basic Dashboard**: View totals and pending items.
- **Daily Summaries**: Automated daily roll-ups.
- **Export Capabilities**: Excel and PDF report generation.
- **Advanced Insights** *(Future)*: AI-driven contribution predictions and anomalies.

---

## 3. Proposed Subscription Packages

Here is a proposed 3-tier SaaS pricing model tailored to community sizes and needs. Amounts are suggestive and should be adjusted based on market research and cloud infrastructure costs.

### Tier 1: **Starter / Bronze** 
**Target:** Small families, informal friend groups, small chamas.
**Pricing:** *e.g., $10 / month (or ~KES 1,500/month)*

**Features:**
- **Groups:** 1 Group
- **Members:** Up to 50 Members
- **Campaigns:** Up to 3 Active Campaigns
- **Transaction Volume:** Up to 100 parsed messages/month
- **Ingestion Channels:** Manual Entry + Standard SMS
- **Workflow:** Basic Approvals (Approve/Reject)
- **Reporting:** Basic Web Dashboard & Daily Summaries
- **Ledger:** Standard Relational Database (PostgreSQL)
- **Support:** Standard Email Support

---

### Tier 2: **Professional / Silver (Most Popular)**
**Target:** Mid-to-large chamas, church groups, alumni associations.
**Pricing:** *e.g., $29 / month (or ~KES 4,000/month)*

**Features:**
- **Groups:** Up to 3 Groups
- **Members:** Up to 500 Members
- **Campaigns:** Unlimited Active Campaigns
- **Transaction Volume:** Up to 1,000 parsed messages/month
- **Ingestion Channels:** SMS + **WhatsApp Integration**
- **Workflow:** Advanced Approvals (Split Allocations, Edits)
- **Reporting:** Excel & PDF Report Exports
- **Ledger:** **Immutable Ledger (Amazon QLDB)** included for audit readiness
- **Support:** Priority Email & Chat Support

---

### Tier 3: **Enterprise / Gold**
**Target:** Large SACCOs, multi-branch religious organizations, large NGOs.
**Pricing:** *e.g., $99 / month (or ~KES 12,000/month) or Custom*

**Features:**
- **Groups:** Unlimited Groups
- **Members:** Unlimited Members
- **Campaigns:** Unlimited Active Campaigns
- **Transaction Volume:** Unlimited (Subject to Fair Use / Tiered overage pricing)
- **Ingestion Channels:** SMS, WhatsApp, and **Direct M-Pesa API Integration** *(Future)*
- **Workflow:** Advanced Approvals + Custom Roles (Multiple Treasurers, Auditors)
- **Reporting:** Custom PDF Reports + **AI-driven Financial Insights** *(Future)*
- **Ledger:** Immutable Ledger (QLDB) + Downloadable Cryptographic Audit Trails
- **Support:** Dedicated Account Manager & Phone Support

---

## 4. Key Levers for Monetization (Upsells)

Beyond flat-rate subscriptions, you can employ usage-based upsells to maximize revenue:

1. **Transaction Overage Fees:** Charge a micro-fee (e.g., $0.05) per parsed transaction if a group exceeds their monthly quota.
2. **WhatsApp Add-on:** If Starter users want WhatsApp parsing, offer it as a $5/mo add-on without requiring an upgrade to Professional.
3. **Audit Certificates:** Charge a one-time fee to generate a verified, cryptographically signed ledger audit report for groups undergoing external audits.
4. **Member Self-Service Portal:** Allow members to log in and see their own contributions. This could be a premium add-on per member per month.

## 5. Next Implementation Steps
If you agree with this structure, we can proceed to:
1. **Database Updates:** Create `SubscriptionTier` and `OrganizationBilling` models in `models/`.
2. **Feature Flags:** Implement a utility in `common/` that checks if an organization is allowed to use a feature (e.g., `can_export_pdf()`, `can_use_qldb()`) based on their active subscription.
3. **Stripe/Paystack Integration:** Scaffold the endpoints in `services/subscriptions/` to handle checkout, webhooks, and subscription lifecycle events.
