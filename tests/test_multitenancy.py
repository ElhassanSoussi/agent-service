"""
Tests for Phase 9: Multi-tenancy support.
Tests tenant management, API key management, usage tracking, and quota enforcement.
"""
import os
import pytest
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Set test environment variables BEFORE any app imports
# Use direct assignment to override any existing values
os.environ["AGENT_API_KEY"] = "test-api-key"
os.environ["AGENT_ADMIN_KEY"] = "test-admin-key"
os.environ["AGENT_KEY_HASH_SECRET"] = "test-hash-secret"

from main import app
from app.core.auth import (
    hash_api_key,
    generate_api_key,
    constant_time_compare,
    create_tenant,
    get_tenant,
    list_tenants,
    update_tenant_quotas,
    create_api_key,
    list_api_keys,
    rotate_api_key,
    revoke_api_key,
    authenticate_api_key,
    increment_request_count,
    increment_job_count,
    increment_tool_call,
    check_request_quota,
    check_tool_quota,
    get_usage,
    AuthContext,
)
from app.db.database import SessionLocal, init_db, run_migrations
from app.db.models import Tenant, ApiKey, UsageDaily, Job as JobModel

# Initialize test database and run migrations
init_db()


def unique_name(prefix: str) -> str:
    """Generate a unique name for test entities."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Admin headers for admin endpoints."""
    return {"X-Admin-Key": "test-admin-key"}


@pytest.fixture
def api_headers():
    """API headers for regular endpoints using legacy key."""
    return {"X-API-Key": "test-api-key"}


@pytest.fixture
def cleanup_db():
    """Clean up test data after tests."""
    yield
    db = SessionLocal()
    try:
        # Clean up test data - use try/except in case columns don't exist
        try:
            db.query(UsageDaily).filter(UsageDaily.tenant_id.like("test-%")).delete(synchronize_session=False)
        except Exception:
            pass
        try:
            db.query(ApiKey).filter(ApiKey.tenant_id.like("test-%")).delete(synchronize_session=False)
        except Exception:
            pass
        # Don't try to filter jobs by tenant_id since it may not exist
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# =============================================================================
# Key Generation and Hashing Tests
# =============================================================================

class TestKeyGeneration:
    """Tests for API key generation and hashing."""
    
    def test_hash_api_key_consistent(self):
        """Same key always produces same hash."""
        key = "agk_live_abc123"
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)
        assert hash1 == hash2
    
    def test_hash_api_key_different_keys(self):
        """Different keys produce different hashes."""
        hash1 = hash_api_key("agk_live_key1")
        hash2 = hash_api_key("agk_live_key2")
        assert hash1 != hash2
    
    def test_generate_api_key_format(self):
        """Generated keys have correct format."""
        raw_key, key_hash, key_prefix = generate_api_key()
        
        assert raw_key.startswith("agk_live_")
        assert len(raw_key) == 57  # "agk_live_" (9) + 48 random chars
        assert len(key_hash) == 64  # SHA256 hex digest
        assert key_prefix == raw_key[:16]
    
    def test_generate_api_key_unique(self):
        """Each generated key is unique."""
        keys = [generate_api_key()[0] for _ in range(10)]
        assert len(set(keys)) == 10
    
    def test_constant_time_compare_equal(self):
        """Constant time compare returns True for equal strings."""
        assert constant_time_compare("secret123", "secret123")
    
    def test_constant_time_compare_not_equal(self):
        """Constant time compare returns False for different strings."""
        assert not constant_time_compare("secret123", "secret456")


# =============================================================================
# Tenant Management Tests
# =============================================================================

