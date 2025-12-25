"""Debug endpoints to diagnose auth issues."""
import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"])


class HeaderEchoResponse(BaseModel):
    """Response showing what headers were received."""
    x_api_key_present: bool
    x_api_key_length: int
    x_api_key_first_chars: str
    all_headers: dict


@router.get("/echo-headers", response_model=HeaderEchoResponse)
async def echo_headers(request: Request):
    """
    Echo back header information for debugging.
    Shows if X-API-Key header was received and its format.
    """
    api_key = request.headers.get("X-API-Key", "")

    return HeaderEchoResponse(
        x_api_key_present=bool(api_key),
        x_api_key_length=len(api_key),
        x_api_key_first_chars=api_key[:20] if api_key else "",
        all_headers={k: v[:50] + "..." if len(v) > 50 else v
                    for k, v in request.headers.items()}
    )
