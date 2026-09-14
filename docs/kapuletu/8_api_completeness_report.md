# 8. API Completeness Report

This document serves as the final audit of the KapuLetu Backend API. It aggregates all missing endpoints, structural flaws, and performance vulnerabilities discovered across the 7 core modules. 

The current API lacks several critical enterprise-grade features required for scaling, security, and a rich frontend user experience.

---

## 8.1 Missing Search, Filters & Pagination (Data Fetching Flaws)
The current data retrieval endpoints are built for small datasets and lack enterprise querying capabilities.

*   **Missing Search & Status Filters:** 
    *   `GET /groups` and `GET /campaigns` lack `?search=` parameters. A Treasurer cannot search for a campaign by title.
    *   There is no `?status=` filter. Treasurers have absolutely no way to view "archived" or "completed" campaigns once they are inactive.
*   **Missing Pagination (Memory Crash Risk):**
    *   Endpoints like the Pending Inbox (`fetch_pending_transactions_by_owner`) execute `.all()` queries without `?page=` or `?limit=` constraints. 
    *   *Risk:* A viral campaign will result in thousands of rows loaded into API memory simultaneously, crashing the AWS Lambda container. Standard Limit/Offset pagination is strictly required across all list endpoints.

## 8.2 Missing Analytics & Aggregated Stats Endpoints
The frontend requires rich contextual data to build a premium dashboard, but the current endpoints return "bare-bones" database rows without statistical aggregations.

*   **Group Stats Missing:** 
    *   `GET /groups` only returns the group's name and description. 
    *   *Required Fields to Add:* `total_campaigns_count`, `active_campaigns`, and `total_funds_raised_for_group`.
*   **Campaign Stats Missing in List Views:** 
    *   `GET /campaigns` does not return real-time financial progress. To display a progress bar on a list of campaigns, the frontend would have to execute a catastrophic N+1 query against the reporting engine.
    *   *Required Fields to Add:* `total_raised`, `target_amount`, `progress_percentage`, and `total_contributor_count`.
*   **Treasurer Workspace Stats:** 
    *   There is no lightweight `/workspace/stats` endpoint. Obtaining global totals currently forces a heavy, unoptimized ledger scan.

## 8.3 Missing CRUD Endpoints (Lifecycle Flaws)
*   **Campaign Management:** 
    *   There is a `POST /campaigns` endpoint, but no `PATCH /campaigns/{id}` or `DELETE /campaigns/{id}`. Treasurers cannot edit typos in campaign titles or soft-delete finished goals.
*   **Group Management:** 
    *   Groups cannot be edited or deleted once created.
*   *Solution:* Standard `PATCH` and soft-delete (`DELETE`) endpoints must be built for both Groups and Campaigns.

## 8.4 Missing Rate Limiting & Security Defenses
*   **Auth Vulnerability:** 
    *   `POST /auth/login` lacks brute-force rate limiting, making it vulnerable to credential stuffing attacks.
*   **Webhook Ingestion DoS Risk:** 
    *   Meta WhatsApp webhooks hit the database to resolve phone numbers *before* validating the sender's authorization. A malicious actor spamming the webhook will execute thousands of un-cached database queries, causing a Denial of Service (DoS) attack on the RDS instance.
*   *Solution:* Implement Redis-based rate limiting (e.g., `slowapi`) across all public and authentication endpoints.

## 8.5 Broken Asynchronous Workflows (Timeout Risks)
*   **PDF/Excel Exports:** 
    *   Generating reports happens synchronously in the API request loop. Exporting a 20,000-row ledger will exceed the standard 29-second AWS API Gateway timeout, resulting in a 504 error.
*   **AI Training Trigger:** 
    *   The Admin module triggers AI training via `subprocess.Popen()`. This is impossible in an AWS Lambda environment; the process will die instantly when the API returns a response.
*   *Solution:* Both heavy file generation and AI model retraining must be migrated to asynchronous AWS SQS Queues or ECS Tasks.

## 8.6 Architectural Rule Conflicts (Orphaned Code)
*   **Member Management Split:** 
    *   The API contains a `split_transaction` endpoint and a `ReviewAllocation` model designed to split a transaction across multiple specific "Members." 
    *   *Conflict:* The new product architecture explicitly dictates: *"We are not doing members management in this version."* These models and endpoints are therefore orphaned, cause N+1 query bugs in the reporting engine, and bloat the API.
    *   *Solution:* Deprecate and remove the `split_transaction` API and `ReviewAllocation` models to align strictly with the "Campaign-Only" architecture.
