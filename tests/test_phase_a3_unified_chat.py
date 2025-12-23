"""
Tests for Phase A3: Unified /ui/chat as Command Center.

Tests verify:
- /ui/chat serves the unified left-only UI
- /ui/chat contains Xone header
- /ui/chat has left navigation for core panels
- Chat send flow works from /ui/chat
- Both /ui/chat and /ui/command-center serve the same UI
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
# /ui/chat Unified Command Center Tests
# =============================================================================

class TestUnifiedChatUI:
    """Test /ui/chat is now the unified Command Center."""

    def test_chat_route_returns_200(self, client):
        """Test that /ui/chat returns HTTP 200."""
        response = client.get("/ui/chat")
        assert response.status_code == 200

    def test_chat_has_xone_header(self, client):
        """Test that /ui/chat has Xone branding in the header."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "Xone" in response.text
        assert "Agent Control Panel" not in response.text

    def test_chat_has_no_command_center_badge(self, client):
        """Test that /ui/chat has no command center badge."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "Command Center" not in response.text

    def test_chat_has_left_nav_items(self, client):
        """Test that /ui/chat has left navigation items."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        
        # Check for core nav items
        assert "Approvals" in response.text
        assert "Jobs" in response.text
        assert "Memory" in response.text
        assert "Audit" in response.text
        assert "Settings" in response.text

    def test_chat_has_no_approval_banner(self, client):
        """Test that /ui/chat has no approval banner."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "Approval Mode" not in response.text

    def test_chat_has_xone_branding(self, client):
        """Test that /ui/chat has Xone branding."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "Xone" in response.text

    def test_chat_has_chat_input(self, client):
        """Test that /ui/chat has message input area."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Should have chat input element
        assert "chatInput" in response.text or "messageInput" in response.text

    def test_chat_has_no_drawer(self, client):
        """Test that /ui/chat does not render the right drawer."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="drawer"' not in response.text

    def test_chat_has_pwa_support(self, client):
        """Test that /ui/chat has PWA manifest link."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "manifest.json" in response.text


# =============================================================================
# Unified Route Tests
# =============================================================================

class TestUnifiedRoutes:
    """Test that /ui/chat and /ui/command-center serve same content."""

    def test_chat_and_command_center_same_content(self, client):
        """Test /ui/chat and /ui/command-center return same HTML."""
        chat_response = client.get("/ui/chat")
        command_center_response = client.get("/ui/command-center")
        
        assert chat_response.status_code == 200
        assert command_center_response.status_code == 200
        
        # Both should return the same HTML content
        assert chat_response.text == command_center_response.text

    def test_both_routes_have_left_nav_items(self, client):
        """Test both routes have left nav items."""
        for route in ["/ui/chat", "/ui/command-center"]:
            response = client.get(route)
            assert response.status_code == 200
            assert "Approvals" in response.text
            assert "Settings" in response.text


# =============================================================================
# Chat Functionality Tests
# =============================================================================

class TestChatFunctionality:
    """Test chat functionality works from /ui/chat."""

    def test_agent_run_endpoint_exists(self, client, auth_headers):
        """Test that /agent/run endpoint exists for chat functionality."""
        # This is a POST endpoint, should return 422 without body (not 404)
        response = client.post("/agent/run", headers=auth_headers)
        assert response.status_code in (400, 422)  # Validation error, not 404

    def test_conversations_can_be_managed(self, client):
        """Test that conversation management is present in UI."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Should have conversation-related functionality
        assert "conversation" in response.text.lower() or "newChat" in response.text


# =============================================================================
# Sidebar Navigation Tests
# =============================================================================

class TestSidebarNavigation:
    """Test sidebar navigation elements exist."""

    def test_sidebar_has_conversations(self, client):
        """Test sidebar has conversation list area."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Should have conversation list
        assert "conversationsList" in response.text or "conversations" in response.text.lower()

    def test_has_new_chat_button(self, client):
        """Test there's a New Chat button."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "New Chat" in response.text or "newChat" in response.text

    def test_has_search_functionality(self, client):
        """Test there's search functionality."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "search" in response.text.lower()


# =============================================================================
# Mobile Responsive Tests
# =============================================================================

class TestMobileResponsive:
    """Test mobile responsive features."""

    def test_has_mobile_viewport(self, client):
        """Test page has mobile viewport meta tag."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "viewport" in response.text

    def test_has_mobile_sidebar_toggle(self, client):
        """Test page has mobile sidebar toggle."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "toggleSidebar" in response.text

    def test_has_sidebar_overlay(self, client):
        """Test page has sidebar overlay for mobile."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "sidebarOverlay" in response.text


class TestDeveloperPage:
    """Tests for Developer Xone page."""

    def test_developer_route_returns_200(self, client):
        response = client.get("/ui/developer")
        assert response.status_code == 200

    def test_developer_page_has_expected_elements(self, client):
        response = client.get("/ui/developer")
        assert response.status_code == 200
        assert "Developer Xone" in response.text
        assert 'id="developerMessageInput"' in response.text
        assert "Developer Xone" in response.text

    def test_sidebar_has_developer_item(self, client):
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "Developer Xone" in response.text


# =============================================================================
# Security Tests
# =============================================================================

class TestSecurityFromChat:
    """Test security features accessible from /ui/chat."""

    def test_api_key_input_present(self, client):
        """Test API key input is present."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "apiKey" in response.text or "API Key" in response.text

    def test_approval_enforcement_from_chat(self, client, auth_headers):
        """Test approval enforcement works (non-negotiable rule)."""
        # Create a batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Chat Test Batch",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to run without approval -> should fail with 403
        run_resp = client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        assert run_resp.status_code == 403
        assert "approved" in run_resp.json()["detail"].lower()
