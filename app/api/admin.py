"""
Admin API endpoints for tenant and API key management.
All endpoints require X-Admin-Key header.
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field

from app.core.auth import (
    verify_admin_key,
    create_tenant,
    get_tenant,
    get_tenant_by_name,
    list_tenants,
    update_tenant_quotas,
    create_api_key,
    get_api_key,
    list_api_keys,
    rotate_api_key,
    revoke_api_key,
    get_usage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateTenantRequest(BaseModel):
    """Request to create a tenant."""
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class TenantResponse(BaseModel):
    """Tenant response."""
    tenant_id: str
    name: str
    created_at: str
    max_requests_per_day: int
    max_tool_calls_per_day: int
    max_bytes_fetched_per_day: int


class UpdateQuotasRequest(BaseModel):
    """Request to update tenant quotas."""
    max_requests_per_day: Optional[int] = Field(None, ge=0)
    max_tool_calls_per_day: Optional[int] = Field(None, ge=0)
    max_bytes_fetched_per_day: Optional[int] = Field(None, ge=0)


class CreateApiKeyRequest(BaseModel):
    """Request to create an API key."""
    label: Optional[str] = Field(None, max_length=100)


class ApiKeyResponse(BaseModel):
    """API key response (with masked key)."""
    api_key_id: str
    tenant_id: str
    key_prefix: str
    label: Optional[str]
    status: str
    created_at: str
    last_used_at: Optional[str]


class NewApiKeyResponse(BaseModel):
    """Response when creating/rotating API key - includes raw key once."""
    api_key: str  # Raw key - shown only once!
    api_key_id: str
    tenant_id: str
    key_prefix: str
    label: Optional[str]


class RotateApiKeyResponse(BaseModel):
    """Response when rotating API key."""
    api_key: str  # Raw key - shown only once!
    api_key_id: str
    rotated_from: str
    tenant_id: str
    key_prefix: str


class RevokeResponse(BaseModel):
    """Response when revoking API key."""
    status: str


class UsageRecord(BaseModel):
    """Daily usage record."""
    day: str
    requests_total: int
    agent_jobs_total: int
    tool_calls_total: int
    bytes_fetched_total: int
    per_tool: Optional[str]


class UsageResponse(BaseModel):
    """Usage response."""
    tenant_id: str
    days: int
    records: List[UsageRecord]
    totals: dict


# =============================================================================
# Admin Auth Dependency
# =============================================================================

def require_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")) -> None:
    """Verify admin key header."""
    if not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")


# =============================================================================
# Tenant Endpoints
# =============================================================================

@router.post("/tenants", response_model=TenantResponse)
async def create_tenant_endpoint(
    request: CreateTenantRequest,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Create a new tenant."""
    require_admin(x_admin_key)
    
    # Check if tenant already exists
    existing = get_tenant_by_name(request.name)
    if existing:
        raise HTTPException(status_code=409, detail="Tenant with this name already exists")
    
    tenant = create_tenant(request.name)
    
    return TenantResponse(
        tenant_id=tenant.id,
        name=tenant.name,
        created_at=tenant.created_at,
        max_requests_per_day=tenant.max_requests_per_day,
        max_tool_calls_per_day=tenant.max_tool_calls_per_day,
        max_bytes_fetched_per_day=tenant.max_bytes_fetched_per_day,
    )