class TestTenantManagement:
    """Tests for tenant CRUD operations."""
    
    def test_create_tenant(self, cleanup_db):
        """Can create a new tenant."""
        name = unique_name("TestTenant")
        tenant = create_tenant(name)
        
        assert tenant.id is not None
        assert tenant.name == name
        assert tenant.max_requests_per_day == 500
        assert tenant.max_tool_calls_per_day == 200
        assert tenant.max_bytes_fetched_per_day == 5000000
    
    def test_get_tenant(self, cleanup_db):
        """Can retrieve tenant by ID."""
        name = unique_name("TestTenant")
        created = create_tenant(name)
        retrieved = get_tenant(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == name
    
    def test_get_tenant_not_found(self):
        """Returns None for non-existent tenant."""
        result = get_tenant("non-existent-id")
        assert result is None
    
    def test_list_tenants(self, cleanup_db):
        """Can list all tenants."""
        name1 = unique_name("TestTenantList")
        name2 = unique_name("TestTenantList")
        create_tenant(name1)
        create_tenant(name2)
        
        tenants = list_tenants()
        names = [t.name for t in tenants]
        
        assert name1 in names
        assert name2 in names
    
    def test_update_tenant_quotas(self, cleanup_db):
        """Can update tenant quota limits."""
        name = unique_name("TestTenantQuota")
        tenant = create_tenant(name)
        
        updated = update_tenant_quotas(
            tenant.id,
            max_requests_per_day=1000,
            max_tool_calls_per_day=500,
            max_bytes_fetched_per_day=10000000
        )
        
        assert updated.max_requests_per_day == 1000
        assert updated.max_tool_calls_per_day == 500
        assert updated.max_bytes_fetched_per_day == 10000000


# =============================================================================
# API Key Management Tests
# =============================================================================

class TestApiKeyManagement:
    """Tests for API key CRUD operations."""
    
    def test_create_api_key(self, cleanup_db):
        """Can create API key for tenant."""
        tenant = create_tenant(unique_name("TestKeyTenant"))
        raw_key, api_key = create_api_key(tenant.id, label="test-key")
        
        assert raw_key.startswith("agk_live_")
        assert api_key.tenant_id == tenant.id
        assert api_key.label == "test-key"
        assert api_key.status == "active"
    
    def test_list_api_keys(self, cleanup_db):
        """Can list API keys for tenant."""
        tenant = create_tenant(unique_name("TestKeyTenant"))
        create_api_key(tenant.id, label="key1")
        create_api_key(tenant.id, label="key2")
        
        keys = list_api_keys(tenant.id)
        labels = [k.label for k in keys]
        
        assert "key1" in labels
        assert "key2" in labels
    
    def test_rotate_api_key(self, cleanup_db):
        """Can rotate an API key."""
        tenant = create_tenant(unique_name("TestKeyTenant"))
        _, old_key = create_api_key(tenant.id, label="to-rotate")
        
        new_raw_key, new_api_key, old_key_id = rotate_api_key(old_key.id)
        
        assert new_raw_key.startswith("agk_live_")
        assert new_api_key.id != old_key.id
        assert old_key_id == old_key.id
        
        # Old key should be revoked
        from app.core.auth import get_api_key
        old = get_api_key(old_key.id)
        assert old.status == "revoked"
    
    def test_revoke_api_key(self, cleanup_db):
        """Can revoke an API key."""
        tenant = create_tenant(unique_name("TestKeyTenant"))
        _, api_key = create_api_key(tenant.id, label="to-revoke")
        
        result = revoke_api_key(api_key.id)
        
        assert result is True
        
        from app.core.auth import get_api_key
        revoked = get_api_key(api_key.id)
        assert revoked.status == "revoked"


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAuthentication:
    """Tests for API key authentication."""
    
    def test_authenticate_valid_key(self, cleanup_db):
        """Valid API key returns auth context."""
        name = unique_name("TestAuthTenant")
        tenant = create_tenant(name)
        raw_key, _ = create_api_key(tenant.id)
        
        context = authenticate_api_key(raw_key)
        
        assert context is not None
        assert context.tenant_id == tenant.id
        assert context.tenant_name == name
    
    def test_authenticate_invalid_key(self):
        """Invalid API key returns None."""
        context = authenticate_api_key("invalid-key")
        assert context is None
    
    def test_authenticate_revoked_key(self, cleanup_db):
        """Revoked API key returns None."""
        tenant = create_tenant(unique_name("TestAuthTenant"))
        raw_key, api_key = create_api_key(tenant.id)
        revoke_api_key(api_key.id)
        
        context = authenticate_api_key(raw_key)
        assert context is None
    
    def test_authenticate_legacy_key(self):
        """Legacy AGENT_API_KEY still works."""
        # The env var is set at the top of the file
        # Just verify the legacy key works
        context = authenticate_api_key("test-api-key")
        
        assert context is not None
        assert context.tenant_id == "legacy"


# =============================================================================
# Usage Tracking Tests
# =============================================================================

class TestUsageTracking:
    """Tests for usage tracking."""
    
    def test_increment_request_count(self, cleanup_db):
        """Can increment request count."""
        tenant = create_tenant(unique_name("TestUsageTenant"))
        
        count1 = increment_request_count(tenant.id)
        count2 = increment_request_count(tenant.id)
        
        assert count1 == 1
        assert count2 == 2
    
    def test_increment_job_count(self, cleanup_db):
        """Can increment job count."""
        tenant = create_tenant(unique_name("TestUsageTenant"))
        
        count1 = increment_job_count(tenant.id)
        count2 = increment_job_count(tenant.id)
        
        assert count1 == 1
        assert count2 == 2
    
    def test_increment_tool_call(self, cleanup_db):
        """Can increment tool call count with bytes."""
        tenant = create_tenant(unique_name("TestUsageTenant"))
        
        calls1, bytes1 = increment_tool_call(tenant.id, "web_page_text", 1000)
        calls2, bytes2 = increment_tool_call(tenant.id, "web_search", 500)
        
        assert calls1 == 1
        assert bytes1 == 1000
        assert calls2 == 2
        assert bytes2 == 1500
    
    def test_get_usage(self, cleanup_db):
        """Can retrieve usage records."""
        tenant = create_tenant(unique_name("TestUsageTenant"))
        
        increment_request_count(tenant.id)
        increment_tool_call(tenant.id, "echo", 100)
        
        records = get_usage(tenant.id, days=7)
        
        assert len(records) > 0
        today = records[0]
        assert today["requests_total"] >= 1
        assert today["tool_calls_total"] >= 1
    
    def test_legacy_tenant_not_tracked(self):
        """Legacy tenant usage is not tracked."""
        count = increment_request_count("legacy")
        assert count == 0


# =============================================================================
# Quota Enforcement Tests
# =============================================================================

class TestQuotaEnforcement:
    """Tests for quota checking."""
    
    def test_check_request_quota_allowed(self, cleanup_db):
        """Request allowed when under quota."""
        tenant = create_tenant(unique_name("TestQuotaTenant"))
        
        allowed, error = check_request_quota(tenant.id)
        
        assert allowed is True
        assert error is None
    
    def test_check_request_quota_exceeded(self, cleanup_db):
        """Request denied when quota exceeded."""
        tenant = create_tenant(unique_name("TestQuotaTenant"))
        update_tenant_quotas(tenant.id, max_requests_per_day=2)
        
        increment_request_count(tenant.id)
        increment_request_count(tenant.id)
        
        allowed, error = check_request_quota(tenant.id)
        
        assert allowed is False
        assert "quota exceeded" in error.lower()
    
    def test_check_tool_quota_allowed(self, cleanup_db):
        """Tool call allowed when under quota."""
        tenant = create_tenant(unique_name("TestQuotaTenant"))
        
        allowed, error = check_tool_quota(tenant.id)
        
        assert allowed is True
        assert error is None
    
    def test_check_tool_quota_exceeded(self, cleanup_db):
        """Tool call denied when quota exceeded."""
        tenant = create_tenant(unique_name("TestQuotaTenant"))
        update_tenant_quotas(tenant.id, max_tool_calls_per_day=2)
        
        increment_tool_call(tenant.id, "echo", 0)
        increment_tool_call(tenant.id, "echo", 0)
        
        allowed, error = check_tool_quota(tenant.id)
        
        assert allowed is False
        assert "quota exceeded" in error.lower()
    
    def test_check_bytes_quota_exceeded(self, cleanup_db):
        """Bytes quota enforcement."""
        tenant = create_tenant(unique_name("TestQuotaTenant"))
        update_tenant_quotas(tenant.id, max_bytes_fetched_per_day=1000)
        
        increment_tool_call(tenant.id, "web_page_text", 1000)
        
        allowed, error = check_tool_quota(tenant.id)
        
        assert allowed is False
        assert "bytes" in error.lower()
    
    def test_legacy_tenant_no_quota(self):
        """Legacy tenant has no quota limits."""
        allowed, error = check_request_quota("legacy")
        
        assert allowed is True
        assert error is None


# =============================================================================
# Admin API Tests
# =============================================================================

class TestAdminAPI:
    """Tests for admin API endpoints."""
    
    def test_create_tenant_endpoint(self, client, admin_headers, cleanup_db):
        """POST /admin/tenants creates tenant."""
        name = unique_name("TestAPITenant")
        response = client.post(
            "/admin/tenants",
            json={"name": name},
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == name
        assert data["tenant_id"] is not None
    
    def test_create_tenant_duplicate(self, client, admin_headers, cleanup_db):
        """POST /admin/tenants rejects duplicate name."""
        name = unique_name("TestDupTenant")
        client.post("/admin/tenants", json={"name": name}, headers=admin_headers)
        response = client.post(
            "/admin/tenants",
            json={"name": name},
            headers=admin_headers
        )
        
        assert response.status_code == 409
    
    def test_list_tenants_endpoint(self, client, admin_headers, cleanup_db):
        """GET /admin/tenants lists tenants."""
        client.post("/admin/tenants", json={"name": unique_name("TestListTenant")}, headers=admin_headers)
        
        response = client.get("/admin/tenants", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_tenant_endpoint(self, client, admin_headers, cleanup_db):
        """GET /admin/tenants/{id} returns tenant."""
        name = unique_name("TestGetTenant")
        create_response = client.post(
            "/admin/tenants",
            json={"name": name},
            headers=admin_headers
        )
        tenant_id = create_response.json()["tenant_id"]
        
        response = client.get(f"/admin/tenants/{tenant_id}", headers=admin_headers)
        
        assert response.status_code == 200
        assert response.json()["name"] == name
    
    def test_update_quotas_endpoint(self, client, admin_headers, cleanup_db):
        """PATCH /admin/tenants/{id}/quotas updates quotas."""
        create_response = client.post(
            "/admin/tenants",
            json={"name": unique_name("TestPatchTenant")},
            headers=admin_headers
        )
        tenant_id = create_response.json()["tenant_id"]
        
        response = client.patch(
            f"/admin/tenants/{tenant_id}/quotas",
            json={"max_requests_per_day": 1000},
            headers=admin_headers
        )
        
        assert response.status_code == 200
        assert response.json()["max_requests_per_day"] == 1000
    
    def test_create_api_key_endpoint(self, client, admin_headers, cleanup_db):
        """POST /admin/tenants/{id}/keys creates API key."""
        create_response = client.post(
            "/admin/tenants",
            json={"name": unique_name("TestKeyAPITenant")},
            headers=admin_headers
        )
        tenant_id = create_response.json()["tenant_id"]
        
        response = client.post(
            f"/admin/tenants/{tenant_id}/keys",
            json={"label": "test-key"},
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["api_key"].startswith("agk_live_")
        assert data["label"] == "test-key"
    
    def test_list_keys_endpoint(self, client, admin_headers, cleanup_db):
        """GET /admin/tenants/{id}/keys lists keys."""
        create_response = client.post(
            "/admin/tenants",
            json={"name": unique_name("TestListKeysTenant")},
            headers=admin_headers
        )
        tenant_id = create_response.json()["tenant_id"]
        
        client.post(f"/admin/tenants/{tenant_id}/keys", json={}, headers=admin_headers)
        
        response = client.get(f"/admin/tenants/{tenant_id}/keys", headers=admin_headers)
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_admin_requires_auth(self, client):
        """Admin endpoints require X-Admin-Key."""
        response = client.get("/admin/tenants")
        assert response.status_code == 422  # Missing header
        
        response = client.get("/admin/tenants", headers={"X-Admin-Key": "wrong"})
        assert response.status_code == 403


# =============================================================================
# Tenant Scoping Tests
# =============================================================================

class TestTenantScoping:
    """Tests for tenant-scoped job access."""
    
    def test_create_job_with_tenant(self, client, cleanup_db):
        """Job is created with tenant_id from API key."""
        # Create tenant and key
        tenant = create_tenant(unique_name("TestScopingTenant"))
        raw_key, _ = create_api_key(tenant.id)
        
        response = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "test"}},
            headers={"X-API-Key": raw_key}
        )
        
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        
        # Verify job has tenant_id
        from app.core.jobs import job_store
        job = job_store.get(job_id)
        assert job.tenant_id == tenant.id
    
    def test_cannot_access_other_tenant_job(self, client, cleanup_db):
        """Cannot access job from different tenant."""
        # Create two tenants
        tenant1 = create_tenant(unique_name("TestScopingTenant"))
        tenant2 = create_tenant(unique_name("TestScopingTenant"))
        key1, _ = create_api_key(tenant1.id)
        key2, _ = create_api_key(tenant2.id)
        
        # Create job as tenant1
        create_response = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "test"}},
            headers={"X-API-Key": key1}
        )
        job_id = create_response.json()["job_id"]
        
        # Try to access as tenant2
        response = client.get(
            f"/agent/status/{job_id}",
            headers={"X-API-Key": key2}
        )
        
        assert response.status_code == 404
    
    def test_can_access_own_job(self, client, cleanup_db):
        """Can access own tenant's job."""
        tenant = create_tenant(unique_name("TestScopingTenant"))
        raw_key, _ = create_api_key(tenant.id)
        
        # Create job
        create_response = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "test"}},
            headers={"X-API-Key": raw_key}
        )
        job_id = create_response.json()["job_id"]
        
        # Access own job
        response = client.get(
            f"/agent/status/{job_id}",
            headers={"X-API-Key": raw_key}
        )
        
        assert response.status_code == 200
    
    def test_list_jobs_shows_only_own_jobs(self, client, cleanup_db):
        """List jobs only shows tenant's own jobs."""
        tenant1 = create_tenant(unique_name("TestScopingTenant"))
        tenant2 = create_tenant(unique_name("TestScopingTenant"))
        key1, _ = create_api_key(tenant1.id)
        key2, _ = create_api_key(tenant2.id)
        
        # Create jobs for both tenants
        resp1 = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "tenant1"}},
            headers={"X-API-Key": key1}
        )
        job1_id = resp1.json()["job_id"]
        
        resp2 = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "tenant2"}},
            headers={"X-API-Key": key2}
        )
        job2_id = resp2.json()["job_id"]
        
        # List jobs as tenant1
        response = client.get("/agent/jobs", headers={"X-API-Key": key1})
        
        assert response.status_code == 200
        job_ids = [j["job_id"] for j in response.json()["items"]]
        
        # Should see tenant1's job
        assert job1_id in job_ids
        # Should NOT see tenant2's job
        assert job2_id not in job_ids
    
    def test_legacy_key_can_access_all_jobs(self, client, api_headers, cleanup_db):
        """Legacy API key can access all jobs (backwards compatibility)."""
        # The env var is set at the top of the file
        # Create a job with legacy key
        create_response = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "legacy"}},
            headers=api_headers
        )
        assert create_response.status_code == 202, f"Got {create_response.status_code}: {create_response.json()}"
        job_id = create_response.json()["job_id"]
        
        # Access with legacy key
        response = client.get(f"/agent/status/{job_id}", headers=api_headers)
        
        assert response.status_code == 200


# =============================================================================
# Quota Enforcement Integration Tests
# =============================================================================

class TestQuotaEnforcementIntegration:
    """Integration tests for quota enforcement."""
    
    def test_request_rejected_when_quota_exceeded(self, client, cleanup_db):
        """Requests rejected with 429 when quota exceeded."""
        tenant = create_tenant(unique_name("TestQuotaIntegration"))
        update_tenant_quotas(tenant.id, max_requests_per_day=1)
        raw_key, _ = create_api_key(tenant.id)
        
        # First request should succeed
        response1 = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "first"}},
            headers={"X-API-Key": raw_key}
        )
        assert response1.status_code == 202
        
        # Second request should be rejected
        response2 = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "second"}},
            headers={"X-API-Key": raw_key}
        )
        assert response2.status_code == 429


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
