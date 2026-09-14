# Implementation Plan: Subscriptions, Payments & Checkout

This plan addresses the end-to-end functionality of the KapuLetu Subscription Lifecycle, covering onboarding, trial expiration, the checkout flow, and crucially, how we enforce feature limits securely across the platform.

## 1. Feature Enforcement Engine (The Gatekeeper)

To answer the critical question: *"How do we ensure correct features are enforced without hardcoding or errors?"*

We will NOT hardcode `if user.plan == 'Free'` inside every endpoint. That approach leads to massive security gaps and maintenance nightmares. Instead, we will build a centralized **Feature Guard (Dependency Injection)** system deeply integrated into FastAPI.

### Mechanism: `FeatureGuard` & `UsageTracker`
We will introduce two FastAPI dependencies (decorators) that wrap around our endpoints:

1. **`RequireFeature(feature_name: str)`**: 
   Before an endpoint runs (e.g., the Excel Export endpoint), this dependency queries the user's active `Plan` from the database. If the plan's `allowed_features` JSON does not contain `"excel_export"`, it throws an immediate `403 Forbidden: Upgrade required`.
2. **`CheckLimit(metric: str)`**:
   Before creating a new campaign, this checks the `UsageTracking` table against the `Plan` limits (e.g., `max_campaigns`). If the limit is reached, it throws a `402 Payment Required: Resource limit reached`.

This guarantees that feature gating is evaluated dynamically at runtime against the database, ensuring zero feature leakage across the entire platform.

## 2. Subscription Plans & Feature Matrix
Based on the `kapuletu_subscription_packages.md` strategy, here is the detailed breakdown of all plans and what the Feature Guard will enforce:

### Tier 0: Free / Basic
- **Target:** Micro-fundraisers testing the system.
- **Resource Limits:** 1 Group, 1 Campaign, Max 15 Members, 30 transactions/month.
- **Feature Flags:** 
  - `whatsapp_parsing`: False (Manual entry only)
  - `excel_exports`: False (Web dashboard only)
  - `pdf_exports`: False
  - `ai_auto_approve`: False

### Tier 1: Starter / Bronze
- **Target:** Small committees, event organizers.
- **Resource Limits:** 1 Group, 3 Campaigns, Max 50 Members, 150 transactions/month.
- **Feature Flags:** 
  - `whatsapp_parsing`: True (Single forwarding only)
  - `excel_exports`: False 
  - `pdf_exports`: True (KapuLetu Watermarked)
  - `ai_auto_approve`: False

### Tier 2: Professional / Silver *(14-Day Free Trial Default)*
- **Target:** Mid-to-large associations, church treasurers.
- **Resource Limits:** 5 Groups, 15 Campaigns, Max 500 Members, 1,500 transactions/month.
- **Feature Flags:** 
  - `whatsapp_parsing`: True (Bulk Forwarding Enabled)
  - `excel_exports`: True
  - `pdf_exports`: True (Custom headers/footers)
  - `ai_auto_approve`: True

### Tier 3: Enterprise / Gold
- **Target:** Large SACCOs, multi-branch organizations.
- **Resource Limits:** Unlimited Groups/Campaigns/Members, 10,000 transactions/month.
- **Feature Flags:** 
  - `whatsapp_parsing`: True 
  - `excel_exports`: True
  - `pdf_exports`: True (Fully Whitelabeled / No watermark)
  - `ai_auto_approve`: True (Custom confidence thresholds)
  - `deep_ai_insights`: True

## 3. The User Flow (At what point do they pay?)

To maximize user acquisition, we will use the **Frictionless Trial Flow**:
1. **Signup Phase:** The user registers. We do *not* ask for payment upfront. 
2. **Instant Access:** Upon successful registration, the backend automatically creates an active `Subscription` record tied to the **Professional / Silver Plan** lasting for 14 days.
3. **The Countdown:** The user enjoys premium features (Bulk WhatsApp, Auto-Approve, Excel). 
4. **The Squeeze / Expiration:** At Day 14, if they haven't checked out, the system automatically overwrites their `plan_id` to the **Free Tier**. The `FeatureGuard` dependencies instantly kick in—blocking Excel exports and Bulk WhatsApp forwarding, naturally driving them to the Billing Dashboard to pay.