@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants_endpoint(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """List all tenants."""
    require_admin(x_admin_key)
    
    tenants = list_tenants()
    
    return [
        TenantResponse(
            tenant_id=t.id,
            name=t.name,
            created_at=t.created_at,
            max_requests_per_day=t.max_requests_per_day,
            max_tool_calls_per_day=t.max_tool_calls_per_day,
            max_bytes_fetched_per_day=t.max_bytes_fetched_per_day,
        )
        for t in tenants
    ]


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant_endpoint(
    tenant_id: str,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Get a specific tenant."""
    require_admin(x_admin_key)
    
    tenant = get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return TenantResponse(
        tenant_id=tenant.id,
        name=tenant.name,
        created_at=tenant.created_at,
        max_requests_per_day=tenant.max_requests_per_day,
        max_tool_calls_per_day=tenant.max_tool_calls_per_day,
        max_bytes_fetched_per_day=tenant.max_bytes_fetched_per_day,
    )


@router.patch("/tenants/{tenant_id}/quotas", response_model=TenantResponse)
async def update_quotas_endpoint(
    tenant_id: str,
    request: UpdateQuotasRequest,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Update tenant quota limits."""
    require_admin(x_admin_key)
    
    tenant = update_tenant_quotas(
        tenant_id,
        max_requests_per_day=request.max_requests_per_day,
        max_tool_calls_per_day=request.max_tool_calls_per_day,
        max_bytes_fetched_per_day=request.max_bytes_fetched_per_day,
    )
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return TenantResponse(
        tenant_id=tenant.id,
        name=tenant.name,
        created_at=tenant.created_at,
        max_requests_per_day=tenant.max_requests_per_day,
        max_tool_calls_per_day=tenant.max_tool_calls_per_day,
        max_bytes_fetched_per_day=tenant.max_bytes_fetched_per_day,
    )


# =============================================================================
# API Key Endpoints
# =============================================================================

@router.post("/tenants/{tenant_id}/keys", response_model=NewApiKeyResponse)
async def create_key_endpoint(
    tenant_id: str,
    request: CreateApiKeyRequest,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """
    Create a new API key for a tenant.
    
    **IMPORTANT**: The `api_key` value is shown only once in this response.
    Store it securely - it cannot be retrieved again.
    """
    require_admin(x_admin_key)
    
    tenant = get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    raw_key, api_key = create_api_key(tenant_id, label=request.label)
    
    return NewApiKeyResponse(
        api_key=raw_key,
        api_key_id=api_key.id,
        tenant_id=tenant_id,
        key_prefix=api_key.key_prefix,
        label=api_key.label,
    )


@router.get("/tenants/{tenant_id}/keys", response_model=List[ApiKeyResponse])
async def list_keys_endpoint(
    tenant_id: str,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """List all API keys for a tenant (masked)."""
    require_admin(x_admin_key)
    
    tenant = get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    keys = list_api_keys(tenant_id)
    
    return [
        ApiKeyResponse(
            api_key_id=k.id,
            tenant_id=k.tenant_id,
            key_prefix=k.key_prefix,
            label=k.label,
            status=k.status,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@router.post("/keys/{api_key_id}/rotate", response_model=RotateApiKeyResponse)
async def rotate_key_endpoint(
    api_key_id: str,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """
    Rotate an API key: revokes the old key and creates a new one.
    
    **IMPORTANT**: The `api_key` value is shown only once in this response.
    Store it securely - it cannot be retrieved again.
    """
    require_admin(x_admin_key)
    
    old_key = get_api_key(api_key_id)
    if not old_key:
        raise HTTPException(status_code=404, detail="API key not found")
    
    try:
        new_raw_key, new_api_key, old_key_id = rotate_api_key(api_key_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return RotateApiKeyResponse(
        api_key=new_raw_key,
        api_key_id=new_api_key.id,
        rotated_from=old_key_id,
        tenant_id=new_api_key.tenant_id,
        key_prefix=new_api_key.key_prefix,
    )


@router.post("/keys/{api_key_id}/revoke", response_model=RevokeResponse)
async def revoke_key_endpoint(
    api_key_id: str,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Revoke an API key."""
    require_admin(x_admin_key)
    
    if not revoke_api_key(api_key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    
    return RevokeResponse(status="revoked")


# =============================================================================
# Usage Endpoints
# =============================================================================

@router.get("/tenants/{tenant_id}/usage", response_model=UsageResponse)
async def get_usage_endpoint(
    tenant_id: str,
    days: int = Query(default=7, ge=1, le=90),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Get usage statistics for a tenant."""
    require_admin(x_admin_key)
    
    tenant = get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    records = get_usage(tenant_id, days)
    
    # Calculate totals
    totals = {
        "requests_total": sum(r["requests_total"] for r in records),
        "agent_jobs_total": sum(r["agent_jobs_total"] for r in records),
        "tool_calls_total": sum(r["tool_calls_total"] for r in records),
        "bytes_fetched_total": sum(r["bytes_fetched_total"] for r in records),
    }
    
    return UsageResponse(
        tenant_id=tenant_id,
        days=days,
        records=[
            UsageRecord(
                day=r["day"],
                requests_total=r["requests_total"],
                agent_jobs_total=r["agent_jobs_total"],
                tool_calls_total=r["tool_calls_total"],
                bytes_fetched_total=r["bytes_fetched_total"],
                per_tool=r["per_tool"],
            )
            for r in records
        ],
        totals=totals,
    )
