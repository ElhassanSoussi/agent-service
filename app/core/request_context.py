"""
Request context for tracking request_id across async calls.
"""
import uuid
from contextvars import ContextVar

# Context variable for request ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID."""
    return request_id_var.get()


def set_request_id(request_id: str | None = None) -> str:
    """Set the request ID (generates new one if not provided)."""
    rid = request_id or str(uuid.uuid4())
    request_id_var.set(rid)
    return rid
