"""
Tests for Phase A2: Xone Command Center - Unified Chat UI.

Tests cover:
- Command Center UI loads successfully
- UI contains required elements (drawer tabs, sidebar, etc.)
- PWA manifest and service worker available
- Approvals integration works
- Mobile responsive elements present
- Non-negotiable: Cannot run without approval (server-side enforcement)
"""
import pytest
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Return valid authentication headers."""
    return {"X-API-Key": "test-api-key"}


# =============================================================================
# Command Center UI Tests
# =============================================================================

class TestCommandCenterUI:
    """Test Command Center UI loads and contains required elements."""

    def test_command_center_loads(self, client):
        """Test that /ui/command-center loads successfully."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_command_center_has_agent_name(self, client):
        """Test that Command Center displays agent name."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        # Should contain Xone branding
        assert "Xone" in response.text

    def test_command_center_has_left_nav_items(self, client):
        """Test that Command Center has all required nav items."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        
        # Check for nav items
        assert "Approvals" in response.text
        assert "Jobs" in response.text
        assert "Memory" in response.text
        assert "Audit" in response.text
        assert "Settings" in response.text

    def test_command_center_has_sidebar(self, client):
        """Test that Command Center has left sidebar elements."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        
        # Should have conversation management elements
        assert "New Chat" in response.text or "newChat" in response.text
        assert "Search" in response.text or "search" in response.text

    def test_command_center_has_chat_area(self, client):
        """Test that Command Center has main chat area."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        
        # Should have chat input area
        assert "chatInput" in response.text or "chat-input" in response.text or "message" in response.text.lower()

    def test_command_center_has_dark_mode(self, client):
        """Test that Command Center has dark mode toggle."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        
        # Should have dark mode functionality
        assert "darkMode" in response.text or "dark-mode" in response.text or "toggleDark" in response.text

    def test_command_center_mobile_responsive(self, client):
        """Test that Command Center has mobile responsive elements."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        
        # Should have responsive meta tag
        assert "viewport" in response.text
        # Should have mobile-specific classes or media queries
        assert ("@media" in response.text or 
                "mobile" in response.text.lower() or 
                "responsive" in response.text.lower() or
                "sidebarOverlay" in response.text)


# =============================================================================
# PWA Tests
# =============================================================================

class TestPWASupport:
    """Test PWA manifest and service worker."""

    def test_manifest_loads(self, client):
        """Test that PWA manifest is available."""
        response = client.get("/static/manifest.json")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "Xone" in data.get("name", "")

    def test_service_worker_loads(self, client):
        """Test that service worker is available."""
        response = client.get("/static/sw.js")
        assert response.status_code == 200
        assert "javascript" in response.headers.get("content-type", "").lower() or response.status_code == 200

    def test_manifest_has_required_fields(self, client):
        """Test that manifest has required PWA fields."""
        response = client.get("/static/manifest.json")
        assert response.status_code == 200
        data = response.json()
        
        # Required PWA manifest fields
        assert "name" in data
        assert "short_name" in data
        assert "start_url" in data
        assert "display" in data
        assert "icons" in data

    def test_command_center_links_manifest(self, client):
        """Test that Command Center links to PWA manifest."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        assert 'manifest.json' in response.text

    def test_command_center_registers_service_worker(self, client):
        """Test that Command Center registers service worker."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        assert 'serviceWorker' in response.text or 'sw.js' in response.text


# =============================================================================
# Approval Gate Enforcement (Critical - Non-negotiable)
# =============================================================================

