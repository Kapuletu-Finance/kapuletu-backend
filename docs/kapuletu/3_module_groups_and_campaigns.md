# 3. Module: Groups and Campaigns

This module manages the core structural hierarchy of KapuLetu. Financial transactions must logically belong to a Group, and can optionally be attributed to specific Campaigns (fundraising goals) within that Group.

## 3.1 Group Architecture (The Tenant Unit)
A Group is the highest-level organizational unit under a Treasurer (e.g., "St. Peter's Welfare", "Family Contribution Fund").

### 3.1.1 Exact Data Fields & Validations
*(Derived from `models/group.py` and `GroupOut` schema)*
*   **Identifiers:** `id` (UUID, Primary Key), `owner_id` (UUID, Foreign Key linking strictly to `users.user_id`).
*   **Metadata:** 
    *   `name` (String, strictly 1-100 chars).
    *   `description` (String, max 500 chars).
*   **Financial Settings:** 
    *   `currency` (String/Enum). The Pydantic schema strictly enforces validation via `CurrencyEnum` (allowed values: `KES`, `USD`, `EUR`, `GBP`).
    *   *Immutability Constraint:* The `currency` field is intentionally stripped from the `GroupUpdate` payload, ensuring it can never be altered via the API after initial creation.
*   **State & Lifecycle:** `status` (`GroupStatusEnum`: active/archived), `is_active` (Boolean), `created_at` (Datetime).
*   **Extensibility:** `settings_override` (JSON dict for custom group-level configurations).

### 3.1.2 Security & Operational Logic
*   **Tenant Isolation:** Every operation in the `services/groups/router.py` utilizes `current_user.get('sub')` to perform an explicit check: `str(group.owner_id) != current_user.get('sub')`. Cross-tenant data leakage is structurally prevented at the router level.
*   **Soft Deletes:** The API does not expose a `DELETE` SQL command. Archiving a group updates `status` to "archived" and `is_active` to `False`, protecting historical immutable ledgers tied to that group.

## 3.2 Campaign Architecture (The Goal Unit)
A Campaign represents a specific target operating *inside* a Group (e.g., "Church Roof Fund"). 

### 3.2.1 Exact Data Fields
*(Derived from `models/campaign.py` and `CampaignOut` schema)*
*   **Identifiers:** `id` (UUID, Primary Key), `group_id` (UUID, Foreign Key linking to `groups.group_id`).
*   **Metadata:** 
    *   `title` (String, 1-100 chars).
    *   `description` (String, max 1000 chars).
    *   `payment_instructions` (String, max 1000 chars).
*   **Financial Targets:** 
    *   `target_amount` (Float, enforced `ge=0` in schema).
*   **State:** `status` (active/archived), `is_active` (Boolean), `created_at`.
*   **Extensibility:** `settings_override` (JSON dict).

### 3.2.2 Inherited Security
Campaign APIs utilize a `_verify_group_ownership(db, group_id, owner_id)` dependency. Before a campaign can be created, updated, or archived, the system checks if the requesting Treasurer actually owns the parent Group.

---

## 3.3 Architectural Flaws, Gaps & Missing Implementations
*(Audited strictly for Enterprise Performance & API Completeness)*

1.  **Disastrous Stats Performance (In-Memory Aggregation):** 
    *   *Flaw:* The `Campaign` table lacks cached operational metrics (`amount_raised`, `percentage_complete`). To generate Campaign Stats on the dashboard (`services/reporting/router.py`), the system executes a catastrophic pattern: it fetches **all valid ledger entries** into memory (`ledger.entries`), iterates over them in a Python `for` loop, and maps amounts to campaign IDs.
    *   *Risk:* In production, an organization with tens of thousands of transactions will hit severe memory limits and timeout failures on AWS Lambda.
2.  **Missing Pagination Metadata:**
    *   *Flaw:* While `list_groups` and `list_campaigns` accept `skip` and `limit` query parameters, the response is a flat JSON Array (`List[CampaignOut]`).
    *   *Gap:* There is no surrounding metadata object returning `total_items`, `total_pages`, or `has_next`. An enterprise frontend cannot render a functional pagination component without this data.
3.  **Complete Lack of Search & Filtering:**
    *   *Flaw (Search):* The routers do not support a `?search=` parameter. Treasurers cannot query or filter campaigns by title via the API.
    *   *Flaw (Status Filtering):* The repository functions (`get_owner_groups`, `get_group_campaigns`) hardcode `is_active == True`. Because there is no status toggle parameter (e.g., `?status=archived`), Treasurers have **absolutely no way to view their archived campaigns or groups** via the API once they delete them.
4.  **Vulnerability to Resource Abuse:**
    *   *Risk:* A malicious script could flood the system with 50,000 campaigns, bloating the PostgreSQL RDS instance without restriction.

---

## Adjustments, Corrections, and Resolutions
*(End-to-End fixes applied based on the audit)*

### 1. Stats Performance Overhauled (N+1 Query Fixed)
*   **Fix:** Instead of pulling transactions into memory, `get_owner_groups` and `get_group_campaigns` were refactored to utilize SQLAlchemy `func.count()` and `func.sum()` combined with `group_by`.
*   **Implementation:** The API now executes optimized aggregate queries directly inside PostgreSQL, securely calculating `total_raised`, `progress_percentage`, and `contributor_count` for campaigns in milliseconds.

### 2. Pagination Standardized (PaginatedResponse Schema)
*   **Fix:** Replaced the flat `List[]` responses with `PaginatedGroupResponse` and `PaginatedCampaignResponse`.
*   **Implementation:** `GET /groups` and `GET /campaigns` now return the standardized payload `{"items": [...], "total_items": 10, "total_pages": 1, "page": 1, "limit": 10}`, enabling fully functional frontend table components.

### 3. Search and Status Filtering Added
*   **Fix:** Added `search` and `group_status`/`campaign_status` query parameters to the router and repository layers.
*   **Implementation:** Treasurers can now freely search for campaigns/groups by name via the API. By supplying `status=all` or `status=archived`, they can also view their deleted records.

### 4. Creation Rate Limiting
*   **Fix:** Integrated `slowapi` decorators (`@limiter.limit("50/minute")`).
*   **Implementation:** Ensures that malicious agents cannot overwhelm the KapuLetu API by mass-creating groups or scraping data beyond normal human speeds.