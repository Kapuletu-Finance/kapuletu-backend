# Implement Workspace Overview Endpoint

This plan outlines the architecture and implementation for the new `GET /workspace/overview` endpoint. This endpoint will serve as the "Home of the Workspace," providing the treasurer with an immediate, aggregated snapshot of their system upon login.

## Proposed Changes

We will introduce a new `workspace` module to orchestrate the fetching of data from other domain services, keeping the architecture clean and separated.

### 1. New Workspace Module

#### [NEW] [services/workspace/schemas.py](file:///c:/Users/josep/kapuletu-backend/services/workspace/schemas.py)
Create the Pydantic models for the dashboard.
- `WorkspaceOverviewOut`: The main response model containing:
  - `total_groups: int`
  - `total_campaigns: int`
  - `total_members: int`
  - `pending_approvals: int`
  - `total_collected: float`
  - `subscription: SubscriptionOverview` (Plan name, status, days remaining)
  - `active_groups: List[GroupOverview]` (A quick summary of the user's groups)
  - `recent_activities: List[AuditActivity]` (Top 5-10 recent system events from the audit log)

#### [NEW] [services/workspace/router.py](file:///c:/Users/josep/kapuletu-backend/services/workspace/router.py)
Create the `APIRouter` containing:
- `GET /overview`: The orchestrator endpoint.
  - Queries `group_repo`, `campaign_repo`, and `member_repo` (if applicable) for aggregate counts.
  - Queries `transaction_repo` for the number of pending manual approvals.
  - Uses `LedgerService` to get the global `total_collected` amount.
  - Queries `Subscription` to fetch the current plan status.
  - Queries `AuditLog` to get recent workspace activity events (e.g., settings changed, groups created).

### 2. Update Application Entrypoint

#### [MODIFY] [main.py](file:///c:/Users/josep/kapuletu-backend/main.py)
- Import the new `workspace` router and include it in the FastAPI application setup (e.g., `app.include_router(workspace_router)`).

## User Review Required

> [!NOTE]
> Please review the schema fields proposed above. Let me know if you would like to include any other specific statistics or context in the workspace overview before I begin execution.

## Verification Plan

### Automated/Manual Verification
- I will make an HTTP request to `GET /workspace/overview` against the local development server (using a test user or dummy token context, if available, or a test script).
- Verify that the API correctly aggregates data across all domains without circular dependency issues.
- Verify that the Swagger UI (`/docs`) accurately reflects the new workspace schema.
