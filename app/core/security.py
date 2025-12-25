"""
API key authentication middleware.
Supports both X-API-Key header and Authorization: Bearer token.
Multi-tenant aware with quota enforcement.

PUBLIC ROUTES (no auth required):
- /, /health, /meta - System endpoints
- /docs, /redoc, /openapi.json - API documentation
- /ui, /ui/* - Web UI (auth handled client-side)
- /admin/* - Uses separate X-Admin-Key

PROTECTED ROUTES (API key required):
- /agent/* - Agent job endpoints
- /builder/* - Builder endpoints
- /metrics/* - Metrics endpoints
"""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.auth import (
    authenticate_api_key,
    increment_request_count,
    check_request_quota,
    AuthContext,
)

logger = logging.getLogger(__name__)

# Routes that don't require authentication
# Note: UI routes are public but will require client-side API key for fetch calls
PUBLIC_PATHS = frozenset([
    "/",
    "/health",
    "/meta",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/llm/health",  # LLM health check is public for monitoring
])

# Route prefixes that don't require authentication
PUBLIC_PREFIXES = (
    "/ui",          # Web UI is public (auth handled in client JS)
    "/admin/",      # Admin uses separate X-Admin-Key
    "/static",      # Static files (PWA manifest, service worker, icons)
    "/api/debug/",  # Debug endpoints (DEV only)
)


def is_public_path(path: str) -> bool:
    """Check if a path is public (no auth required)."""
    # Exact match for public paths
    if path in PUBLIC_PATHS:
        return True
    
    # Prefix match for public prefixes
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    
    return False


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce API key on protected endpoints.
    
    Public routes (no key required):
    - /, /health, /meta, /docs, /redoc, /openapi.json
    - /ui, /ui/* (Web UI)
    - /admin/* (uses X-Admin-Key)
    
    Protected routes (key required):
    - /agent/*, /builder/*, /metrics/*
    
    API Key can be provided via:
    - X-API-Key header
    - Authorization: Bearer <token> header
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Allow public paths without authentication
        if is_public_path(path):
            return await call_next(request)

        # Check for API key in X-API-Key header first
        api_key = request.headers.get("X-API-Key")
        
        # If not found, check Authorization: Bearer header
        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]  # Extract token after "Bearer "
        
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key"}
            )
        
        # Authenticate
        auth_context = authenticate_api_key(api_key)
        if not auth_context:
            # Log failed auth attempt (don't include the key!)
            logger.warning(f"auth_failed path={path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"}
            )
        
        # Check request quota
        allowed, error = check_request_quota(auth_context.tenant_id)
        if not allowed:
            logger.warning(f"quota_exceeded tenant_id={auth_context.tenant_id} type=request")
            return JSONResponse(
                status_code=429,
                content={"detail": error, "error_code": "QUOTA_EXCEEDED"}
            )
        
        # Increment request counter
        increment_request_count(auth_context.tenant_id)
        
        # Attach auth context to request state for downstream use
        request.state.auth = auth_context
        request.state.tenant_id = auth_context.tenant_id
        request.state.api_key_id = auth_context.api_key_id
        
        return await call_next(request)


def get_auth_context(request: Request) -> AuthContext:
    """Get auth context from request. Call after middleware has run."""
    return getattr(request.state, "auth", None)


def get_tenant_id(request: Request) -> str:
    """Get tenant ID from request. Returns 'legacy' if not set."""
    return getattr(request.state, "tenant_id", "legacy")
