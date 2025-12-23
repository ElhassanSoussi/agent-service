"""
Metrics endpoint for Prometheus scraping.
Auth required.
"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.metrics import metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics() -> str:
    """
    Export metrics in Prometheus text format.
    
    Requires authentication via X-API-Key header.
    """
    return metrics.to_prometheus()
