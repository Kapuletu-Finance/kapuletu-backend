from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from common.database import SessionLocal
from common.system_config_service import get_system_config
from common.auth_dependencies import get_current_user
import logging

logger = logging.getLogger(__name__)

class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # We only want to block non-admin APIs
        path = request.url.path
        
        # Always allow docs, openapi, auth routes, health checks, and webhooks to function
        if (
            path.startswith("/docs") or 
            path.startswith("/openapi.json") or 
            path.startswith("/auth") or 
            path.startswith("/ingestion/webhook") or
            path.startswith("/health") or
            path.startswith("/metrics")
        ):
            return await call_next(request)
            
        # Admin routes should always bypass maintenance mode so admins can turn it off
        if path.startswith("/admin"):
            return await call_next(request)

        # Check maintenance mode via DB
        db = SessionLocal()
        try:
            maintenance_mode = get_system_config(db, "maintenance_mode", default=False)
            maintenance_modules = get_system_config(db, "maintenance_modules", default={"web_app": True, "whatsapp_bot": False, "public_api": True})
            maintenance_message = get_system_config(db, "maintenance_message", default="Kapuletu platform is currently undergoing scheduled maintenance. Please try again later.")
        finally:
            db.close()

        if maintenance_mode:
            # If we're here, it's a non-admin attempting to access a route during maintenance.
            # If web_app is blocked, we block the standard API routes.
            if maintenance_modules.get("web_app", True):
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "detail": maintenance_message,
                        "error_code": "MAINTENANCE_MODE_ACTIVE"
                    }
                )

        return await call_next(request)

import time

# Simple in-memory stats to aggregate metrics before DB insertion
class PerformanceMetrics:
    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.total_response_time = 0.0

    def record(self, duration: float, is_error: bool):
        self.request_count += 1
        self.total_response_time += duration
        if is_error:
            self.error_count += 1

    def flush(self):
        reqs = self.request_count
        errs = self.error_count
        avg_time = (self.total_response_time / reqs) if reqs > 0 else 0.0
        
        # Reset
        self.request_count = 0
        self.error_count = 0
        self.total_response_time = 0.0
        
        return reqs, errs, avg_time

performance_stats = PerformanceMetrics()

import threading
import psutil
from common.database import SessionLocal

def _flush_metrics_loop():
    # Delay import to avoid circular dependencies if any
    from models.system_metric import SystemMetric
    import datetime
    
    # Initialize psutil CPU percent
    psutil.cpu_percent(interval=None)
    
    while True:
        time.sleep(60)
        reqs, errs, avg_time = performance_stats.flush()
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        
        db = SessionLocal()
        try:
            from models.users import User
            
            # Calculate active sessions (users active in the last 15 minutes)
            now = datetime.datetime.utcnow()
            active_threshold = now - datetime.timedelta(minutes=15)
            active_sessions = db.query(User).filter(User.last_active_at >= active_threshold).count()
            
            metric = SystemMetric(
                cpu_percent=cpu,
                memory_percent=mem,
                request_count=reqs,
                error_count=errs,
                avg_response_time_ms=avg_time,
                active_sessions_count=active_sessions
            )
            db.add(metric)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to flush system metrics: {e}")
        finally:
            db.close()

# Start background thread
threading.Thread(target=_flush_metrics_loop, daemon=True).start()

class PerformanceTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        try:
            response = await call_next(request)
            duration = (time.time() - start_time) * 1000  # ms
            is_error = response.status_code >= 400
            performance_stats.record(duration, is_error)
            return response
        except Exception:
            duration = (time.time() - start_time) * 1000
            performance_stats.record(duration, True)
            raise
