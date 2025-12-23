"""
Request logging middleware.
Logs structured request/response info with timing.
NEVER logs: API keys, request bodies, sensitive headers.
"""
import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import set_request_id, get_request_id
from app.core.metrics import metrics

logger = logging.getLogger("agent.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    - Generates request_id
    - Logs request/response with timing
    - Adds X-Request-Id header
    - Updates metrics
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate and set request ID
        request_id = set_request_id(str(uuid.uuid4()))
        
        # Get client IP (handle proxied requests)
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        
        # Record start time
        start_time = time.perf_counter()
        
        # Process request
        response: Response = await call_next(request)
        
        # Calculate duration
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Add request ID to response headers
        response.headers["X-Request-Id"] = request_id
        
        # Update metrics
        metrics.inc("requests_total")
        status_class = response.status_code // 100
        if status_class == 2:
            metrics.inc("requests_2xx")
        elif status_class == 4:
            metrics.inc("requests_4xx")
        elif status_class == 5:
            metrics.inc("requests_5xx")
        
        # Log request (structured)
        # Skip health checks to reduce noise
        if request.url.path != "/health":
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                }
            )
        
        return response
