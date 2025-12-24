#!/usr/bin/env python3
"""
agent-service: FastAPI service with Agent API.
API key authentication required for all endpoints except /health.
"""
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi

from app.api.agent import router as agent_router
from app.api.metrics import router as metrics_router
from app.api.admin import router as admin_router
from app.api.builder import router as builder_router
from app.api.ui import router as ui_router
from app.api.llm import router as llm_router
from app.api.memory import router as memory_router
from app.api.feedback import router as feedback_router
from app.api.batches import router as batches_router  # Phase A1
from app.api.approvals_ui import router as approvals_ui_router  # Phase A1 UI
from app.api.developer import router as developer_router
from app.api.xone import router as xone_router  # Xone AI Agent API
from app.api.agent_controller import router as agent_controller_router  # Autonomous Agent Controller
from app.ui.command_center import router as command_center_router  # Phase A2
from app.core.security import APIKeyMiddleware
from app.core.request_logging import RequestLoggingMiddleware
from app.core.logging import setup_logging
from app.core.jobs import job_store
from app.core.artifact_store import artifact_store
from app.db.database import init_db

# Setup structured JSON logging
setup_logging()

# Initialize database on startup
init_db()

# Run cleanup at startup (safe, won't crash)
job_store.run_startup_cleanup()
artifact_store.run_startup_cleanup()

# =============================================================================
# Configuration from environment
# =============================================================================
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
VERSION = "1.0.0"

# Agent identity (Phase 21)
AGENT_NAME = os.environ.get("AGENT_NAME", "Xone by Elhassan Soussi")
AGENT_SYSTEM_PROMPT_DEFAULT = os.environ.get(
    "AGENT_SYSTEM_PROMPT_DEFAULT",
    "You are Xone, an AI assistant created by Elhassan Soussi. When asked about your name or who you are, always respond that your name is 'Xone by Elhassan Soussi'. Be concise, accurate, and helpful."
)


def get_base_url(request: Request | None = None) -> str:
    """
    Get the base URL for building absolute URLs.
    
    Priority:
    1. PUBLIC_BASE_URL environment variable (if set)
    2. Request host (if request provided)
    3. Fallback to localhost with configured port
    """
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    if request:
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
        if host:
            return f"{scheme}://{host}"
    return f"http://localhost:{PORT}"


# Create app
app = FastAPI(
    title="agent-service",
    description="Agent API with background job execution",
    version=VERSION,
)


def custom_openapi():
    """Custom OpenAPI schema with security schemes for Swagger UI."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "apiKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key authentication via X-API-Key header",
        },
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Bearer token authentication via Authorization header",
        },
    }
    
    # Apply security globally to all endpoints except public ones
    public_paths = {"/health", "/meta", "/docs", "/openapi.json", "/redoc", "/", "/llm/health"}
    for path, path_item in openapi_schema["paths"].items():
        if path not in public_paths:
            for method in path_item.values():
                if isinstance(method, dict):
                    method["security"] = [
                        {"apiKeyHeader": []},
                        {"bearerAuth": []},
                    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


class NoCacheStaticFiles(StaticFiles):
    """Static files with no-cache headers to avoid stale UI assets."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


@app.middleware("http")
async def no_cache_ui(request: Request, call_next):
    """Ensure UI and static assets are never cached in the browser."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/ui") or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Add request logging middleware (must be first to capture all requests)
app.add_middleware(RequestLoggingMiddleware)

# Add authentication middleware
app.add_middleware(APIKeyMiddleware)

# Include routes
app.include_router(agent_router)
app.include_router(metrics_router)
app.include_router(admin_router)
app.include_router(builder_router)
app.include_router(ui_router)
app.include_router(llm_router)
app.include_router(memory_router)
app.include_router(feedback_router)
app.include_router(batches_router)
app.include_router(approvals_ui_router)
app.include_router(developer_router)
app.include_router(xone_router)  # Xone AI Agent API
app.include_router(agent_controller_router)  # Autonomous Agent Controller
app.include_router(command_center_router)  # Phase A2: Command Center

# Mount static files for PWA (Phase A2)
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def root():
    """Root homepage."""
    base_url = PUBLIC_BASE_URL or f"http://localhost:{PORT}"
    return f"""
    <html>
      <head><title>Agent Service</title></head>
      <body style="font-family: Arial; padding: 24px;">
        <h1>✅ Agent Service is running</h1>
        <ul>
          <li><a href="/health">/health</a> - Health check</li>
          <li><a href="/meta">/meta</a> - Service metadata</li>
          <li><a href="/docs">/docs</a> - API Documentation</li>
          <li><a href="/ui">/ui</a> - Web UI</li>
        </ul>
        <p><strong>Base URL:</strong> <code>{base_url}</code></p>
      </body>
    </html>
    """


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/meta")
def meta(request: Request):
    """
    Service metadata endpoint.
    
    Returns configuration info useful for diagnostics and client setup.
    Includes agent identity and LLM provider info (Phase 21).
    """
    from app.llm.config import get_llm_config
    
    config = get_llm_config()
    
    # Determine LLM info
    llm_info = {
        "provider": config.provider or "not_configured",
        "model": config.model,
        "planner_mode": config.planner_mode,
    }
    
    # Add base_url for Ollama
    if config.provider in ("ollama", "local"):
        from app.llm.providers.ollama_client import get_ollama_base_url, get_ollama_model
        llm_info["base_url"] = config.base_url or get_ollama_base_url()
        llm_info["model"] = get_ollama_model(config)
    
    return {
        "agent_name": AGENT_NAME,
        "public_base_url": PUBLIC_BASE_URL or None,
        "computed_base_url": get_base_url(request),
        "listen_host": LISTEN_HOST,
        "port": PORT,
        "version": VERSION,
        "docs_url": f"{get_base_url(request)}/docs",
        "ui_url": f"{get_base_url(request)}/ui",
        "health_url": f"{get_base_url(request)}/health",
        "llm": llm_info,
        "features": {
            "memory": True,
            "feedback": True,
            "streaming": config.provider in ("ollama", "local"),
        },
    }
