from __future__ import annotations
import json
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, FastAPI, Request, Response, Depends

# Ensure all logger.info() messages (like OTP codes) are printed to the console
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:\t  %(message)s", datefmt='%Y-%m-%d %H:%M:%S %Z')

# Override logging time converter to EAT
from datetime import datetime, timezone
import zoneinfo
def custom_time(*args):
    return datetime.now(timezone.utc).astimezone(zoneinfo.ZoneInfo("Africa/Nairobi")).timetuple()
logging.Formatter.converter = custom_time

from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from services.approval.handler import handler as approval_handler
from services.auth.router import router as auth

from services.groups.router import router as groups
from services.finance.ledger_router import router as ledger
from services.finance.checkout_router import router as checkout_router
from services.reporting.router import router as reporting

# Import Handlers
from services.ingestion.handler import handler as ingestion_handler
from services.members.handler import handler as members_handler

openapi_tags = [
    {"name": "1. Authentication", "description": "User registration, login, and profile management."},
    {"name": "2. Workspace Overview", "description": "Treasurer's primary workspace dashboard and statistics."},
    {"name": "3. Members Management", "description": "Manage community members and directories."},
    {"name": "4. Groups Management", "description": "Manage contribution groups and communities."},
    {"name": "5. Campaigns Management", "description": "Manage fundraising and contribution campaigns."},
    {"name": "6. Finance & Subscriptions", "description": "Platform subscription plans and checkouts."},
    {"name": "7. Transaction Ingestion", "description": "Automated ingestion via external webhooks (e.g., MPesa)."},
    {"name": "8. Review & Approval Workflow", "description": "Review, approve, or reject pending transactions."},
    {"name": "9. Ledger (Immutable)", "description": "Core immutable financial ledger records."},
    {"name": "10. Reporting Service", "description": "Dashboards and detailed financial reports."},
    {"name": "11. Notifications", "description": "System alerts and external communication."},
    {"name": "12. Audit Logs", "description": "System-wide immutable audit trail."},
    {"name": "13. Enterprise Settings", "description": "Global and entity-level configuration settings."},
    {"name": "14. Admin Governance Suite", "description": "Platform-wide administrative controls."},
    {"name": "15. System Health & Admin", "description": "Service health checks and metrics."}
]

import orjson
from fastapi.responses import JSONResponse
import re

def fix_datetime_strings(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: fix_datetime_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fix_datetime_strings(v) for v in obj]
    elif isinstance(obj, str):
        # Match ISO8601 naive datetime strings (YYYY-MM-DDTHH:MM:SS or with microseconds)
        if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$', obj):
            return obj + 'Z'
    return obj

class CustomORJSONResponse(JSONResponse):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        # Fast API / Pydantic stringifies naive datetimes before they reach here.
        # We must recursively inject 'Z' (UTC offset) so the frontend browser
        # correctly localizes the timestamp (e.g. into EAT).
        fixed_content = fix_datetime_strings(content)
        return orjson.dumps(
            fixed_content,
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NAIVE_UTC,
        )

app = FastAPI(
    title="KapuLetu Treasury API — Full Specification",
    description="Local development bridge mapping every endpoint from the technical specification (v1).",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
    openapi_tags=openapi_tags,
    default_response_class=CustomORJSONResponse
)

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from services.auth.router import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

from fastapi.middleware.cors import CORSMiddleware
from common.config import get_config

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://app.kapuletu.co.ke",
        "https://dev.app.kapuletu.co.ke",
        get_config().FRONTEND_URL.rstrip('/')
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

from services.approval.schemas import ManualEntryIn, TransactionActionIn, TransactionEditIn

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
ingestion = APIRouter(tags=["7. Transaction Ingestion"])
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
async def manual_entry(request: Request, current_user: Dict[str, Any] = Depends(get_verified_user)): return await lambda_adapter(request, manual_handler)

# Removed parsing and review endpoints since they are now in native services/approval/router.py
# 8. Ledger
# Removed ledger endpoints since they are now in native services/finance/ledger_router.py

# 9. Members
# members = APIRouter(tags=["3. Members Management"], dependencies=[Depends(get_verified_user)])
# @members.get("/members/suggestions", summary="Auto-Suggest Members")
# async def suggest_members(request: Request): return await lambda_adapter(request, members_handler)
# @members.post("/members", summary="Create Member (Optional)")
# async def create_member(request: Request, payload: MemberIn): return await lambda_adapter(request, members_handler)
# @members.get("/groups/{group_id}/members", summary="Get Members")
# async def group_members(request: Request, group_id: str): return await lambda_adapter(request, members_handler)

# 10. Reporting
# 11. Evidence
# Removed evidence endpoints since they are now in native services/evidence/router.py

# 12. Audit Logs
# Removed audit placeholders since they are now in native services/audit/router.py

# 13. Notifications
# Removed notifications endpoints since they are now in native services/notifications/router.py

# 14. System Health
health = APIRouter(tags=["15. System Health & Admin"])
@health.get("/health", summary="Health Check")
async def health_check(): return {"status": "healthy"}


@health.get("/metrics", summary="Metrics")
async def metrics_check(): return {"metrics": "..."}



# --- Section 16: Finance & Subscriptions (Treasurer Facing) ---
# Removed placeholder finance endpoints since they are now in native services/finance/checkout_router.py

# --- Include All Routers ---
app.include_router(auth) # 2
app.include_router(groups) # 3
from services.campaigns.router import router as campaigns_router
from common.config import get_config
app.include_router(campaigns_router) # 4
app.include_router(ingestion) # 5

from services.approval.router import router as approval
app.include_router(approval) # 6

from services.finance.ledger_router import router as ledger
app.include_router(ledger) # 8

# app.include_router(members) # 9
app.include_router(reporting) # 10


from services.audit.router import router as audit_router
app.include_router(audit_router) # 12
from services.notifications.router import router as notifications_router
app.include_router(notifications_router) # 13
app.include_router(health)
from services.admin.router import router as admin_router
app.include_router(admin_router)

app.include_router(checkout_router, tags=["6. Finance & Subscriptions"], prefix="/finance", dependencies=[Depends(get_verified_user)])

from services.workspace.router import router as workspace_router
app.include_router(workspace_router, dependencies=[Depends(get_verified_user)])

from services.settings.router import router as settings_router
app.include_router(settings_router, tags=["13. Enterprise Settings"], prefix="", dependencies=[Depends(get_verified_user)])

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
