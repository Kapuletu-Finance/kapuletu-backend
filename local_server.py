from __future__ import annotations
import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from services.approval.handler import handler as approval_handler
from services.auth.router import router as auth
from services.campaigns.handler import handler as campaigns_handler
from services.groups.router import router as groups

# Import Handlers
from services.ingestion.handler import handler as ingestion_handler
from services.members.handler import handler as members_handler
from services.reporting.handler import handler as reporting_handler

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

# --- Group Schemas (Moved to services/groups/schemas.py) ---

class CampaignIn(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "Medical Fund - Jane Doe"})
    description: Optional[str] = Field(None, json_schema_extra={"example": "Fundraising for hospital expenses."})
    target_amount: float = Field(..., json_schema_extra={"example": 50000.0})
    payment_instructions: Optional[str] = Field(None, json_schema_extra={"example": "Paybill 123456, Account: JANE"})

class SplitAllocation(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "John Doe"})
    amount: float = Field(..., json_schema_extra={"example": 500.0})

class TransactionSplit(BaseModel):
    allocations: List[SplitAllocation]

class ManualEntryIn(BaseModel):
    amount: float = Field(..., json_schema_extra={"example": 1500.0})
    sender_name: str = Field(..., json_schema_extra={"example": "Joseph Njoroge"})
    sender_phone: str = Field(..., json_schema_extra={"example": "+254700000000"})
    purpose: Optional[str] = Field(None, json_schema_extra={"example": "January Contribution"})
    transaction_code: Optional[str] = Field(None, json_schema_extra={"example": "MANUAL-12345"})

# --- Authentication Schemas (Moved to services/auth/schemas.py) ---
from services.auth.schemas import UpdateProfileIn

# --- Approval & Review Schemas ---

class TransactionActionIn(BaseModel):
    internal_note: Optional[str] = Field(None, json_schema_extra={"example": "Matched with paper receipt #123"})

class TransactionEditIn(BaseModel):
    extracted_amount: Optional[float] = Field(None, json_schema_extra={"example": 1500.0})
    extracted_sender_name: Optional[str] = Field(None, json_schema_extra={"example": "Joseph Amuyunzu"})
    extracted_code: Optional[str] = Field(None, json_schema_extra={"example": "ABC123XYZ"})
    extracted_date: Optional[str] = Field(None, json_schema_extra={"example": "2026-05-08"})

class BulkActionIn(BaseModel):
    pending_ids: List[str] = Field(..., json_schema_extra={"example": ["uuid-1", "uuid-2"]})
    internal_note: Optional[str] = Field(None, json_schema_extra={"example": "Bulk approval for Sunday collection"})

# --- Admin Governance Schemas ---

class AdminOverviewOut(BaseModel):
    total_treasurers: int = Field(..., json_schema_extra={"example": 1250})
    total_revenue_kes: float = Field(..., json_schema_extra={"example": 450000.0})
    active_subscriptions: int = Field(..., json_schema_extra={"example": 890})
    pending_tickets: int = Field(..., json_schema_extra={"example": 12})
    ai_accuracy_rate: float = Field(..., json_schema_extra={"example": 0.94})

class TreasurerStatusIn(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "suspended"})
    reason: str = Field(..., json_schema_extra={"example": "Suspicious login pattern detected from new IP."})

class AITrainingParamsIn(BaseModel):
    epochs: int = Field(10, json_schema_extra={"example": 15})
    dropout: float = Field(0.2, json_schema_extra={"example": 0.1})
    use_treasurer_feedback: bool = Field(True)

