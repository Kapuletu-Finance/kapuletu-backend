# Module: Subscriptions & Cashflow Management

## 1. Overview
This module is responsible for tracking the platform's revenue streams and managing the subscription parameters that govern what features and limits are available to Treasurers.

## 2. Key Functionalities

### 2.1 Subscription Plan Lifecycle Management
Admins have full control over the definition and lifecycle of subscription tiers.
- **Plan Creation**: Defining new tiers with specific:
    - **Pricing**: Cost per billing cycle (e.g., 2500 KES).
    - **Billing Periods**: Support for `monthly`, `quarterly`, and `annual` billing.
    - **Feature Sets**: Attaching specific platform capabilities (e.g., "WhatsApp Ingestion", "Advanced Reporting").
    - **Hard/Soft Limits**: Setting caps on the number of transactions, groups, or campaigns.
- **Lifecycle Tracking**: Monitoring active, expiring, and canceled subscriptions.
- **Plan Migration**: Logic for moving users between different tiers.

### 2.2 Payment & Transaction Tracking
The system provides a two-tiered view of all financial intake.
- **Granular User-Level Records**: 
    - Full payment history for each Treasurer.
    - Status of recurring billing and renewal attempts.
    - Refund and credit history.
- **Platform-Wide Financial Ledger**: 
    - Real-time stream of all incoming subscription payments.
    - Aggregated totals by day, month, and year.
    - Success/Failure rate monitoring for payment gateways (e.g., M-Pesa B2B).

### 2.3 Billing Support & Overrides
Handling Treasurer billing challenges.
- **Subscription Overrides**: Manually extending a user's subscription or granting a trial period.
- **Billing Adjustments**: Issuing credits or resolving payment discrepancies.
- **Invoice Management**: Generating and viewing invoices for Treasurers.

## 3. Data Captured for Auditing
- **Action**: (e.g., `SUBSCRIPTION_CREATED`, `PLAN_PARAMETER_CHANGED`).
- **Entity ID**: The subscription or plan ID.
- **Payload**: The specific financial change (e.g., `{"old_price": 500, "new_price": 750}`).
- **Actor**: The admin who authorized the override or change.

## 4. Platform Economics (Revenue Tracking)
The system tracks the following "Cashflow Nodes":
- **Incoming**: Subscription Fees (Stripe/M-Pesa).
- **Outgoing**: Third-party service costs (Twilio, AWS).
- **Net**: Platform margin per user.

---
**Next Steps**: For automated notifications regarding expiring subscriptions, see the **[Communication & Engagement](crm-engagement.md)** module.
