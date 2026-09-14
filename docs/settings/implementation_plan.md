# Implementation Plan: Enterprise User Settings Module

To eliminate confusing or clashing endpoints, we are utilizing a highly isolated API structure. Furthermore, this plan details the exact architectural approaches required to bring these settings to life (i.e., how a setting actually triggers a system behavior).

## 1. Clear Isolation: Database Architecture

Settings will be stored in a `JSON` column, but they will be strictly isolated by domain to prevent updates from clashing.
1. **User Model (`models/users.py`)**: Add `preferences = Column(JSON, default=dict)`
2. **Group Model (`models/group.py`)**: Add `settings_override = Column(JSON, default=dict)`
3. **Campaign Model (`models/campaign.py`)**: Add `settings_override = Column(JSON, default=dict)`

*Isolation Strategy:* When the frontend calls `PUT /settings/me/security/timeout`, the backend `SettingsService` will only extract and mutate the `{"security": {...}}` key within the JSON blob. The `automation`, `regional`, and `reporting` domains are completely untouched and isolated during the transaction.

## 2. Exhaustive Settings Dictionary (Pydantic Models)

1. **SecuritySettings**: `require_2fa` (bool), `2fa_method` (SMS/App), `session_timeout_minutes` (int), `require_pin_for_export` (bool), `audit_log_retention_days` (int).
2. **AutomationSettings**: `auto_approve_enabled` (bool), `confidence_threshold` (float), `default_group_id` (uuid), `fallback_action` (Review/Reject).
3. **RegionalSettings**: `default_currency` (string), `timezone` (string), `number_format` (comma/dot), `date_format` (string), `language` (EN/SW).
4. **NotificationSettings**: `large_transaction_alert` (bool), `large_transaction_threshold` (float), `alert_channels` (list).
5. **ReportingSettings**: `auto_report_frequency` (enum: daily/weekly/monthly/none), `global_header_template` (string), `global_footer_template` (string), `remove_kapuletu_branding` (bool), `use_emojis` (bool), `public_ledger_pin` (string).
6. **BillingSettings**: `auto_renew_subscription` (bool), `default_payment_method` (enum: MPESA/CARD), `billing_email` (string).

## 3. Explicit, Non-Clashing API Endpoints (Button-Mapped)

### A. Global Settings (User Level)
| Endpoint | Method | Purpose & Parameters |
| :--- | :--- | :--- |
| `/settings/me` | `GET` | Fetches the entire settings blob to initialize the frontend UI state. |
| `/settings/me/security/2fa` | `PUT` | **UI Toggle:** Enable/Disable 2FA. |
| `/settings/me/security/timeout` | `PUT` | **UI Slider:** Sets `session_timeout_minutes`. |
| `/settings/me/automation/auto-approve` | `PUT` | **UI Toggle & Slider:** Enables AI parsing. |
| `/settings/me/automation/fallback` | `PUT` | **UI Dropdown:** Sets `default_group_id` and `fallback_action`. |
| `/settings/me/reports/frequency` | `PUT` | **UI Dropdown:** Sets `auto_report_frequency`. |
| `/settings/me/reports/branding` | `PUT` | **UI Form & Toggle:** Sets `global_header_template`, `global_footer_template`, and `remove_kapuletu_branding`. |
| `/settings/me/regional/localization` | `PUT` | **UI Dropdowns:** Sets `currency`, `timezone`, `number_format`, `date_format`, `language`. |
| `/settings/me/notifications/alerts` | `PUT` | **UI Toggle & Input:** Sets `large_transaction_alert` and the `threshold` amount. |
| `/settings/me/billing` | `PUT` | **UI Form & Toggle:** Sets `auto_renew_subscription`, `default_payment_method`, and `billing_email`. (Updates JSON and triggers `Subscription` model sync if auto-renew changes). |

### B. Group Level (Overrides)
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/groups/{group_id}/settings` | `GET` | Fetches Group-specific overrides. |
| `/groups/{group_id}/settings/reports` | `PUT` | Updates Group-level headers, footers, or report frequencies. |
| `/groups/{group_id}/settings/automation` | `PUT` | Overrides auto-approval logic just for this specific group. |

### C. Campaign Level (Overrides)
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/campaigns/{campaign_id}/settings` | `GET` | Fetches Campaign-specific overrides. |
| `/campaigns/{campaign_id}/settings/reports` | `PUT` | Set a specific `public_ledger_pin` or `header_template` strictly for this campaign. |

## 4. Execution Approaches: Achieving the Functionalities

Storing settings is not enough; the system must actually enforce them. Here are the precise implementation approaches to achieve all functionalities:

1. **Auto-Approve Engine (Automation)**:
   - *Approach:* We will modify the `services/ingestion/handler.py` (or the NLP Parsing service). After the NLP engine returns a confidence score, it will query the user's `AutomationSettings`. If `auto_approve_enabled` is true AND the NLP score >= `confidence_threshold`, the transaction skips the `PendingTransactions` inbox and is written directly to the Ledger via `LedgerService`.
2. **Export Security PIN (Security)**:
   - *Approach:* We will modify the `GET /reports/export/excel` endpoint. If `require_pin_for_export` is true in settings, the endpoint will require a `pin` query parameter. The `SettingsService` will hash and verify this parameter against the stored master PIN before generating the Excel file.
3. **Session Timeouts (Security)**:
   - *Approach:* We will inject a custom Auth Middleware check. It will compare the current time against a `last_active_timestamp` stored in Redis (or JWT issue time). If the delta exceeds `session_timeout_minutes`, the middleware throws a `401 Unauthorized`.
4. **Automated Reports (Reporting/Notifications)**:
   - *Approach:* We will build a scheduled cron worker (`services/reporting/report_worker.py`). Every day at 6:00 PM, it will query all users where `auto_report_frequency == 'daily'`. It will generate the summary payload and send it via the configured `alert_channels`.
5. **Large Transaction Alerts (Notifications)**:
   - *Approach:* Inside `services/approval/handler.py` (or LedgerService), right after a transaction is committed to the ledger, we will check if the `amount >= large_transaction_threshold`. If true, an immediate asynchronous notification is fired to the Treasurer's WhatsApp.
6. **Auto-Renew Subscriptions (Billing)**:
   - *Approach:* When the user toggles `auto_renew_subscription` via `/settings/me/billing`, the `SettingsService` not only updates the JSON blob but also performs a database `UPDATE` on the `subscriptions` table (setting `is_auto_renew`). This ensures the `expiry_worker.py` gracefully downgrades them or re-bills them accurately.

## 5. Subscription Feature Gating (The Interceptor)
The `SettingsService` will intercept `PUT` requests to premium endpoints.
- If a Free plan user calls `/settings/me/automation/auto-approve`, the `FeatureGuard` blocks it with a `402 Payment Required`.

## User Review Required
I have now explicitly added the **BillingSettings** domain to the plan, including `auto_renew_subscription`, `default_payment_method`, and `billing_email`. I've also detailed how toggling auto-renew in the Settings API will directly sync with the Subscription table database to ensure the worker processes it correctly.

Does this cover everything you need for the Billing Settings tab?
