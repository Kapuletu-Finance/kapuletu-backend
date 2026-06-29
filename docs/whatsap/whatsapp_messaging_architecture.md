# KapuLetu Meta WhatsApp Cloud API Messaging Architecture

This document outlines the messaging taxonomy and architectural rules for KapuLetu's integration with the Meta WhatsApp Cloud API. It defines the exact types of messages the engine receives, the messages we send back, and the strict rules imposed by Meta regarding business communication.

---

## 1. Incoming Messages (From Treasurers to KapuLetu)

The KapuLetu "Engine Bot" is designed to ingest unstructured financial data via the Meta Webhook. When a registered treasurer interacts with the KapuLetu WhatsApp number, we receive a real-time `POST` request containing the following types of messages:

### A. Mobile Money Forwards (M-Pesa)
Treasurers copy and paste raw SMS receipts from M-Pesa directly into the WhatsApp chat.
> *Example:* "PK12ABC345 Confirmed. You have received Ksh 1,500.00 from JANE DOE 0712345678 on 14/5/24 at 10:45 AM."

### B. Bank Transfer Alerts
Forwarded SMS or text alerts from partner banks (e.g., Equity, KCB, Cooperative Bank) indicating a direct deposit into the community account.

### C. Manual Contributions
Free-form text messages entered by the treasurer for cash transactions or un-receipted deposits.
> *Example:* "Received 500 from John Wainaina for the December Welfare fund."

### D. System Commands (Future Roadmap)
Short commands like `BALANCE`, `REPORT`, or `HELP` that the treasurer can text to the bot to request instant financial summaries.

---

## 2. Outgoing Messages (From KapuLetu to Treasurers)

KapuLetu sends various automated responses to treasurers. Based on Meta's official guidelines, these messages are strictly divided into two categories based on the **24-Hour Customer Service Window**.

### Category A: User-Initiated (Free-Form Text)
*These messages can be sent without a pre-approved template, provided they are sent within 24 hours of the treasurer's last incoming message.*

*   **Transaction Confirmations:** "✅ Success! We received KES 1,500.00 from Jane Doe. It is now pending your approval..."
*   **Duplicate Rejections:** "⚠️ Notice: You have already submitted this transaction..."
*   **Unauthorized Access:** "❌ Unauthorized: Your phone number is not registered as a treasurer..."
*   **Help/Error Responses:** Real-time feedback if the AI parser fails to understand a manually typed message.

### Category B: Business-Initiated (Requires Meta Templates)
*If KapuLetu initiates a conversation, or if we reply to a treasurer who hasn't messaged the bot in the last 24 hours, we **must** use a pre-approved Meta Message Template.*

*   **Authentication (OTPs):** When a user signs up on the web app, KapuLetu triggers a WhatsApp OTP. Because the user triggered this on the web (not via a WhatsApp message), this **must** be an official Authentication Template.
    > *Template Example:* "KapuLetu Security: Your verification code is {{1}}."
*   **Onboarding / Welcome Messages:** Sent immediately after successful account verification. Requires an official Utility Template.
*   **Automated Financial Reports:** Real-time or scheduled plain-text contribution reports detailing collections, targets, and contributor lists directly in WhatsApp. PDF attachments are not sent; instead, the backend dynamically constructs a hyper-clean, tabular text summary. Requires a Marketing or Utility Template.
*   **System Broadcasts:** Important maintenance or platform updates broadcasted by KapuLetu administrators.

> [!WARNING]
> Attempting to send a free-form message (like an OTP) to a user outside the 24-hour window will result in a silent API failure (`131047: Re-engagement message requires a template`).

---

## 3. How the Engine Bot Receives Information

The KapuLetu ingestion engine operates via a unified `POST /ingestion/webhook` endpoint. Because KapuLetu's Meta Business account is officially verified, the platform is ready for production volumes.

Every time an event occurs on WhatsApp, Meta sends a JSON payload to our backend. The engine specifically monitors three critical data points within the deeply nested `entry -> changes -> value` structure:

