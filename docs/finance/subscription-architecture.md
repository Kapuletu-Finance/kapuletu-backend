# Documentation: Subscription Engine Architecture

This document defines the technical specifications, integration requirements, and end-to-end lifecycle of the KapuLetu Subscription Engine.

## 1. High-Level Approach
We utilize a **Provider-Agnostic Abstraction Layer**. The core subscription logic (calculating expiry, resetting usage, unlocking features) is decoupled from the specific payment gateway (M-Pesa, Stripe, etc.).

### Key Principles:
- **Idempotency**: Every payment attempt has a unique `CorrelationID` to prevent double-billing.
- **Asynchronous Confirmation**: We rely on verified server-to-server webhooks for finalized payment state.
- **Feature Gating**: Access is enforced at the handler level via Python decorators that check real-time database usage counters.

---

## 2. End-to-End Subscription Flow

### Phase A: Discovery & Intent
1.  **Plan Retrieval**: The Treasurer requests `GET /finance/available-plans`.
2.  **Selection**: The user selects a plan (e.g. "Pro") and a payment method (e.g. "mpesa").
3.  **Checkout Initiation**: The client calls `POST /finance/checkout` with `plan_id` and `provider`.

### Phase B: Payment Execution
- **Case 1: M-Pesa (STK Push)**
    1.  Backend calls Safaricom API.
    2.  Treasurer receives PIN prompt on phone.
    3.  Treasurer enters PIN.
    4.  Safaricom sends a `POST` callback to our webhook.
- **Case 2: Cards (Stripe/Flutterwave)**
    1.  Backend creates a "PaymentIntent" and returns a `client_secret`.
    2.  Frontend collects card details and confirms the payment.
    3.  Gateway sends a `POST` webhook to our system.

### Phase C: Fulfillment (The Unlock)
1.  **Verification**: The system verifies the webhook signature.
2.  **Ledger Entry**: A `SubscriptionPayment` record is created in the database.
3.  **Plan Update**: The `User.current_plan_id` is updated. The `Subscription` record is extended (e.g. +30 days).
4.  **Notification**: A real-time notification is sent via WhatsApp/Email confirming the upgrade.

---

## 3. Supported Payment Methods & Requirements

### A. M-Pesa (Safaricom)
- **Integration**: Daraja API (STK Push).
- **Requirements**:
    - `MPESA_CONSUMER_KEY` / `MPESA_CONSUMER_SECRET`
    - `MPESA_SHORTCODE` / `MPESA_PASSKEY`
    - Publicly accessible Webhook URL (for callbacks).

### B. Credit/Debit Cards (Flutterwave)
- **Integration**: Flutterwave v3 Payments API.
- **Requirements**:
    - `FLW_SECRET_KEY` / `FLW_SECRET_HASH`
    - Redirect URL for hosted checkout.

---

## 4. Technical Requirements for Implementation

### Environmental Variables
```bash
# Gateway Credentials
DATABASE_URL=...
MPESA_SHORTCODE=...
FLW_SECRET_KEY=...

# System Config
SUBSCRIPTION_RENEWAL_GRACE_PERIOD=3 # Days
```

### Critical Handlers
1.  **Checkout Dispatcher**: Routes requests to the appropriate provider logic.
2.  **Webhook Unified Handler**: Validates signatures and triggers the fulfillment service.
3.  **Usage Monitor**: A background service that periodically checks for expired subscriptions and demotes users to the "Free" tier.

## 6. Payment Methods & Setup Requirements

To activate the subscription engine in production, the following credentials and configurations must be provisioned.

### A. M-Pesa (Safaricom Daraja API)
**Target**: Kenyan Treasurers.
- **Provider**: Safaricom.
- **Protocol**: STK Push (Lipa Na M-Pesa Online).
- **Setup Requirements**:
    1.  **Daraja Account**: Create an app on [Safaricom Developer Portal](https://developer.safaricom.co.ke/).
    2.  **Shortcode**: A Lipa Na M-Pesa Paybill or Till Number.
    3.  **Passkey**: Generated from the Daraja portal.
    4.  **Environment Variables**:
        - `MPESA_CONSUMER_KEY`
        - `MPESA_CONSUMER_SECRET`
        - `MPESA_SHORTCODE`
        - `MPESA_PASSKEY`
        - `MPESA_CALLBACK_URL`: Must be our public API Gateway endpoint.

### B. Global Cards & African Payments (Flutterwave)
**Target**: International Treasurers and Pan-African Markets.
- **Provider**: Flutterwave.
- **Protocol**: Hosted Checkout / v3 API.
- **Setup Requirements**:
    1.  **Flutterwave Account**: Activated account at [Flutterwave.com](https://flutterwave.com).
    2.  **Secret Key**: Used for server-side API calls.
    3.  **Environment Variables**:
        - `FLW_SECRET_KEY`
        - `FLW_SECRET_HASH`: Required to verify incoming webhook signatures.
        - `FLW_CURRENCY`: Default currency (e.g., `KES`).

---

## 7. Operational Parameters

| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| `CHECKOUT_TIMEOUT` | 60s | Time before an STK push is considered "Timed Out". |
| `MAX_RETRY_ATTEMPTS` | 3 | Number of times to retry a failed webhook processing. |
| `SUBSCRIPTION_GRACE_PERIOD` | 48h | Extra time given after expiry before feature locking occurs. |
| `AUTO_RENEW_ENABLED` | `True` | Whether the system attempts to charge the card on expiry. |
