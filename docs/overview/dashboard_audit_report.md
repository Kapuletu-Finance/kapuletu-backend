# Treasurer Dashboard Audit Report

## 1. Current State of the Dashboard

Currently, the backend has **one primary endpoint** serving dashboard data:
`GET /reports/dashboard` (located in `services/reporting/router.py`).

**What it currently provides (`DashboardOverviewOut`):**
- **Stats:** `total_collected` and `transaction_count`.
- **Time-Series Data:** `daily_collections_7_days` (for drawing the 7-day revenue chart).
- **Overview:** `campaign_breakdown` (a list of all campaigns with their targets, total raised, and progress percentages).
- **Recent Activities:** `recent_activity` (returns the top 10 most recent financial transactions).

## 2. Identified Gaps ("Picture of the Workspace")

While the current endpoint is excellent for a **financial ledger summary**, it falls short of providing a complete "picture of the workspace" for a Treasurer. 

Here is what is missing from the current dashboard data:
1. **Entity Overview:** There are no statistics on the number of active **Groups** or total **Members** the treasurer manages.
2. **Actionable Tasks:** The dashboard doesn't indicate if there are pending items requiring the treasurer's attention (e.g., transactions awaiting manual approval in the `approval` service).
3. **Subscription/Plan Context:** It lacks workspace context, such as the user's current subscription plan (e.g., "Free Plan" vs "Premium"), which is critical since many features (like AI Auto-Approve or White-labeling) are feature-gated.
4. **Broader Activity Scope:** The current "Recent Activity" is strictly limited to financial transactions. A true workspace overview might also include **Audit Logs** (e.g., "Group X created," "Campaign Y settings updated").

## 3. Recommendations

To build a truly holistic dashboard, I recommend one of the following approaches:

### Option A: Create a New "Workspace" Endpoint (Highly Recommended)
Create a new dedicated endpoint, e.g., `GET /workspace/overview` (perhaps in a new `workspace` router or within an existing administrative router).
- **How it works:** This endpoint acts as an orchestrator. It fetches financial stats from the `LedgerService`, group counts from the `group_repo`, pending approvals from the `ApprovalService`, and subscription status from the `Subscription` models.
- **Why it's best:** It maintains clean architecture. The `reporting` service remains strictly focused on ledger/financial reports, while the `workspace` endpoint serves the UI's specific need for a multi-domain summary.

### Option B: Expand the Current Reporting Endpoint
We can augment the existing `DashboardOverviewOut` schema in `reporting` to include the missing fields.
- **Add fields:** `total_groups: int`, `pending_approvals: int`, `current_plan: str`.
- **Why it's good:** It requires only a single API call for the frontend to render the entire dashboard page, minimizing latency.
- **Drawback:** It creates a "god endpoint" in the reporting service, tightly coupling it to every other domain (Groups, Approvals, Subscriptions).

### Option C: Frontend Aggregation
Keep `GET /reports/dashboard` exactly as it is for the financial widgets. Have the frontend make concurrent requests to other existing endpoints (`GET /groups`, `GET /users/me`, etc.) to fill in the rest of the workspace picture.
- **Why it's good:** Purely RESTful; requires zero backend architectural changes right now.
- **Drawback:** Requires the frontend to handle multiple network requests and aggregate the data itself, which can increase load times on slower networks.

---

> [!TIP]
> If you want to proceed with **Option A**, we can implement a new `WorkspaceRouter` that aggregates this data cleanly. Let me know which direction you'd like to take!
