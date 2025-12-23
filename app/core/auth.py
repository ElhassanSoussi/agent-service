"""
Multi-tenant authentication and API key management.

Key format: agk_live_<random32>
Storage: HMAC-SHA256 hash with server secret
"""
import hashlib
import hmac
import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.db.database import SessionLocal
from app.db.models import Tenant, ApiKey, UsageDaily

logger = logging.getLogger(__name__)

# Key hash secret - required in production
KEY_HASH_SECRET = os.getenv("AGENT_KEY_HASH_SECRET", "dev-secret-change-in-prod")


def get_admin_key() -> Optional[str]:
    """Get admin key at runtime (for testability)."""
    return os.getenv("AGENT_ADMIN_KEY")


def get_legacy_api_key() -> Optional[str]:
    """Get legacy API key at runtime (for testability)."""
    return os.getenv("AGENT_API_KEY")

# Key prefix for generated keys
KEY_PREFIX = "agk_live_"


@dataclass
class AuthContext:
    """Authentication context attached to requests."""
    tenant_id: str
    api_key_id: str
    tenant_name: str


def hash_api_key(raw_key: str) -> str:
    """
    Hash an API key using HMAC-SHA256 with server secret.
    Returns hex digest.
    """
    return hmac.new(
        KEY_HASH_SECRET.encode(),
        raw_key.encode(),
        hashlib.sha256
    ).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (raw_key, key_hash, key_prefix).
    The raw_key should only be shown once to the user.
    """
    # Generate 32 random bytes = 64 hex chars
    random_part = secrets.token_hex(24)  # 48 chars
    raw_key = f"{KEY_PREFIX}{random_part}"
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:16]  # "agk_live_" + first 7 chars of random
    
    return raw_key, key_hash, key_prefix


def authenticate_api_key(raw_key: str) -> Optional[AuthContext]:
    """
    Authenticate an API key and return the auth context.
    Returns None if authentication fails.
    """
    if not raw_key:
        return None
    
    # Check legacy single API key first (for backwards compatibility)
    legacy_key = get_legacy_api_key()
    if legacy_key and constant_time_compare(raw_key, legacy_key):
        # Return a special "legacy" context
        # This allows existing API keys to continue working
        return AuthContext(
            tenant_id="legacy",
            api_key_id="legacy",
            tenant_name="legacy"
        )
    
    # Hash the key and look it up
    key_hash = hash_api_key(raw_key)
    
    db = SessionLocal()
    try:
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == key_hash,
            ApiKey.status == "active"
        ).first()
        
        if not api_key:
            return None
        
        # Update last_used_at
        api_key.last_used_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        
        # Get tenant
        tenant = db.query(Tenant).filter(Tenant.id == api_key.tenant_id).first()
        if not tenant:
            return None
        
        return AuthContext(
            tenant_id=tenant.id,
            api_key_id=api_key.id,
            tenant_name=tenant.name
        )
    finally:
        db.close()


def verify_admin_key(admin_key: str) -> bool:
    """Verify the admin key."""
    configured_key = get_admin_key()
    if not configured_key:
        logger.warning("AGENT_ADMIN_KEY not configured - admin endpoints disabled")
        return False
    return constant_time_compare(admin_key, configured_key)


# =============================================================================
# Tenant Management
# =============================================================================

def create_tenant(name: str) -> Tenant:
    """Create a new tenant."""
    db = SessionLocal()
    try:
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=name,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        
        logger.info(f"tenant_created tenant_id={tenant.id} name={name}")
        return tenant
    finally:
        db.close()


def get_tenant(tenant_id: str) -> Optional[Tenant]:
    """Get a tenant by ID."""
    db = SessionLocal()
    try:
        return db.query(Tenant).filter(Tenant.id == tenant_id).first()
    finally:
        db.close()


def get_tenant_by_name(name: str) -> Optional[Tenant]:
    """Get a tenant by name."""
    db = SessionLocal()
    try:
        return db.query(Tenant).filter(Tenant.name == name).first()
    finally:
        db.close()


def list_tenants() -> list[Tenant]:
    """List all tenants."""
    db = SessionLocal()
    try:
        tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
        for t in tenants:
            db.expunge(t)
        return tenants
    finally:
        db.close()


def update_tenant_quotas(
    tenant_id: str,
    max_requests_per_day: Optional[int] = None,
    max_tool_calls_per_day: Optional[int] = None,
    max_bytes_fetched_per_day: Optional[int] = None
) -> Optional[Tenant]:
    """Update tenant quota limits."""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return None
        
        if max_requests_per_day is not None:
            tenant.max_requests_per_day = max_requests_per_day
        if max_tool_calls_per_day is not None:
            tenant.max_tool_calls_per_day = max_tool_calls_per_day
        if max_bytes_fetched_per_day is not None:
            tenant.max_bytes_fetched_per_day = max_bytes_fetched_per_day
        
        db.commit()
        db.refresh(tenant)
        return tenant
    finally:
        db.close()


# =============================================================================
# API Key Management
# =============================================================================

def create_api_key(tenant_id: str, label: Optional[str] = None) -> tuple[str, ApiKey]:
    """
    Create a new API key for a tenant.
    Returns (raw_key, api_key_model).
    The raw_key should only be shown once.
    """
    raw_key, key_hash, key_prefix = generate_api_key()
    
    db = SessionLocal()
    try:
        api_key = ApiKey(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label=label,
            status="active",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        
        logger.info(f"api_key_created key_id={api_key.id} tenant_id={tenant_id}")
        return raw_key, api_key
    finally:
        db.close()


def get_api_key(api_key_id: str) -> Optional[ApiKey]:
    """Get an API key by ID."""
    db = SessionLocal()
    try:
        return db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
    finally:
        db.close()


def list_api_keys(tenant_id: str) -> list[ApiKey]:
    """List all API keys for a tenant."""
    db = SessionLocal()
    try:
        keys = db.query(ApiKey).filter(
            ApiKey.tenant_id == tenant_id
        ).order_by(ApiKey.created_at.desc()).all()
        for k in keys:
            db.expunge(k)
        return keys
    finally:
        db.close()


def rotate_api_key(api_key_id: str) -> tuple[str, ApiKey, str]:
    """
    Rotate an API key: revoke old key and create new one under same tenant.
    Returns (new_raw_key, new_api_key, old_key_id).
    """
    db = SessionLocal()
    try:
        old_key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
        if not old_key:
            raise ValueError("API key not found")
        
        if old_key.status == "revoked":
            raise ValueError("Cannot rotate revoked key")
        
        tenant_id = old_key.tenant_id
        old_label = old_key.label
        
        # Revoke old key
        old_key.status = "revoked"
        old_key.revoked_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        
        logger.info(f"api_key_revoked key_id={api_key_id} reason=rotation")
    finally:
        db.close()
    
    # Create new key
    new_raw_key, new_api_key = create_api_key(tenant_id, label=old_label)
    
    return new_raw_key, new_api_key, api_key_id


def revoke_api_key(api_key_id: str) -> bool:
    """Revoke an API key."""
    db = SessionLocal()
    try:
        api_key = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
        if not api_key:
            return False
        
        if api_key.status == "revoked":
            return True  # Already revoked
        
        api_key.status = "revoked"
        api_key.revoked_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        
        logger.info(f"api_key_revoked key_id={api_key_id}")
        return True
    finally:
        db.close()


# =============================================================================
# Usage Tracking
# =============================================================================

def get_today() -> str:
    """Get today's date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_or_create_daily_usage(tenant_id: str, day: Optional[str] = None) -> UsageDaily:
    """Get or create daily usage record for a tenant."""
    if day is None:
        day = get_today()
    
    db = SessionLocal()
    try:
        usage = db.query(UsageDaily).filter(
            UsageDaily.tenant_id == tenant_id,
            UsageDaily.day == day
        ).first()
        
        if not usage:
            usage = UsageDaily(
                tenant_id=tenant_id,
                day=day,
                requests_total=0,
                agent_jobs_total=0,
                tool_calls_total=0,
                bytes_fetched_total=0,
                per_tool_json="{}"
            )
            db.add(usage)
            db.commit()
            db.refresh(usage)
        
        return usage
    finally:
        db.close()


