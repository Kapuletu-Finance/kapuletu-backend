# KapuLetu Enterprise Settings Module: Technical Specification

## 1. Executive Summary
The Settings Module is the configuration backbone of the KapuLetu treasury platform. Moving beyond simple cosmetic toggles, this enterprise-grade engine governs strict financial automation rules, hierarchical overrides (Global User vs Local Campaign), feature-gating based on active subscriptions, and regional compliance rules.

## 2. Hierarchical Configuration Strategy (Global vs Local)
Enterprise software requires default configurations with granular override capabilities.
- **Global User Level (Level 1)**: Defines the treasurer's baseline. Example: *Global WhatsApp Footer = "Managed by KapuLetu"*.
- **Group Level (Level 2)**: Overrides Global. Example: *Welfare Group Footer = "Welfare Matters"*.
- **Campaign Level (Level 3)**: Overrides Group. Example: *Funeral Campaign Footer = "Rest in Peace"*.

## 3. Subscription & Feature Gating
Settings are strictly tied to the `Subscription` and `Plan` models. The backend will enforce these gates when a user attempts to fetch or modify settings.

| Feature Category | Basic Plan | Pro Plan | Enterprise Plan |
| :--- | :--- | :--- | :--- |
| **Automation** | Manual Review Only | Auto-Approve (AI) enabled | Custom AI Training allowed |
| **Branding/Reports** | Standard KapuLetu Template | Custom Headers/Footers | Full Whitelabel (No Watermark) |
| **Security** | SMS OTP | SMS + Authenticator App | Custom Session Timeouts |
| **Export Formats**| PDF Only | PDF + Excel | PDF + Excel + Direct API |

## 4. Deep Audit: Exhaustive Settings Dictionary

### 4.1 Security & Compliance (Domain: `security`)
* `require_2fa` (Boolean): Enforces 2FA across all logins.
* `2fa_method` (Enum: `SMS`, `AUTHENTICATOR`, `WHATSAPP`): Delivery method.
* `session_timeout_minutes` (Int: `15` to `120`): *[Pro/Enterprise]* Auto-logout threshold.
* `require_pin_for_export` (Boolean): *[Enterprise]* Requires entering a Master PIN before downloading an Excel ledger.
* `audit_log_retention_days` (Int: `30`, `90`, `365`): Depends on subscription tier.

### 4.2 Automation & AI (Domain: `automation`)
* `auto_approve_enabled` (Boolean): *[Pro/Enterprise]* If true, AI parses directly to the ledger.
* `confidence_threshold` (Float: `0.80` to `1.0`): The minimum AI certainty required for auto-approval.
* `default_group_id` (UUID): Fallback routing for transactions without a clear group context.
* `fallback_action` (Enum: `REVIEW_INBOX`, `REJECT`): What to do if AI confidence is low.

### 4.3 Regional & Localization (Domain: `regional`)
* `default_currency` (String: `KES`, `USD`, `TZS`).
* `timezone` (String: e.g., `Africa/Nairobi`).
* `number_format` (Enum: `COMMA`, `DOT` -> `1,000.00` vs `1.000,00`).
* `date_format` (Enum: `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD`).
* `language` (Enum: `EN`, `SW`).

### 4.4 Notifications & SLA (Domain: `notifications`)
* `daily_digest_enabled` (Boolean): Receive a 6:00 PM summary of all transactions.
* `weekly_report_enabled` (Boolean): Receive an end-of-week PDF to email.
* `large_transaction_alert` (Boolean): Instant ping for massive contributions.
* `large_transaction_threshold` (Float): E.g., `50000` KES.
* `alert_channels` (List: `["WHATSAPP", "EMAIL", "SMS"]`).

### 4.5 Reporting & Branding (Domain: `reporting`)
* `global_header_template` (String): *[Pro/Enterprise]* Used if campaign lacks one.
* `global_footer_template` (String): *[Pro/Enterprise]* Used if campaign lacks one.
* `remove_kapuletu_branding` (Boolean): *[Enterprise Only]* Strips "Powered by KapuLetu" from PDFs and WhatsApp texts.
* `use_emojis` (Boolean): Global default for reports.
* `public_ledger_pin` (String): Master PIN used for public sharing if no campaign PIN exists.

---

## 5. Architectural Decision: The `report_settings` Migration
**Audit Analysis of `models/report_settings.py`:**
Should `CampaignReportSettings` be deleted and migrated entirely into the User Settings JSON?

**Decision: NO. It must remain a relational table, but architecture will change to an Inheritance Model.**
*Why?* A treasurer with 10 different campaigns needs different settings (different payment instructions, different PINs for different public groups). Migrating them to a single User blob would destroy multi-tenant capabilities.
*How it will work:* 
When generating a report, the `TemplateEngine` will fetch `CampaignReportSettings`. If a field (like `header_template`) is null, it will query the `UserSettings` (Global blob). If the Global blob lacks it, it falls back to the hardcoded `KapuLetu Standard Default`.

## 6. Database Schema Architecture
To support the sheer volume of these settings without creating 40 columns in PostgreSQL, we will implement a strictly typed JSONB field on the `User` model, governed by Pydantic validators.

```json
// The user.preferences JSONB column
{
  "security": { "require_2fa": true, "session_timeout_minutes": 60 },
  "automation": { "auto_approve_enabled": false },
  "regional": { "currency": "KES", "timezone": "Africa/Nairobi" },
  "notifications": { "daily_digest": true, "large_tx_threshold": 50000 },
  "reporting": { "remove_branding": false }
}
```

## 7. Service Layer Integration
A new `SettingsService` will act as the gatekeeper. 
1. It parses the JSONB blob.
2. It queries `SubscriptionService` to check the user's active plan.
3. If a Basic user tries to set `remove_branding: true`, the service intercepts it, throws a `HTTP 402 Payment Required`, and drops the operation.