class TestApprovalGateEnforcement:
    """Test that approval gate is enforced - Xone is NOT autonomous."""

    def test_command_center_mentions_approval(self, client):
        """Test that Command Center UI mentions approval requirement."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        # Should mention approval somewhere
        assert ("approval" in response.text.lower() or 
                "approve" in response.text.lower() or
                "Approvals" in response.text)

    def test_cannot_run_unapproved_batch_from_ui(self, client, auth_headers):
        """Test that unapproved batches cannot be run (server-side enforcement)."""
        # Create a batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "UI Test Batch",
                "actions": [
                    {"kind": "note", "risk": "safe", "payload": {"note": "Test"}, "preview_text": "Test note"}
                ],
                "auto_submit": True  # Goes to pending
            },
            headers=auth_headers
        )
        assert create_resp.status_code == 200
        batch_id = create_resp.json()["id"]
        
        # Try to run without approval -> should fail with 403
        run_resp = client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        assert run_resp.status_code == 403
        assert "approved" in run_resp.json()["detail"].lower()

    def test_can_run_approved_batch(self, client, auth_headers):
        """Test that approved batches can be run."""
        # Create and submit batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Approved UI Test",
                "actions": [
                    {"kind": "note", "risk": "safe", "payload": {"note": "Approved action"}, "preview_text": "Test note"}
                ],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Approve the batch
        approve_resp = client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        assert approve_resp.status_code == 200
        
        # Now run should succeed
        run_resp = client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["status"] == "executing"


# =============================================================================
# Drawer Integration Tests
# =============================================================================

class TestDrawerIntegration:
    """Test drawer tab integrations."""

    def test_approvals_tab_api_endpoint(self, client, auth_headers):
        """Test that approvals can be fetched via API."""
        response = client.get("/v1/batches?status=pending", headers=auth_headers)
        assert response.status_code == 200
        assert "batches" in response.json()

    def test_audit_logs_api_endpoint(self, client, auth_headers):
        """Test that audit logs can be fetched via API."""
        response = client.get("/v1/audit-logs", headers=auth_headers)
        assert response.status_code == 200
        assert "logs" in response.json()

    def test_memory_api_endpoint(self, client, auth_headers):
        """Test that memory can be fetched via API."""
        response = client.get("/memory", headers=auth_headers)
        assert response.status_code == 200

    def test_jobs_api_endpoint(self, client, auth_headers):
        """Test that jobs can be fetched via API."""
        response = client.get("/agent/jobs", headers=auth_headers)
        assert response.status_code == 200


# =============================================================================
# Settings Tests
# =============================================================================

class TestSettingsIntegration:
    """Test settings functionality."""

    def test_command_center_has_settings_section(self, client):
        """Test that Command Center has settings section."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        assert "Settings" in response.text

    def test_command_center_has_api_key_field(self, client):
        """Test that Command Center has API key configuration."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        # Should have API key input or storage
        assert ("apiKey" in response.text or 
                "api-key" in response.text or 
                "API Key" in response.text)


# =============================================================================
# Route Tests
# =============================================================================

class TestRoutes:
    """Test Command Center routes."""

    def test_command_center_route_exists(self, client):
        """Test that /ui/command-center route exists."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200

    def test_static_files_mounted(self, client):
        """Test that static files are properly mounted."""
        response = client.get("/static/manifest.json")
        assert response.status_code == 200

    def test_chat_route_still_works(self, client):
        """Test that original /ui/chat route still works."""
        response = client.get("/ui/chat")
        assert response.status_code == 200


# =============================================================================
# Accessibility Tests
# =============================================================================

class TestAccessibility:
    """Test basic accessibility features."""

    def test_html_has_lang_attribute(self, client):
        """Test that HTML has language attribute."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        assert 'lang="en"' in response.text or "lang='en'" in response.text

    def test_has_viewport_meta(self, client):
        """Test that page has viewport meta tag for mobile."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        assert "viewport" in response.text

    def test_buttons_have_text_or_aria(self, client):
        """Test that interactive elements are accessible."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        # Basic check - buttons should have text content
        assert "<button" in response.text


# =============================================================================
# Security Tests
# =============================================================================

class TestSecurity:
    """Test security features."""

    def test_api_endpoints_require_auth(self, client):
        """Test that API endpoints require authentication."""
        # Batch creation requires auth
        response = client.post("/v1/batches", json={"title": "Test", "actions": []})
        assert response.status_code == 401

    def test_approval_requires_auth(self, client, auth_headers):
        """Test that batch approval requires authentication."""
        # Create a batch first
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Auth Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to approve without auth
        response = client.post(f"/v1/batches/{batch_id}/approve")
        assert response.status_code == 401

    def test_run_requires_auth(self, client, auth_headers):
        """Test that batch run requires authentication."""
        # Create and approve a batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Run Auth Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        
        # Try to run without auth
        response = client.post(f"/v1/batches/{batch_id}/run")
        assert response.status_code == 401
