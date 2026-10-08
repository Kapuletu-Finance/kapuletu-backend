# Communications Module: Audit and Revamp Plan

Date: 2026-10-08 · Scope: backend (`kapuletu-backend`) and admin UI (`kapuletu-frontend`)

## 1. What exists today

| Concern | Where | Notes |
|---|---|---|
| Broadcast (admin hub) | `services/admin/crm_service.py`, `POST /admin/crm/broadcast` | Untyped `Dict[str, Any]` payload, FastAPI `BackgroundTasks` + 10-thread pool |
| Broadcast (second copy) | `services/notifications/service.py`, `POST /notifications/broadcast` | Synchronous loop inside the request; no campaign record |
| Delivery log | `models/communication_logs.py` | One row per send, no indexes, no FK, no delivery events |
| Campaign record | `models/broadcast.py` (`BroadcastCampaign`) | No author, no stats, `scheduled_for` never used |
| Providers | `services/notifications/providers/` | Resend (email), Meta Cloud API (WhatsApp) |
| Templates | `templates/email_base.html`, `services/notifications/templates/*.html`, `services/notifications/email_templates.py` | Three separate template systems; admin edits write to the container filesystem |
| In-app notifications | `services/notifications/router.py` | Per-user feed |
| Contact inquiries | `/admin/contact-messages` | List + status only, no reply |
| Admin UI | `src/features/admin/components/communications/*` | 5 tabs, ~1,100 lines |

About 22 other files send email/WhatsApp directly (auth OTPs, receipts, invoices, HR, support), each in its own way.

## 2. Findings

Severity: **Critical** = security hole or silent data loss/false reporting; **High** = legal/compliance exposure or broken at realistic scale; **Medium** = correctness/maintainability; **Low** = polish.

### Critical

