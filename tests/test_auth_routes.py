"""
Tests for authentication and route protection.

Verifies:
- Public routes work without API key
- Protected routes require API key
- API key authentication works correctly
"""
import pytest
from fastapi.testclient import TestClient


class TestPublicRoutes:
    """Test that public routes work without authentication."""

    def test_health_no_auth(self, client: TestClient):
        """Health endpoint should work without API key."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_meta_no_auth(self, client: TestClient):
        """Meta endpoint should work without API key."""
        response = client.get("/meta")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "port" in data

    def test_root_no_auth(self, client: TestClient):
        """Root endpoint should work without API key."""
        response = client.get("/")
        assert response.status_code == 200

    def test_docs_no_auth(self, client: TestClient):
        """Docs endpoint should work without API key."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_no_auth(self, client: TestClient):
        """OpenAPI endpoint should work without API key."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_ui_root_no_auth(self, client: TestClient):
        """UI root should work without API key (redirect)."""
        response = client.get("/ui", follow_redirects=False)
        assert response.status_code == 302

    def test_ui_jobs_no_auth(self, client: TestClient):
        """UI jobs page should work without API key."""
        response = client.get("/ui/jobs")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_ui_run_no_auth(self, client: TestClient):
        """UI run page should work without API key."""
        response = client.get("/ui/run")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestProtectedRoutes:
    """Test that protected routes require authentication."""

    def test_agent_jobs_no_auth(self, client: TestClient):
        """Agent jobs endpoint should require API key."""
        response = client.get("/agent/jobs")
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing API key"

    def test_agent_run_no_auth(self, client: TestClient):
        """Agent run endpoint should require API key."""
        response = client.post("/agent/run", json={"prompt": "test"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing API key"

    def test_builder_jobs_no_auth(self, client: TestClient):
        """Builder jobs endpoint should require API key."""
        response = client.get("/builder/jobs")
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing API key"

    def test_metrics_no_auth(self, client: TestClient):
        """Metrics endpoint should require API key."""
        response = client.get("/metrics/usage")
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing API key"


class TestAPIKeyAuthentication:
    """Test API key authentication mechanisms."""

    def test_agent_jobs_with_header_key(self, client: TestClient, auth_headers: dict):
        """Agent jobs should work with X-API-Key header."""
        response = client.get("/agent/jobs", headers=auth_headers)
        assert response.status_code == 200
        assert "items" in response.json()

    def test_agent_jobs_with_bearer_token(self, client: TestClient):
        """Agent jobs should work with Bearer token."""
        response = client.get(
            "/agent/jobs",
            headers={"Authorization": "Bearer test-api-key"}
        )
        assert response.status_code == 200
        assert "items" in response.json()

    def test_invalid_api_key(self, client: TestClient, invalid_auth_headers: dict):
        """Invalid API key should return 401."""
        response = client.get("/agent/jobs", headers=invalid_auth_headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid API key"

    def test_empty_api_key(self, client: TestClient):
        """Empty API key should return 401."""
        response = client.get("/agent/jobs", headers={"X-API-Key": ""})
        assert response.status_code == 401

    def test_builder_with_key(self, client: TestClient, auth_headers: dict):
        """Builder endpoint should work with API key."""
        response = client.get("/builder/jobs", headers=auth_headers)
        assert response.status_code == 200


class TestUIContainsAPIKeyInput:
    """Test that UI pages contain API key input field."""

    def test_ui_jobs_has_api_key_input(self, client: TestClient):
        """UI jobs page should have API key input field."""
        response = client.get("/ui/jobs")
        assert response.status_code == 200
        content = response.text
        assert "apiKeyInput" in content
        assert "API Key" in content
        assert "localStorage" in content

    def test_ui_run_has_api_key_input(self, client: TestClient):
        """UI run page should have API key input field."""
        response = client.get("/ui/run")
        assert response.status_code == 200
        content = response.text
        assert "apiKeyInput" in content
        assert "X-API-Key" in content
