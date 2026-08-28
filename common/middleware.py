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
        
        # Always allow docs, openapi, and auth routes to function
        if path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/auth/login") or path.startswith("/auth/refresh"):
            return await call_next(request)
            
        # Admin routes should always bypass maintenance mode so admins can turn it off
        if path.startswith("/admin"):
            return await call_next(request)

        # Check maintenance mode via DB
        db = SessionLocal()
        try:
            maintenance_mode = get_system_config(db, "maintenance_mode", default=False)
        finally:
            db.close()

        if maintenance_mode:
            # If we're here, it's a non-admin attempting to access a route during maintenance.
            # We return 503 Service Unavailable with JSON
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Kapuletu platform is currently undergoing scheduled maintenance. Please try again later."}
            )

        return await call_next(request)
