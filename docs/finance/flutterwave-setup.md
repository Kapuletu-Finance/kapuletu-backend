# Flutterwave Setup Guide for KapuLetu

This guide outlines the steps required to configure your Flutterwave account to work with the KapuLetu Subscription Engine.

## 1. Create and Activate Account
1.  Go to [Flutterwave.com](https://flutterwave.com) and create an account.
2.  Complete the **Compliance** section by providing your business details (required to accept live payments).

## 2. Obtain API Keys
1.  Navigate to **Settings > API Keys** in the Flutterwave Dashboard.
2.  Copy the **Public Key** (used by the frontend/mobile app).
3.  Copy the **Secret Key** (used by the backend).
4.  Copy the **Encryption Key**.
5.  Add these to your environment:
    - `FLW_SECRET_KEY=FLWSECK-xxxxxxxxxxxxxxxxxxxx-X`
    - `FLW_PUBLIC_KEY=FLWPUBK-xxxxxxxxxxxxxxxxxxxx-X`

## 3. Configure Webhooks (CRITICAL)
Webhooks are essential for KapuLetu to know when a payment has succeeded so it can unlock features.

1.  Go to **Settings > Webhooks**.
2.  **URL**: `https://api.kapuletu.com/finance/webhooks/flutterwave` (Replace with your actual production URL).
3.  **Secret Hash**: Enter a strong random string (e.g., `kapuletu_webhook_secret_123`).
4.  Copy this hash and add it to your environment:
    - `FLW_SECRET_HASH=your_random_string`
5.  Ensure the following events are enabled:
    - `charge.completed`
    - `transfer.completed` (if using payouts)

## 4. Testing
Before going live, use the **Test Mode** keys provided in your dashboard:
1.  Use the `FLWPUBK_TEST-...` and `FLWSECK_TEST-...` keys.
2.  Use Flutterwave's [test card numbers](https://developer.flutterwave.com/docs/integration-guides/testing-helpers) to simulate successful and failed payments.
3.  Verify that your subscription is automatically updated in the KapuLetu Dashboard after a successful test payment.

## 5. Supported Payment Methods
In the Flutterwave Dashboard, go to **Settings > Account Settings**. Ensure the following are enabled:
- Cards
- M-Pesa (Kenya)
- Mobile Money (various countries)
- Bank Transfer