def increment_request_count(tenant_id: str) -> int:
    """Increment request count for today. Returns new total."""
    if tenant_id == "legacy":
        return 0  # Don't track legacy tenant
    
    db = SessionLocal()
    try:
        day = get_today()
        usage = db.query(UsageDaily).filter(
            UsageDaily.tenant_id == tenant_id,
            UsageDaily.day == day
        ).first()
        
        if not usage:
            usage = UsageDaily(
                tenant_id=tenant_id,
                day=day,
                requests_total=1,
                agent_jobs_total=0,
                tool_calls_total=0,
                bytes_fetched_total=0,
                per_tool_json="{}"
            )
            db.add(usage)
        else:
            usage.requests_total += 1
        
        db.commit()
        return usage.requests_total
    finally:
        db.close()


def increment_job_count(tenant_id: str) -> int:
    """Increment agent job count for today. Returns new total."""
    if tenant_id == "legacy":
        return 0
    
    db = SessionLocal()
    try:
        day = get_today()
        usage = db.query(UsageDaily).filter(
            UsageDaily.tenant_id == tenant_id,
            UsageDaily.day == day
        ).first()
        
        if not usage:
            usage = UsageDaily(
                tenant_id=tenant_id,
                day=day,
                requests_total=0,
                agent_jobs_total=1,
                tool_calls_total=0,
                bytes_fetched_total=0,
                per_tool_json="{}"
            )
            db.add(usage)
        else:
            usage.agent_jobs_total += 1
        
        db.commit()
        return usage.agent_jobs_total
    finally:
        db.close()


