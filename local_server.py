from __future__ import annotations
import json
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, FastAPI, Request, Response, Depends

# Ensure all logger.info() messages (like OTP codes) are printed to the console
logging.basicConfig(level=logging.INFO, format="%(levelname)s:\t  %(message)s")

from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from services.approval.handler import handler as approval_handler
from services.auth.router import router as auth

from services.groups.router import router as groups
from services.finance.ledger_router import router as ledger
from services.reporting.router import router as reporting

# Import Handlers
from services.ingestion.handler import handler as ingestion_handler
from services.members.handler import handler as members_handler

app = FastAPI(
    title="KapuLetu Treasury API — Full Specification",
    description="Local development bridge mapping every endpoint from the technical specification (v1).",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True}
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://app.kapuletu.co.ke",
        "https://dev.kapuletu.co.ke"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

class AuthLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/auth"):
            return await call_next(request)

        # Log Request
        body = await request.body()
        logging.info(f"========== INCOMING AUTH REQUEST ==========")
        logging.info(f"{request.method} {request.url.path}")
        if body:
            try:
                # Mask password if present
                payload = json.loads(body)
                if 'password' in payload:
                    payload['password'] = '***MASKED***'
                if 'new_password' in payload:
                    payload['new_password'] = '***MASKED***'
                if 'old_password' in payload:
                    payload['old_password'] = '***MASKED***'
                logging.info(f"Payload: {json.dumps(payload, indent=2)}")
            except:
                logging.info(f"Payload: {body}")
                
        # Re-inject body for the route handler
        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive

        # Process Response
        start_time = time.time()
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000

        # Log Response
        logging.info(f"---------- AUTH RESPONSE ----------")
        logging.info(f"Status: {response.status_code} ({process_time:.2f}ms)")
        
        # Consume response body to log it
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk
            
        if response_body:
            try:
                logging.info(f"Body: {json.dumps(json.loads(response_body), indent=2)}")
            except:
                logging.info(f"Body: {response_body}")
                
        logging.info(f"===========================================\n")
                
        # Reconstruct response to send to client
        return StarletteResponse(
            content=response_body, 
            status_code=response.status_code, 
            headers=dict(response.headers),
            media_type=response.media_type
        )

app.add_middleware(AuthLoggingMiddleware)


# --- Pydantic Schemas for Swagger UI ---

class TransactionIn(BaseModel):
    Body: str = Field(..., json_schema_extra={"example": "KES 1500 from Jane Doe for Welfare"})
    From: str = Field(..., json_schema_extra={"example": "+254700000000"})
    MessageSid: Optional[str] = Field(None, json_schema_extra={"example": "SM12345"})

# --- Group Schemas (Moved to services/groups/schemas.py) ---


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

class AdminUserCreateIn(BaseModel):
    first_name: str = Field(..., json_schema_extra={"example": "New"})
    last_name: str = Field(..., json_schema_extra={"example": "User"})
    email: str = Field(..., json_schema_extra={"example": "newuser@kapuletu.co.ke"})
    phone_number: str = Field(..., json_schema_extra={"example": "+254700000001"})
    role: str = Field("treasurer", json_schema_extra={"example": "treasurer"})
    password: str = Field(..., json_schema_extra={"example": "TempPassword123!"})

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


# 5. Transaction Ingestion
ingestion = APIRouter(tags=["5. Transaction Ingestion"])
@ingestion.post("/ingestion/webhook", summary="Webhook (Meta / External)")
async def ingestion_webhook_schema(payload: TransactionIn): return Response(status_code=200)
@app.post("/ingestion/webhook", include_in_schema=False)
async def ingestion_webhook_impl(request: Request): return await lambda_adapter(request, ingestion_handler)

@ingestion.get("/ingestion/webhook", summary="Meta Webhook Verification")
async def ingestion_webhook_verify_schema(request: Request): return Response(status_code=200)
@app.get("/ingestion/webhook", include_in_schema=False)
async def ingestion_webhook_verify_impl(request: Request): return await lambda_adapter(request, ingestion_handler)

from common.auth_dependencies import get_current_user, get_verified_user, get_admin_user, get_super_admin_user
from common.database import get_db
from sqlalchemy.orm import Session
from models.users import User
from services.auth.auth_service import get_password_hash
from services.admin.user_service import UserService
from common.enums import UserRole
from fastapi import HTTPException
from typing import Dict, Any

@app.get("/temp-elevate", summary="Temporary Elevation Script", include_in_schema=False)
async def temp_elevate(email: str, db: Session = Depends(get_db)):
    from models.users import User
    from common.enums import UserRole
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {"status": "error", "message": f"User {email} not found. Please register this email first."}
    
    user.role = UserRole.SUPER_ADMIN.value
    db.commit()
    return {"status": "success", "message": f"Elevated {email} to super_admin"}



from services.ingestion.manual_handler import handler as manual_handler
@ingestion.post("/transactions/manual", summary="Manual Entry")
async def manual_entry(request: Request, payload: ManualEntryIn, current_user: Dict[str, Any] = Depends(get_verified_user)): return await lambda_adapter(request, manual_handler)

# Removed parsing and review endpoints since they are now in native services/approval/router.py
# 8. Ledger
# Removed ledger endpoints since they are now in native services/finance/ledger_router.py