### A. Messages Data
If a treasurer sends text or media, the payload includes a `messages` array. The KapuLetu parser extracts:
*   `text.body`: The raw string of the M-Pesa receipt or manual entry.
*   `type`: Identifies if the message is `text`, `image`, or `document`. *(Currently, KapuLetu strictly processes `text` messages).*

### B. Metadata & Identification
*   `from`: The sender's phone number in international format (e.g., `254700000000`). This is cross-referenced against the PostgreSQL database to authenticate the user and resolve their `owner_id`.
*   `timestamp`: Used to log exact interaction times for forensic auditing.

### C. Status Updates (Delivery Receipts)
When KapuLetu sends an outgoing message (like an OTP), Meta fires secondary webhooks containing a `statuses` array.
*   This array tells the backend if the message was `sent`, `delivered`, or `read`. 
*   *Note: Currently, the backend acknowledges these statuses with a `200 OK` but does not persist them to the database. This can be added in the future for delivery analytics.*

---

## 4. Production Readiness & Next Steps

With the business account verified and the infrastructure deployed on AWS Serverless (API Gateway + Lambda), KapuLetu is architecturally prepared for high-throughput messaging.

**Immediate Action Items for the Admin:**
1.  **Template Creation:** Navigate to the Meta WhatsApp Manager and create dedicated templates for the **OTP Verification** and **Welcome Message**. Submit them for Meta approval.
2.  **Update Code with Template IDs:** Once the templates are approved, the `services/auth/custom_sender.py` and `services/auth/handler.py` files must be updated to use the `template` message type rather than `text`, passing the specific template names and language codes.
3.  **Field Subscriptions:** Ensure that both the `messages` and `message_deliveries` fields are checked in the Webhook configuration on the Meta portal.


KapuLetu WhatsApp Template Report
1. Authentication Template: OTP Verification
This template is used by custom_sender.py to send secure verification codes.
Template Name: kapuletu_auth_otp
Category: Authentication
Language: en_US
Structure:
Body: {{1}} is your verification code. For your security, do not share this code.
Footer: Expires in 10 minutes.
Button: Copy Code (linked to {{1}})
Backend Variable: {{1}} = 6-digit numeric string.
2. Utility Template: Welcome Message (V2)
This template is used by handler.py to onboard new users with the correct .co.ke contact details.
Template Name: kapuletu_welcome
Category: Utility
Language: en_US
Structure:
Header: Financial Transparency Verified
Body:
*WELCOME TO KAPULETU*, {{1}}
Your account has been successfully verified and is now active.
Next Steps:
1. Access your dashboard
2. Create your first Group, then add a Campaign.
3. Forward your first M-Pesa receipt to this WhatsApp number to see the AI tracking engine in action.
For assistance, email support@kapuletu.co.ke or contact us at +254 143 933472
Footer: Automated Financial Tracking
Button: Visit Website (Static: https://app.kapuletu.co.ke)
Backend Variable: {{1}} = User's first name.
3. Utility Template: Financial Alert (Two-Step Flow)
This template is used to trigger the transparency reports while bypassing character limits.
Template Name: kapuletu_financial_alert
Category: Utility
Language: en_US
Structure:
Header: 📊 Treasury Alert
Body:
*KAPULETU TREASURY ALERT*
Campaign: {{1}}
Date: {{2}}
------------------------
Total Collected: KES {{3}}
Your full contributor breakdown is ready. Reply with REPORT to view details.
Button: Quick Reply (REPORT)
Backend Variables:
{{1}} = Campaign Name
{{2}} = Current Date
{{3}} = Total Amount (numeric)
Backend Integration Logic
For the Financial Alert, your backend must listen for the incoming webhook event where text.body is exactly REPORT. When detected, your daily_summary.py should execute and send the full, dynamically generated contributor list as a free-form text message, as the user has now opened the 24-hour customer service window.