def increment_tool_call(tenant_id: str, tool_name: str, bytes_fetched: int = 0) -> tuple[int, int]:
    """
    Increment tool call count for today.
    Returns (tool_calls_total, bytes_fetched_total).
    """
    if tenant_id == "legacy":
        return 0, 0
    
    import json
    
    db = SessionLocal()
    try:
        day = get_today()
        usage = db.query(UsageDaily).filter(
            UsageDaily.tenant_id == tenant_id,
            UsageDaily.day == day
        ).first()
        
        if not usage:
            per_tool = {tool_name: 1}
            usage = UsageDaily(
                tenant_id=tenant_id,
                day=day,
                requests_total=0,
                agent_jobs_total=0,
                tool_calls_total=1,
                bytes_fetched_total=bytes_fetched,
                per_tool_json=json.dumps(per_tool)
            )
            db.add(usage)
        else:
            usage.tool_calls_total += 1
            usage.bytes_fetched_total += bytes_fetched
            
            # Update per-tool counts
            try:
                per_tool = json.loads(usage.per_tool_json or "{}")
            except json.JSONDecodeError:
                per_tool = {}
            
            per_tool[tool_name] = per_tool.get(tool_name, 0) + 1
            usage.per_tool_json = json.dumps(per_tool)
        
        db.commit()
        return usage.tool_calls_total, usage.bytes_fetched_total
    finally:
        db.close()


def get_usage(tenant_id: str, days: int = 7) -> list[dict]:
    """Get usage for a tenant for the last N days."""
    from datetime import timedelta
    
    db = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        start_date = (today - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        
        records = db.query(UsageDaily).filter(
            UsageDaily.tenant_id == tenant_id,
            UsageDaily.day >= start_date
        ).order_by(UsageDaily.day.desc()).all()
        
        return [
            {
                "day": r.day,
                "requests_total": r.requests_total,
                "agent_jobs_total": r.agent_jobs_total,
                "tool_calls_total": r.tool_calls_total,
                "bytes_fetched_total": r.bytes_fetched_total,
                "per_tool": r.per_tool_json,
            }
            for r in records
        ]
    finally:
        db.close()


# =============================================================================
# Quota Checking
# =============================================================================

def check_request_quota(tenant_id: str) -> tuple[bool, Optional[str]]:
    """
    Check if tenant has remaining request quota.
    Returns (allowed, error_message).
    """
    if tenant_id == "legacy":
        return True, None
    
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return False, "Tenant not found"
        
        day = get_today()
        usage = db.query(UsageDaily).filter(
            UsageDaily.tenant_id == tenant_id,
            UsageDaily.day == day
        ).first()
        
        current = usage.requests_total if usage else 0
        
        if current >= tenant.max_requests_per_day:
            return False, f"Request quota exceeded ({current}/{tenant.max_requests_per_day} per day)"
        
        return True, None
    finally:
        db.close()


def check_tool_quota(tenant_id: str) -> tuple[bool, Optional[str]]:
    """
    Check if tenant has remaining tool call quota.
    Returns (allowed, error_message).
    """
    if tenant_id == "legacy":
        return True, None
    
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return False, "Tenant not found"
        
        day = get_today()
        usage = db.query(UsageDaily).filter(
            UsageDaily.tenant_id == tenant_id,
            UsageDaily.day == day
        ).first()
        
        current_calls = usage.tool_calls_total if usage else 0
        current_bytes = usage.bytes_fetched_total if usage else 0
        
        if current_calls >= tenant.max_tool_calls_per_day:
            return False, f"Tool call quota exceeded ({current_calls}/{tenant.max_tool_calls_per_day} per day)"
        
        if current_bytes >= tenant.max_bytes_fetched_per_day:
            return False, f"Bytes fetched quota exceeded ({current_bytes}/{tenant.max_bytes_fetched_per_day} per day)"
        
        return True, None
    finally:
        db.close()
