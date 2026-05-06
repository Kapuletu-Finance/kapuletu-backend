from fastapi import FastAPI, Request, Response, APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json

# Import Handlers
from services.ingestion.handler import handler as ingestion_handler
from services.approval.handler import handler as approval_handler
from services.reporting.handler import handler as reporting_handler
from services.members.handler import handler as members_handler
from services.campaigns.handler import handler as campaigns_handler

app = FastAPI(
    title="KapuLetu Treasury API — Full Specification",
    description="Local development bridge mapping every endpoint from the technical specification (v1).",
    version="1.0.0",
)

# --- Pydantic Schemas for Swagger UI ---

class TransactionIn(BaseModel):
    Body: str = Field(..., json_schema_extra={"example": "KES 1500 from Jane Doe for Welfare"})
    From: str = Field(..., json_schema_extra={"example": "+254700000000"})
    MessageSid: Optional[str] = Field(None, json_schema_extra={"example": "SM12345"})

class GroupIn(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "St. Peters Welfare"})

class CampaignIn(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "Hospital Fund"})
    target_amount: float = Field(..., json_schema_extra={"example": 50000.0})

class SplitAllocation(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "John Doe"})
    amount: float = Field(..., json_schema_extra={"example": 500.0})

class TransactionSplit(BaseModel):
    allocations: List[SplitAllocation]

# --- Lambda Adapter Logic ---

async def lambda_adapter(request: Request, handler):
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    
    event = {
        "body": body_str,
        "httpMethod": request.method,
        "headers": dict(request.headers),
        "queryStringParameters": dict(request.query_params),
        "path": request.url.path,
        "pathParameters": request.path_params,
        "isBase64Encoded": False
    }
    
    try:
        response = handler(event, None)
        return Response(
            content=response.get("body", ""),
            status_code=response.get("statusCode", 200),
            headers=response.get("headers", {"Content-Type": "application/json"})
        )
    except Exception as e:
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            headers={"Content-Type": "application/json"}
        )

async def placeholder(request: Request):
    return {
        "status": "error",
        "code": "NOT_IMPLEMENTED",
        "message": f"The endpoint {request.method} {request.url.path} is pending implementation."
    }

# --- API Routers ---

# 2. Authentication
auth = APIRouter(prefix="/auth", tags=["2. Authentication"])
@auth.post("/register", summary="Register Treasurer")
async def register(request: Request): return await placeholder(request)
@auth.post("/login", summary="Login")
async def login(request: Request): return await placeholder(request)
@auth.post("/refresh", summary="Refresh Token")
async def refresh(request: Request): return await placeholder(request)
@auth.post("/logout", summary="Logout")
async def logout(request: Request): return await placeholder(request)
@auth.get("/me", summary="Get Current User")
async def get_me(request: Request): return await placeholder(request)
@auth.patch("/me", summary="Update Profile")
async def update_profile(request: Request): return await placeholder(request)
@auth.post("/change-password", summary="Change Password")
async def change_password(request: Request): return await placeholder(request)
@auth.post("/forgot-password", summary="Request Password Reset")
async def forgot_password(request: Request): return await placeholder(request)
@auth.post("/reset-password", summary="Reset Password")
async def reset_password(request: Request): return await placeholder(request)
@auth.post("/verify", summary="Verify Phone / Email")
async def verify(request: Request): return await placeholder(request)

# 3. Groups Management
groups = APIRouter(prefix="/groups", tags=["3. Groups Management"])
@groups.post("", summary="Create Group")
async def create_group(payload: GroupIn): return await placeholder(None)
@groups.get("", summary="Get All My Groups")
async def list_groups(request: Request): return await placeholder(request)
@groups.get("/{group_id}", summary="Get Single Group")
async def get_group(group_id: str): return await placeholder(None)
@groups.patch("/{group_id}", summary="Update Group")
async def update_group(group_id: str): return await placeholder(None)
@groups.delete("/{group_id}", summary="Archive Group")
async def archive_group(group_id: str): return await placeholder(None)

# 4. Campaigns Management
campaigns = APIRouter(tags=["4. Campaigns Management"])
@campaigns.post("/groups/{group_id}/campaigns", summary="Create Campaign")
async def create_campaign(request: Request, group_id: str, payload: CampaignIn): return await lambda_adapter(request, campaigns_handler)
@campaigns.get("/groups/{group_id}/campaigns", summary="List Campaigns")
async def list_group_campaigns(request: Request, group_id: str): return await lambda_adapter(request, campaigns_handler)
@campaigns.get("/campaigns/{campaign_id}", summary="Get Campaign")
async def get_campaign(campaign_id: str): return await lambda_adapter(None, campaigns_handler)
@campaigns.patch("/campaigns/{campaign_id}", summary="Update Campaign")
async def update_campaign(campaign_id: str): return await lambda_adapter(None, campaigns_handler)
@campaigns.post("/campaigns/{campaign_id}/status", summary="Change Campaign Status")
async def campaign_status(campaign_id: str): return await lambda_adapter(None, campaigns_handler)