# 9. Members
members = APIRouter(tags=["9. Members Management"], dependencies=[Depends(get_verified_user)])
@members.get("/members/suggestions", summary="Auto-Suggest Members")
async def suggest_members(request: Request): return await lambda_adapter(request, members_handler)
@members.post("/members", summary="Create Member (Optional)")
async def create_member(request: Request, payload: MemberIn): return await lambda_adapter(request, members_handler)
@members.get("/groups/{group_id}/members", summary="Get Members")
async def group_members(request: Request, group_id: str): return await lambda_adapter(request, members_handler)

# 10. Reporting
# 11. Evidence
# Removed evidence endpoints since they are now in native services/evidence/router.py

# 12. Audit Logs
audit = APIRouter(prefix="/audit", tags=["12. Audit Logs"], dependencies=[Depends(get_verified_user)])
@audit.get("/logs", summary="Get Audit Logs")
async def get_logs(request: Request): return await placeholder(request)
@audit.get("/logs/{entity_type}/{entity_id}", summary="Get Logs by Entity")
async def get_logs_by_entity(entity_type: str, entity_id: str): return await placeholder(None)

# 13. Notifications
notifications = APIRouter(prefix="/notifications", tags=["13. Notifications"], dependencies=[Depends(get_verified_user)])
@notifications.post("/send", summary="Send Confirmation (After Approval)")
async def send_notification(request: Request, payload: NotificationIn): return await placeholder(request)

# 14. System Health
health = APIRouter(tags=["14. System Health & Admin"])
@health.get("/health", summary="Health Check")
async def health_check(): return {"status": "healthy"}

app.include_router(ledger)
app.include_router(reporting)
@health.get("/metrics", summary="Metrics")
async def metrics_check(): return {"metrics": "..."}

# 15. Admin Governance Suite
admin = APIRouter(prefix="/admin/v1", tags=["15. Admin Governance Suite"], dependencies=[Depends(get_admin_user)])

@admin.get("/overview", summary="Platform Overview Statistics", response_model=AdminOverviewOut)
async def admin_overview():
    return {
        "total_treasurers": 1250,
        "total_revenue_kes": 450000.0,
        "active_subscriptions": 890,
        "pending_tickets": 12,
        "ai_accuracy_rate": 0.94
    }

@admin.get("/users", summary="List All Users")
async def list_users(page: int = 1, limit: int = 50, status: str = None, db: Session = Depends(get_db)): 
    return UserService(db).list_treasurers(page=page, limit=limit, status=status)

@admin.post("/users", summary="Create User Manually")
async def create_user(payload: AdminUserCreateIn, db: Session = Depends(get_db)):
    if db.query(User).filter((User.email == payload.email) | (User.phone_number == payload.phone_number)).first():
        raise HTTPException(status_code=400, detail="User with this email or phone already exists")
    
    hashed_pw = get_password_hash(payload.password)
    new_user = User(
        email=payload.email,
        phone_number=payload.phone_number,
        first_name=payload.first_name,
        last_name=payload.last_name,
        hashed_password=hashed_pw,
        role=payload.role,
        email_verified=True,
        phone_number_verified=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully", "user_id": str(new_user.user_id)}

@admin.delete("/users/{user_id}", summary="Delete User")
async def delete_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    return {"message": f"User {user_id} deleted successfully"}

@admin.get("/users/{user_id}", summary="Get User Profile & Activity")
async def get_treasurer_profile(user_id: str, db: Session = Depends(get_db)): 
    details = UserService(db).get_treasurer_details(user_id)
    if not details: raise HTTPException(status_code=404, detail="User not found")
    return details

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
finance = APIRouter(tags=["16. Finance & Subscriptions"], prefix="/finance", dependencies=[Depends(get_verified_user)])

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
app.include_router(auth) # 2
app.include_router(groups) # 3
from services.campaigns.router import router as campaigns_router
app.include_router(campaigns_router) # 4
app.include_router(ingestion) # 5

from services.approval.router import router as approval
app.include_router(approval) # 6

from services.finance.ledger_router import router as ledger
app.include_router(ledger) # 8

app.include_router(members) # 9
app.include_router(reporting) # 10

from services.evidence.router import router as evidence
app.include_router(evidence) # 11
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
        
        <!-- Primary Meta Tags -->
        <title>KapuLetu Developer Portal</title>
        <meta name="title" content="KapuLetu Developer Portal">
        <meta name="description" content="Official API gateway for KapuLetu. Access the Treasury API core, documentation, and developer environment.">

        <!-- Open Graph / Facebook -->
        <meta property="og:type" content="website">
        <meta property="og:url" content="https://dev-api.kapuletu.co.ke/">
        <meta property="og:title" content="KapuLetu Developer Portal">
        <meta property="og:description" content="Official API gateway for KapuLetu. Access the Treasury API core, documentation, and developer environment.">
        <meta property="og:image" content="https://dev-api.kapuletu.co.ke/assets/logo.jpg">

        <!-- Twitter -->
        <meta property="twitter:card" content="summary_large_image">
        <meta property="twitter:url" content="https://dev-api.kapuletu.co.ke/">
        <meta property="twitter:title" content="KapuLetu Developer Portal">
        <meta property="twitter:description" content="Official API gateway for KapuLetu. Access the Treasury API core, documentation, and developer environment.">
        <meta property="twitter:image" content="https://dev-api.kapuletu.co.ke/assets/logo.jpg">

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
    uvicorn.run("local_server:app", host="0.0.0.0", port=8000, reload=True)