1. **Remote code execution via email templates.** `PUT /admin/templates/raw/{name}` lets any internal employee overwrite a Jinja file, and `GET /admin/templates/preview/{name}` renders it with a non-sandboxed `jinja2.Environment`. A payload such as `{{ cycler.__init__.__globals__.os.popen('...').read() }}` runs on the server. Gate: `get_admin_user` (any non-treasurer role, including content managers and support agents).
2. **WhatsApp broadcasts are reported as sent but are not delivered.** Meta only accepts free-form `text` messages inside the 24-hour customer-service window; business-initiated messages need an approved template. The API still returns 200, the failure arrives later by webhook (which we don't receive), so the log says `SENT`. Most WhatsApp broadcast recipients never get the message.
3. **Email "sent" without sending.** When `RESEND_API_KEY` is missing, `ResendClient` returns `True` and logs `SENT`. A misconfigured production deploy would silently drop every email, including OTPs and invoices, while reporting success.
4. **Broadcasts are lost on restart.** Dispatch runs in-process (`BackgroundTasks` + thread pool). A deploy or crash mid-send leaves the campaign `queued` forever, with no resume and no record of who was not reached. Status is set to `sent` even when every message failed.

### High

5. **Permission not enforced.** The UI gates the hub on `manage_communications`, but every API route uses `get_admin_user`. Any internal employee can email or WhatsApp the whole customer base. (`common/permissions.py` confirms the permission is UI-only.)
6. **No marketing consent or opt-out.** `all_members` ignores `marketing_consent`; there is no unsubscribe link, no `List-Unsubscribe`/one-click header, and no suppression list. This conflicts with the Kenya Data Protection Act 2019 (direct-marketing consent and opt-out) and with Gmail/Yahoo bulk-sender rules, which will route our mail to spam.
7. **Email sending collapses at scale.** Up to 10 threads call Resend one email per request; Resend's default rate limit is far lower, so large sends hit 429s, retry three times one second apart, and are marked `FAILED`. The batch endpoint (100 per call) is not used.
8. **Emailing arbitrary external addresses.** `custom_selection` sends to any typed address that is not a user, from the company domain, with no consent basis.
9. **No accountability.** Broadcasts record no author, approver, or audit-log entry. `AuditLog` exists and is used by finance, not here.
10. **Two broadcast implementations.** `/notifications/broadcast` sends synchronously in the request, to all users including deactivated and deleted ones, with no campaign record.

### Medium

11. **HTML injection into outgoing email.** `{{first_name}}` is replaced with the user's raw name inside HTML; a user named `<a href=...>` puts a link into mail sent from our domain.
12. **Retry logic is wrong.** The first failed attempt writes `FAILED` before retrying; the `except` path references `log` which may be unbound; 4xx (permanent) errors are retried; backoff is a constant 1s despite the comment. No `provider_message_id` is stored, so nothing can be correlated later.
13. **Unknown audiences fall through to "all treasurers".** A typo in `target_type` silently broadcasts to every treasurer.
14. **Template edits vanish on deploy** (written into the container image), with no versioning, diff or audit.
15. **`DELETE /notifications/clear-all` is unreachable**: it is declared after `DELETE /notifications/{notification_id}`, so it 404s with id `clear-all`.
16. **Data model gaps.** `communication_logs` has no indexes on `campaign_id`, `user_id`, `status`, `created_at`; channel values mix `EMAIL` and `email`; "campaign" collides with the fundraising `Campaign` domain model.
17. **Unbounded queries.** Broadcast list and recipient drill-down return every row; `get_unread_count` loads all rows to count them.
18. **WhatsApp API pinned to `v17.0`**, a Graph API version past its support window.
19. **Contact inquiries** accept any string as status, are unpaginated, and cannot be replied to from the hub.

### Low (UI)

20. UI offers "SMS" in copy and "Best practices", but there is no SMS provider.
21. Preview shows raw HTML, not the branded template, and ignores personalization.
22. No recipient count before send, no test send, no draft, no schedule, no cancel.
23. History has no delivery stats; logs are fixed to page 1 with no filters or search.
24. `replace("_", " ")` only replaces the first underscore ("all members" vs "marketing opt_in").

**Overall grade: E.** It sends messages in the happy path at small scale, but it misreports delivery, has an RCE, ignores consent, and loses work on restart.

## 3. Target architecture

A dedicated `services/communications/` package (same shape as `services/admin/finance/`), owning every outbound message, transactional and marketing.

```
 Composer / API          Audience resolver             Outbox (DB)                 Dispatcher worker              Providers
 ───────────────         ──────────────────            ───────────                 ─────────────────              ─────────
 draft → review   ──►   segment → users         ──►   comm_messages rows   ──►   claim (SKIP LOCKED)    ──►   Resend (batch)
 test send               − no consent                  one per recipient          rate-limit per provider        Meta WhatsApp (templates)
 schedule / approve      − suppressed                  × channel, idempotent      retry w/ backoff (5xx/429)     In-app (DB)
                         − deduped, snapshot                                       priority: transactional first  (SMS: later)
                                                                                           │
                         Webhooks (Resend, Meta)  ──►  comm_message_events  ──►  status, stats, auto-suppress on bounce/complaint
```

Principles:

- **Outbox, not threads.** Every message is a row before it is sent. A worker claims rows with `SELECT … FOR UPDATE SKIP LOCKED`, so restarts resume and two workers never double-send. A unique key `(broadcast_id, user_id, channel)` makes enqueueing idempotent.
- **Truthful status.** `queued → sending → sent → delivered/opened/clicked` or `bounced/complained/failed/suppressed`. "Delivered" only comes from the provider webhook.
- **Consent and suppression are enforced at resolve time**, not by the composer: message category (`service`, `product_updates`, `marketing`) decides what consent is required; hard bounces, complaints and unsubscribes suppress the destination permanently.
- **One template system**: templates live in the DB, versioned, rendered with Jinja's `SandboxedEnvironment` and autoescaping; personalization values are escaped.
- **One send API** for the rest of the codebase: `communications.send(user, template, context, category)` replaces the ~22 ad-hoc call sites, and gets priority over bulk sends so a 20k broadcast never delays an OTP.
- **Least privilege.** `manage_communications` enforced on every route; marketing broadcasts above a recipient threshold need a second person to approve (mirrors finance refunds).

### Data model (new tables)

| Table | Purpose |
|---|---|
| `comm_broadcasts` | Name, category, status (`draft/scheduled/awaiting_approval/sending/completed/cancelled`), audience definition (JSON), channels, per-channel content, author, approver, schedule, started/completed, denormalized stats |
| `comm_messages` | Outbox and delivery record: recipient, channel, destination, rendered content ref, status, attempts, `next_attempt_at`, provider + `provider_message_id` (indexed), error, timestamps per state, priority |
| `comm_message_events` | Raw provider webhook events (delivered, opened, clicked, bounced, read…) |
| `comm_templates` / `comm_template_versions` | Versioned templates per channel; WhatsApp entries map to Meta-approved template names |
| `comm_suppressions` | Destination-level blocks with reason (unsubscribe, hard bounce, complaint, WhatsApp block) |
| `comm_preferences` | Per-user, per-category, per-channel opt-in, plus signed unsubscribe tokens |

Existing `broadcast_campaigns` and `communication_logs` rows are migrated into the new tables, then the old tables are dropped in a later release.

## 4. Delivery plan

Each phase ships backend, frontend and tests together, so the hub is never half-migrated.

| Phase | Outcome |
|---|---|
| **1. Foundations and critical fixes** | New package and tables with data migration; outbox + dispatcher worker; Resend batch adapter, honest failure when unconfigured; WhatsApp adapter with configurable API version; `manage_communications` enforced; consent filtering, suppression list, one-click unsubscribe; template RCE closed (sandbox, DB-stored templates); legacy `/notifications/broadcast` removed; notifications bugs fixed; audit logging. UI updated to the new API. |
| **2. Broadcast lifecycle** | Drafts, audience estimate, test send, schedule, cancel, approval rule, WhatsApp approved-template sending, live stats in history. |
| **3. Delivery intelligence** | Resend and Meta webhooks (signed), delivered/open/click/read tracking, auto-suppression on bounce/complaint, overview dashboard and per-broadcast funnel, log filters and export. |
| **4. Unified sending** | Route the ~22 transactional call sites through `communications.send()`; one template registry; user-facing preference centre; reply to inquiries from the hub. |
| **5. Growth (optional)** | SMS channel, saved segments, A/B subject tests, automated journeys (onboarding, trial-ending, win-back). |

## 5. Decisions (2026-10-08)

1. **Approval**: marketing broadcasts reaching more than a threshold (system config `comm_marketing_approval_threshold`, default 500) need a second employee with `manage_communications`. Service broadcasts and small marketing sends go straight out.
2. **WhatsApp**: broadcasts send Meta-approved templates only (name, language, body variables).
3. **SMS**: deferred to Phase 5; the provider interface leaves room for it.

## 6. Phase 1 status: built

Backend `services/communications/`, migration `4f8a2c6d9e10`, tests `tests/test_communications_phase1.py`; admin UI under `/admin/communications/*` and the public `/unsubscribe` page.

Configuration:

| Variable | Purpose |
|---|---|
| `PUBLIC_API_URL` | Public base URL of the API. Enables RFC 8058 one-click `List-Unsubscribe` headers (needed by Gmail/Yahoo for bulk mail). Without it, emails still carry the footer unsubscribe link. |
| `BROADCAST_FROM_EMAIL`, `BROADCAST_REPLY_TO` | Sender and reply-to for broadcasts (default to `DEFAULT_FROM_EMAIL` and support@). |
| `META_API_VERSION` | Graph API version, default `v23.0`. |
| `COMM_DISPATCHER_ENABLED`, `COMM_DISPATCH_INTERVAL` | Turn the outbox worker off, or change its poll interval (seconds, default 5). |
| `COMM_EMAIL_BATCH_INTERVAL` | Seconds between 100-email batches (default 0.6, under Resend's default rate limit). |
| `COMM_MOCK_PROVIDERS` | Allow mock sending outside `IS_LOCAL` (staging). Never set in production. |

Not in Phase 1: delivery/open webhooks (sent means "accepted by the provider"), test sends, drafts, and moving the ~22 transactional call sites onto the outbox. The old `broadcast_campaigns` table and the broadcast rows in `communication_logs` are kept for one release.