## 4. End-to-End Expiration & Reminder Lifecycle

The backend manages lifecycles actively. We will build a scheduled daily task engine (`expiry_worker.py`) that sweeps the `subscriptions` table every midnight:
- **T-Minus 7 Days:** Checks for `end_date` == exactly 7 days away. Fires a "Trial ending soon" email & WhatsApp reminder.
- **T-Minus 3 Days:** Fires an urgent reminder ("Your KapuLetu Pro trial ends in 3 days").
- **T-Minus 24 Hours:** Fires a final "Last Chance" warning.
- **Day 0 (Expiration):** If `end_date` < `current_date`, updates `status = 'expired'` and downgrades `plan_id` to the Free Tier.

## 5. Checkout Module & API Endpoints (Fully Detailed)

We will refactor the legacy serverless `handler.py` into a robust FastAPI router (`services/finance/checkout_router.py`). Here are **all** the endpoints, including countdowns, billing history, and cancellations required by the frontend:

| Endpoint | Method | Purpose & Frontend Usage |
| :--- | :--- | :--- |
| `/finance/available-plans` | `GET` | **Public**. Returns the 4 tiers (Free, Bronze, Silver, Gold) and prices. Used by the pricing page. |
| `/finance/my-subscription` | `GET` | **Auth**. This is the **Countdown Engine**. Returns `active_plan`, `is_on_trial` (bool), and crucially, `days_remaining` (int). The frontend uses this integer to render the red countdown banner (e.g. "3 days left in Pro Trial"). Also returns resource usage limits (Groups: 2/5). |
| `/finance/checkout` | `POST` | **Auth**. Initiates payment. User selects a `plan_id` and provider (M-Pesa/Flutterwave). Returns a checkout URL or STK Push response. |
| `/finance/status/{id}` | `GET` | **Auth**. Polling endpoint to check if M-Pesa/Card payment succeeded. |
| `/finance/webhooks/{provider}` | `POST` | **Public (Secured)**. Silent background endpoint where Safaricom/Flutterwave confirms successful payment. Our `FulfillmentService` receives this, upgrades the plan, and adds +30 days. |
| `/finance/billing-history` | `GET` | **Auth**. Returns an array of past payments (`SubscriptionPayment` records). The frontend uses this to render the "Invoices / Payment History" table. |
| `/finance/cancel-subscription`| `POST` | **Auth**. Allows the user to turn off `is_auto_renew`. Their subscription remains active until the `end_date`, after which the background worker downgrades them. |
| `/admin/finance/trigger-reminders`| `POST` | **Admin Only**. Manual trigger for the `expiry_worker` to force sending out the T-7/T-3/T-1 emails and WhatsApp reminders without waiting for midnight. Used for testing. |

## 6. Technical Execution Checklist

- **[NEW]** `services/finance/guards.py`: Implement the `RequireFeature` and `CheckLimit` dependencies.
- **[NEW]** `services/finance/checkout_router.py`: Build all 8 FastAPI endpoints listed above (Checkout, Subscriptions, History, etc).
- **[MODIFY]** `services/finance/fulfillment.py`: Ensure webhooks trigger account upgrades and create `SubscriptionPayment` records accurately.
- **[NEW]** `services/subscriptions/expiry_worker.py`: Build the cron script for reminders and downgrades.
- **[NEW]** `scripts/seed_plans.py`: Create the database seeding script for the 4 pricing tiers.

## User Review Required

1. **Endpoints Check:** I have explicitly added the endpoints for the **trial countdown logic** (`my-subscription`), **billing history** (`billing-history`), **cancellation** (`cancel-subscription`), and a manual admin trigger for **reminders**. Does this cover all the lifecycle endpoints the frontend needs?
2. **Cron Jobs:** Does your current deployment environment support running background workers (like Celery or raw Linux crontab) to trigger the `expiry_worker.py` script daily?