# 5. Transaction Ingestion
ingestion = APIRouter(tags=["5. Transaction Ingestion"])
@ingestion.post("/ingestion/webhook", summary="Webhook (Twilio / External)")
async def ingestion_webhook_schema(payload: TransactionIn): return Response(status_code=200)
@app.post("/ingestion/webhook", include_in_schema=False)
async def ingestion_webhook_impl(request: Request): return await lambda_adapter(request, ingestion_handler)
@ingestion.post("/transactions/manual", summary="Manual Entry")
async def manual_entry(request: Request): return await placeholder(request)
@ingestion.get("/transactions/pending", summary="Get Pending Transactions (Inbox)")
async def get_pending(request: Request): return await lambda_adapter(request, approval_handler)
@ingestion.get("/transactions/pending/{pending_id}", summary="Get Single Pending")
async def get_pending_single(pending_id: str): return await lambda_adapter(None, approval_handler)

# 6. Parsing & Validation
parsing = APIRouter(prefix="/transactions", tags=["6. Parsing & Validation"])
@parsing.post("/{pending_id}/reparse", summary="Re-parse Message")
async def reparse(pending_id: str): return await placeholder(None)
@parsing.post("/{pending_id}/validate", summary="Validate Transaction")
async def validate_tx(pending_id: str): return await placeholder(None)

# 7. Review & Approval
review = APIRouter(prefix="/transactions", tags=["7. Review & Approval Workflow"])
@review.post("/{pending_id}/approve", summary="Approve Transaction")
async def approve(request: Request, pending_id: str): return await lambda_adapter(request, approval_handler)
@review.post("/{pending_id}/reject", summary="Reject Transaction")
async def reject(request: Request, pending_id: str): return await lambda_adapter(request, approval_handler)
@review.patch("/{pending_id}", summary="Edit Transaction")
async def edit_tx(request: Request, pending_id: str): return await lambda_adapter(request, approval_handler)
@review.post("/{pending_id}/note", summary="Add Note")
async def add_note(pending_id: str): return await placeholder(None)
@review.post("/{pending_id}/split", summary="Split Transaction")
async def split_tx(payload: TransactionSplit, pending_id: str): return await placeholder(None)
@review.post("/bulk/approve", summary="Bulk Approval")
async def bulk_approve(request: Request): return await placeholder(request)
@review.post("/bulk/reject", summary="Bulk Reject")
async def bulk_reject(request: Request): return await placeholder(request)

# 8. Ledger
ledger = APIRouter(prefix="/ledger", tags=["8. Ledger (Immutable)"])
@ledger.get("", summary="Get Ledger Entries")
async def list_ledger(request: Request): return await placeholder(request)
@ledger.get("/campaign/{campaign_id}", summary="Get Ledger by Campaign")
async def ledger_by_campaign(campaign_id: str): return await placeholder(None)
@ledger.get("/{ledger_id}", summary="Get Ledger Entry")
async def get_ledger_entry(ledger_id: str): return await placeholder(None)

# 9. Members
members = APIRouter(tags=["9. Members Management"])
@members.get("/members/suggestions", summary="Auto-Suggest Members")
async def suggest_members(request: Request): return await placeholder(request)
@members.post("/members", summary="Create Member (Optional)")
async def create_member(request: Request): return await lambda_adapter(request, members_handler)
@members.get("/groups/{group_id}/members", summary="Get Members")
async def group_members(group_id: str): return await lambda_adapter(None, members_handler)

# 10. Reporting
reporting = APIRouter(prefix="/reports", tags=["10. Reporting Service"])
@reporting.get("/daily", summary="Daily Summary")
async def daily_report(request: Request): return await lambda_adapter(request, reporting_handler)
@reporting.get("/campaign/{campaign_id}", summary="Campaign Progress")
async def campaign_report(campaign_id: str): return await lambda_adapter(None, reporting_handler)
@reporting.get("/contributors/{campaign_id}", summary="Contributor List")
async def contributors_report(campaign_id: str): return await placeholder(None)
@reporting.get("/export/excel", summary="Export Excel")
async def export_excel(request: Request): return await lambda_adapter(request, reporting_handler)
@reporting.get("/export/pdf", summary="Export PDF")
async def export_pdf(request: Request): return await lambda_adapter(request, reporting_handler)
@reporting.get("/whatsapp-summary", summary="WhatsApp Summary Format")
async def whatsapp_summary(request: Request): return await placeholder(request)

