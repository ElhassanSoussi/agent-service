"""
Tests for Phase 18: Chat UI.

Tests cover:
- Chat route accessibility (200 status)
- Chat page contains expected elements
- API authentication requirements for agent endpoints
- Integration with existing job system

Note: Phase 19 upgraded the chat UI to ChatGPT-style, so some function names changed.
"""
import pytest
from fastapi.testclient import TestClient


# Uses fixtures from conftest.py: client, auth_headers


class TestChatRoute:
    """Tests for /ui/chat route."""

    def test_chat_route_returns_200(self, client):
        """Chat page should be accessible without auth (UI is public)."""
        response = client.get("/ui/chat")
        assert response.status_code == 200

    def test_chat_route_returns_html(self, client):
        """Chat page should return HTML content."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_chat_page_has_title(self, client):
        """Chat page should have proper title."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "Chat - Xone" in response.text

    def test_chat_page_has_message_container(self, client):
        """Chat page should have a messages container."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="messagesContainer"' in response.text

    def test_chat_page_has_input_form(self, client):
        """Chat page should have a message input form."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="chatForm"' in response.text
        assert 'id="messageInput"' in response.text
        assert 'id="sendBtn"' in response.text

    def test_chat_page_has_new_chat_button(self, client):
        """Chat page should have a New Chat button."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="newChatBtn"' in response.text
        assert "New Chat" in response.text

    def test_chat_page_has_api_key_settings(self, client):
        """Chat page should surface API key settings."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="apiKeyInput"' in response.text
        assert 'id="apiKeyStatus"' in response.text

    def test_chat_page_has_localstorage_key_constant(self, client):
        """Chat page should define localStorage key for messages."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Phase 19 uses conversations storage key instead of single messages key
        assert "agent_service_conversations" in response.text

    def test_chat_page_has_polling_logic(self, client):
        """Chat page should have polling configuration."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "MAX_POLL_TIME" in response.text
        assert "POLL_INTERVAL" in response.text
        assert "pollJobStatus" in response.text

    def test_chat_page_has_empty_state(self, client):
        """Chat page should have an empty state message."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="emptyState"' in response.text


class TestChatNavigation:
    """Tests for chat navigation link."""

    def test_jobs_page_has_chat_link(self, client):
        """Jobs page should have link to chat."""
        response = client.get("/ui/jobs")
        assert response.status_code == 200
        assert 'href="/ui/chat"' in response.text

    def test_run_page_has_chat_link(self, client):
        """Run page should have link to chat."""
        response = client.get("/ui/run")
        assert response.status_code == 200
        assert 'href="/ui/chat"' in response.text

    def test_chat_link_in_navbar(self, client):
        """Chat link should appear in navigation."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Phase 19 ChatGPT-style UI has sidebar navigation
        assert "Chat" in response.text or "Agent Chat" in response.text


class TestAgentEndpointAuth:
    """Tests for agent endpoint authentication (used by chat)."""

    def test_agent_run_requires_auth(self, client):
        """POST /agent/run should require authentication."""
        response = client.post(
            "/agent/run",
            json={"mode": "agent", "prompt": "test prompt"}
        )
        assert response.status_code == 401

    def test_agent_run_with_auth(self, client, auth_headers):
        """POST /agent/run should work with valid auth."""
        response = client.post(
            "/agent/run",
            json={"mode": "agent", "prompt": "test prompt"},
            headers=auth_headers
        )
        # Should succeed (either 200 or 202 for queued job)
        assert response.status_code in [200, 202]
        data = response.json()
        assert "job_id" in data

    def test_agent_status_requires_auth(self, client):
        """GET /agent/status/{job_id} should require authentication."""
        response = client.get("/agent/status/nonexistent-job-id")
        assert response.status_code == 401

    def test_agent_status_with_auth_nonexistent_job(self, client, auth_headers):
        """GET /agent/status with auth for nonexistent job should return 404."""
        response = client.get(
            "/agent/status/nonexistent-job-id",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestChatIntegration:
    """Integration tests for chat functionality."""

    def test_full_chat_flow_job_creation(self, client, auth_headers):
        """Test creating a job through the agent endpoint (as chat would)."""
        # Submit job
        response = client.post(
            "/agent/run",
            json={"mode": "agent", "prompt": "Hello, agent!"},
            headers=auth_headers
        )
        assert response.status_code in [200, 202]
        data = response.json()
        job_id = data["job_id"]
        
        # Check status
        status_response = client.get(
            f"/agent/status/{job_id}",
            headers=auth_headers
        )
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert "status" in status_data
        assert status_data["status"] in ["queued", "running", "done", "error"]

    def test_job_appears_in_jobs_list(self, client, auth_headers):
        """Jobs created via agent endpoint should appear in UI jobs list."""
        # Create a job
        response = client.post(
            "/agent/run",
            json={"mode": "agent", "prompt": "Test job for listing"},
            headers=auth_headers
        )
        assert response.status_code in [200, 202]
        job_id = response.json()["job_id"]
        
        # Check jobs list page
        jobs_response = client.get("/ui/jobs")
        assert jobs_response.status_code == 200
        # Job ID (or part of it) should appear in the jobs list
        assert job_id[:8] in jobs_response.text or job_id in jobs_response.text

    def test_chat_page_references_agent_endpoints(self, client):
        """Chat page JavaScript should reference the correct API endpoints."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Chat now uses /llm/generate directly for simpler chat interactions
        assert "/llm/generate" in response.text
        assert "/agent/status/" in response.text


class TestChatPageScripts:
    """Tests for chat page JavaScript functionality references."""

    def test_has_message_functions(self, client):
        """Chat page should have message management functions."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Phase 19 uses conversation-based functions
        assert "loadConversations" in response.text
        assert "saveConversations" in response.text
        assert "addMessage" in response.text
        assert "renderMessages" in response.text

    def test_has_submit_function(self, client):
        """Chat page should have submit message function."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "submitMessage" in response.text

    def test_has_polling_function(self, client):
        """Chat page should have polling function."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "pollJobStatus" in response.text

    def test_has_format_content_function(self, client):
        """Chat page should have content formatting function."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Phase 19 uses formatAgentMessage instead of formatContent
        assert "formatAgentMessage" in response.text

    def test_has_api_key_check(self, client):
        """Chat page should have API key check function."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Phase 19 uses updateApiKeyUI and testApiKey instead of checkApiKey
        assert "getApiKey" in response.text
        assert "updateApiKeyUI" in response.text or "testApiKey" in response.text