class SubscriptionPlanIn(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Pro Treasurer"})
    price: float = Field(..., json_schema_extra={"example": 1500.0})
    billing_period: str = Field("monthly", json_schema_extra={"example": "annual"})
    features: List[str] = Field(..., json_schema_extra={"example": ["Unlimited Groups", "AI Parsing"]})

class SystemBroadcastIn(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Platform maintenance scheduled for 10:00 PM EAT."})
    channel: str = Field("all", json_schema_extra={"example": "whatsapp"})
    target_role: str = Field("treasurer")

# --- Members & Notifications ---

class MemberIn(BaseModel):
    member_name: str = Field(..., json_schema_extra={"example": "John Wainaina"})
    member_phone: Optional[str] = Field(None, json_schema_extra={"example": "+254700000000"})
    group_id: str = Field(..., json_schema_extra={"example": "group-uuid"})

class NotificationIn(BaseModel):
    pending_id: str = Field(..., json_schema_extra={"example": "pending-uuid"})
    message_type: str = Field("confirmation", json_schema_extra={"example": "confirmation"})

# --- Finance & Subscription Schemas ---

class KapuletuCheckoutIn(BaseModel):
    plan_id: str = Field(..., json_schema_extra={"example": "pro"})
    provider: str = Field(..., json_schema_extra={"example": "flutterwave"}) # Options: mpesa, flutterwave, stripe (legacy)
    phone_number: Optional[str] = Field(None, json_schema_extra={"example": "+254700000000"})

class KapuletuCheckoutOut(BaseModel):
    checkout_id: str = Field(..., json_schema_extra={"example": "CH-123"})
    status: str = Field(..., json_schema_extra={"example": "initiated"})
    provider_response: Any = Field(None)

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

# 2. Authentication (Native FastAPI Router imported from services.auth.router)

# 3. Groups Management (Native FastAPI Router imported from services.groups.router)

# 4. Campaigns Management
campaigns = APIRouter(tags=["4. Campaigns Management"])
@campaigns.post("/groups/{group_id}/campaigns", summary="Create Campaign")
async def create_campaign(request: Request, group_id: str, payload: CampaignIn): return await lambda_adapter(request, campaigns_handler)
@campaigns.get("/groups/{group_id}/campaigns", summary="List Campaigns")
async def list_group_campaigns(request: Request, group_id: str): return await lambda_adapter(request, campaigns_handler)
@campaigns.get("/campaigns/{campaign_id}", summary="Get Campaign")
async def get_campaign(request: Request, campaign_id: str): return await lambda_adapter(request, campaigns_handler)
@campaigns.patch("/campaigns/{campaign_id}", summary="Update Campaign")
async def update_campaign(request: Request, campaign_id: str): return await lambda_adapter(request, campaigns_handler)
@campaigns.post("/campaigns/{campaign_id}/status", summary="Change Campaign Status")
async def campaign_status(request: Request, campaign_id: str): return await lambda_adapter(request, campaigns_handler)

# 5. Transaction Ingestion
ingestion = APIRouter(tags=["5. Transaction Ingestion"])
@ingestion.post("/ingestion/webhook", summary="Webhook (Twilio / External)")
async def ingestion_webhook_schema(payload: TransactionIn): return Response(status_code=200)
@app.post("/ingestion/webhook", include_in_schema=False)
async def ingestion_webhook_impl(request: Request): return await lambda_adapter(request, ingestion_handler)

from services.ingestion.manual_handler import handler as manual_handler
@ingestion.post("/transactions/manual", summary="Manual Entry")
async def manual_entry(request: Request, payload: ManualEntryIn): return await lambda_adapter(request, manual_handler)

@ingestion.get("/transactions/pending", summary="Get Pending Transactions (Inbox)")
async def get_pending(request: Request): return await lambda_adapter(request, approval_handler)
@ingestion.get("/transactions/pending/{pending_id}", summary="Get Single Pending")
async def get_pending_single(request: Request, pending_id: str): return await lambda_adapter(request, approval_handler)

# 6. Parsing & Validation
parsing = APIRouter(prefix="/transactions", tags=["6. Parsing & Validation"])
@parsing.post("/{pending_id}/reparse", summary="Re-parse Message")
async def reparse(request: Request, pending_id: str): return await lambda_adapter(request, approval_handler)
@parsing.post("/{pending_id}/validate", summary="Validate Transaction")
async def validate_tx(request: Request, pending_id: str): return await lambda_adapter(request, approval_handler)

# 7. Review & Approval
review = APIRouter(prefix="/transactions", tags=["7. Review & Approval Workflow"])
@review.post("/{pending_id}/approve", summary="Approve Transaction")
async def approve(request: Request, pending_id: str, payload: Optional[TransactionActionIn] = None): return await lambda_adapter(request, approval_handler)
@review.post("/{pending_id}/reject", summary="Reject Transaction")
async def reject(request: Request, pending_id: str, payload: Optional[TransactionActionIn] = None): return await lambda_adapter(request, approval_handler)
@review.patch("/{pending_id}", summary="Edit Transaction")
async def edit_tx(request: Request, pending_id: str, payload: TransactionEditIn): return await lambda_adapter(request, approval_handler)
@review.post("/{pending_id}/note", summary="Add Note")
async def add_note(request: Request, pending_id: str, payload: TransactionActionIn): return await lambda_adapter(request, approval_handler)
@review.post("/{pending_id}/split", summary="Split Transaction")
async def split_tx(request: Request, payload: TransactionSplit, pending_id: str): return await lambda_adapter(request, approval_handler)
@review.post("/bulk/approve", summary="Bulk Approval")
async def bulk_approve(request: Request, payload: BulkActionIn): return await lambda_adapter(request, approval_handler)
@review.post("/bulk/reject", summary="Bulk Reject")
async def bulk_reject(request: Request, payload: BulkActionIn): return await lambda_adapter(request, approval_handler)

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
async def suggest_members(request: Request): return await lambda_adapter(request, members_handler)
@members.post("/members", summary="Create Member (Optional)")
async def create_member(request: Request, payload: MemberIn): return await lambda_adapter(request, members_handler)
@members.get("/groups/{group_id}/members", summary="Get Members")
async def group_members(request: Request, group_id: str): return await lambda_adapter(request, members_handler)

# 10. Reporting
reporting = APIRouter(prefix="/reports", tags=["10. Reporting Service"])
@reporting.get("/daily", summary="Daily Summary")
async def daily_report(request: Request): return await lambda_adapter(request, reporting_handler)
@reporting.get("/campaign/{campaign_id}", summary="Campaign Progress")
async def campaign_report(request: Request, campaign_id: str): return await lambda_adapter(request, reporting_handler)
@reporting.get("/contributors/{campaign_id}", summary="Contributor List")
async def contributors_report(request: Request, campaign_id: str): return await lambda_adapter(request, reporting_handler)
@reporting.get("/export/excel", summary="Export Excel")
async def export_excel(request: Request): return await lambda_adapter(request, reporting_handler)
@reporting.get("/export/pdf", summary="Export PDF")
async def export_pdf(request: Request): return await lambda_adapter(request, reporting_handler)
@reporting.get("/whatsapp-summary", summary="WhatsApp Summary Format")
async def whatsapp_summary(request: Request): return await lambda_adapter(request, reporting_handler)

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
async def send_notification(request: Request, payload: NotificationIn): return await placeholder(request)

# 14. System Health
health = APIRouter(tags=["14. System Health & Admin"])
@health.get("/health", summary="Health Check")
async def health_check(): return {"status": "healthy"}
@health.get("/metrics", summary="Metrics")
async def metrics_check(): return {"metrics": "..."}

# 15. Admin Governance Suite
admin = APIRouter(prefix="/admin/v1", tags=["15. Admin Governance Suite"])

@admin.get("/overview", summary="Platform Overview Statistics", response_model=AdminOverviewOut)
async def admin_overview():
    return {
        "total_treasurers": 1250,
        "total_revenue_kes": 450000.0,
        "active_subscriptions": 890,
        "pending_tickets": 12,
        "ai_accuracy_rate": 0.94
    }

@admin.get("/users/treasurers", summary="List All Treasurers")
async def list_treasurers(request: Request): return await placeholder(request)

@admin.get("/users/treasurers/{user_id}", summary="Get Treasurer Profile & Activity")
async def get_treasurer_profile(user_id: str): return await placeholder(None)

@admin.get("/users/treasurers/{user_id}/groups", summary="View Treasurer Groups")
async def get_treasurer_groups(user_id: str): return await placeholder(None)

@admin.get("/users/treasurers/{user_id}/payments", summary="View Treasurer Payment History")
async def get_treasurer_payments(user_id: str): return await placeholder(None)

@admin.patch("/users/treasurers/{user_id}", summary="Escalated Profile Update")
async def admin_update_user(user_id: str, payload: UpdateProfileIn): return await placeholder(None)

@admin.post("/users/treasurers/{user_id}/status", summary="Update Account Status (Suspend/Active)")
async def update_user_status(user_id: str, payload: TreasurerStatusIn): return await placeholder(None)

@admin.post("/ai/parser/train", summary="Trigger AI Model Training")
async def trigger_ai_training(payload: AITrainingParamsIn): return {"status": "accepted", "job_id": "job-123"}

@admin.get("/ai/parser/knowledge", summary="Review AI Knowledge Base")
async def review_ai_knowledge(): return await placeholder(None)

@admin.get("/ai/parser/feedback-queue", summary="Manage AI Feedback Loop")
async def ai_feedback_queue(): return await placeholder(None)

@admin.post("/finance/plans", summary="Create Subscription Plan")
async def create_plan(payload: SubscriptionPlanIn): return {"status": "created", "plan_id": "plan-xyz"}

@admin.get("/finance/plans", summary="List Subscription Plans")
async def list_plans(): return await placeholder(None)

@admin.get("/finance/payments", summary="Global Payment Records")
async def global_payments(): return await placeholder(None)

@admin.post("/finance/payments/override", summary="Manual Subscription Override")
async def manual_override(): return {"status": "success", "message": "Subscription updated"}

@admin.post("/crm/broadcast", summary="Platform-Wide Broadcast")
async def system_broadcast(payload: SystemBroadcastIn): return {"status": "sent", "recipient_count": 1250}

@admin.get("/audit/logs", summary="Search Forensic Audit Trail")
async def search_audit_logs(request: Request): return await placeholder(request)

# --- Section 16: Finance & Subscriptions (Treasurer Facing) ---
finance = APIRouter(tags=["16. Finance & Subscriptions"], prefix="/finance")

@finance.post("/checkout", response_model=KapuletuCheckoutOut, summary="Initiate Subscription Payment")
async def initiate_checkout(data: KapuletuCheckoutIn):
    return {
        "checkout_id": "CH-SUB-12345",
        "status": "initiated",
        "provider_response": {"message": "STK Push Sent / Payment Intent Created"}
    }

@finance.get("/status/{checkout_id}", summary="Check Payment Fulfillment Status")
async def get_payment_status(checkout_id: str):
    return {"status": "success", "confirmed_at": "2024-05-14T10:00:00Z", "plan": "Professional"}

@finance.get("/available-plans", summary="List Subscription Tiers")
async def list_plans():
    return [
        {"id": "basic", "name": "Basic", "price": 0, "limits": {"groups": 1}},
        {"id": "pro", "name": "Professional", "price": 1000, "limits": {"groups": 10}}
    ]

@finance.get("/my-subscription", summary="View Active Subscription & Usage")
async def my_subscription():
    return {
        "active_plan": "Professional",
        "expiry_date": "2024-06-14",
        "usage": {
            "groups": "3/10",
            "campaigns": "5/50"
        }
    }

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
app.include_router(admin)
app.include_router(finance)

# Serve static assets (Logo, Favicons, etc.)
import os

from fastapi.staticfiles import StaticFiles

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
    