# 11. Evidence
evidence = APIRouter(prefix="/transactions", tags=["11. Evidence Management"])
@evidence.get("/{pending_id}/evidence", summary="Get Transaction Evidence")
async def get_evidence(pending_id: str): return await placeholder(None)
@evidence.post("/{pending_id}/evidence", summary="Upload Evidence (Future)")
async def upload_evidence(pending_id: str): return await placeholder(None)

# 12. Audit Logs
audit = APIRouter(prefix="/audit", tags=["12. Audit Logs"])
@audit.get("/logs", summary="Get Audit Logs")
async def get_logs(request: Request): return await placeholder(request)
@audit.get("/logs/{entity_type}/{entity_id}", summary="Get Logs by Entity")
async def get_logs_by_entity(entity_type: str, entity_id: str): return await placeholder(None)

# 13. Notifications
notifications = APIRouter(prefix="/notifications", tags=["13. Notifications"])
@notifications.post("/send", summary="Send Confirmation (After Approval)")
async def send_notification(request: Request): return await placeholder(request)

# 14. System Health
health = APIRouter(tags=["14. System Health & Admin"])
@health.get("/health", summary="Health Check")
async def health_check(): return {"status": "healthy"}
@health.get("/metrics", summary="Metrics")
async def metrics_check(): return {"metrics": "..."}

# --- Include All Routers ---
app.include_router(auth)
app.include_router(groups)
app.include_router(campaigns)
app.include_router(ingestion)
app.include_router(parsing)
app.include_router(review)
app.include_router(ledger)
app.include_router(members)
app.include_router(reporting)
app.include_router(evidence)
app.include_router(audit)
app.include_router(notifications)
app.include_router(health)

# Serve static assets (Logo, Favicons, etc.)
from fastapi.staticfiles import StaticFiles
import os
if os.path.exists("assets"):
    app.mount("/assets", StaticFiles(directory="assets"), name="assets")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>KapuLetu Developer Portal</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root { --primary: #0A2540; --accent: #CFA94B; --text: #111; --subtext: #666; --bg: #fafafa; }
            body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
            .box { background: white; padding: 56px; border-radius: 2px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid #eee; max-width: 480px; width: 90%; text-align: center; }
            .logo { width: 100px; height: auto; margin-bottom: 32px; }
            .tag { display: inline-block; background: #F6F9FC; padding: 6px 12px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--primary); margin-bottom: 24px; border: 1px solid #E6EBF1; }
            h1 { font-size: 26px; margin: 0 0 16px 0; font-weight: 700; color: var(--primary); letter-spacing: -0.02em; }
            p { font-size: 15px; color: var(--subtext); line-height: 1.6; margin: 0 0 40px 0; }
            .btn { display: block; padding: 14px; border-radius: 6px; text-decoration: none; font-size: 15px; font-weight: 600; text-align: center; transition: 0.2s cubic-bezier(0.165, 0.84, 0.44, 1); }
            .btn-black { background: var(--primary); color: white; margin-bottom: 12px; border: 1px solid var(--primary); }
            .btn-black:hover { background: #000; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(10,37,64,0.15); }
            .btn-white { background: white; color: var(--primary); border: 1px solid #E6EBF1; }
            .btn-white:hover { background: #F6F9FC; border-color: #CFA94B; }
            .footer { margin-top: 48px; font-size: 12px; color: #999; border-top: 1px solid #F6F9FC; padding-top: 24px; display: flex; justify-content: space-between; }
            .dot { color: #00D664; margin-right: 4px; }
        </style>
    </head>
    <body>
        <div class="box">
            <img src="/assets/logo.jpg" alt="KapuLetu" class="logo" onerror="this.src='https://via.placeholder.com/100x100?text=KapuLetu'">
            <div class="tag">Local Service Bridge</div>
            <h1>Developer Environment</h1>
            <p>Direct interface for testing the Treasury API core. All 50+ endpoints from the v1 technical specification are mapped to active Lambda handlers or production placeholders.</p>
            <a href="/docs" class="btn btn-black">Launch API Explorer</a>
            <a href="/redoc" class="btn btn-white">Technical Documentation</a>
            <div class="footer">
                <span><span class="dot">●</span> System Live</span>
                <span>v1.0.0</span>
            </div>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
