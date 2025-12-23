"""
Tests for Phase 20: Local Agent Chat UI.

Tests cover:
- Provider/model badge visibility
- /llm/health returns provider/model fields
- Chat UI never renders [object Object]
- Streaming endpoint functionality
- System prompt support
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


class TestProviderBadge:
    """Tests for provider/model badge in chat UI."""

    def test_chat_page_has_provider_badge_element(self, client):
        """Chat page should have the provider badge element."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="providerBadge"' in response.text
        assert 'id="providerText"' in response.text

    def test_chat_page_fetches_llm_health(self, client):
        """Chat page should call fetchLLMHealth on load."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "fetchLLMHealth()" in response.text
        assert "/llm/health" in response.text

    def test_chat_page_has_update_provider_badge_function(self, client):
        """Chat page should have updateProviderBadge function."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "function updateProviderBadge" in response.text


class TestLLMHealthEndpoint:
    """Tests for /llm/health endpoint fields."""

    def test_health_returns_provider_field(self, client):
        """LLM health should return provider field."""
        response = client.get("/llm/health")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data

    def test_health_returns_model_field(self, client):
        """LLM health should return model field."""
        response = client.get("/llm/health")
        assert response.status_code == 200
        data = response.json()
        assert "model" in data

    def test_health_returns_status_field(self, client):
        """LLM health should return status field."""
        response = client.get("/llm/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @patch.dict('os.environ', {'LLM_PROVIDER': 'ollama', 'LLM_MODEL': 'test-model'})
    def test_health_with_ollama_provider(self, client):
        """LLM health with Ollama should return ollama provider."""
        # Note: This test may need mocking if Ollama isn't available
        response = client.get("/llm/health")
        assert response.status_code == 200
        data = response.json()
        # Provider should be in the response
        assert "provider" in data


class TestChatRenderNoObjectObject:
    """Tests to ensure chat never renders [object Object]."""

    def test_extract_output_text_function_exists(self, client):
        """Chat page should have extractOutputText function."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "function extractOutputText" in response.text

    def test_add_message_ensures_string_content(self, client):
        """addMessage should ensure content is always a string."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Check that addMessage converts non-strings
        assert "typeof content !== 'string'" in response.text
        assert "extractOutputText(content)" in response.text

    def test_format_agent_message_handles_objects(self, client):
        """formatAgentMessage should handle non-string content."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "function formatAgentMessage" in response.text
        # Should check content type and extract text
        assert "typeof content !== 'string'" in response.text

    def test_extract_output_handles_common_fields(self, client):
        """extractOutputText should handle common response fields."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        # Should check for common field names
        assert "output.response" in response.text or "output.text" in response.text
        assert "output.content" in response.text or "output.message" in response.text


class TestSettingsModal:
    """Tests for settings modal functionality."""

    def test_chat_has_settings_button(self, client):
        """Chat page should have settings button."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="settingsBtn"' in response.text

    def test_chat_has_settings_section(self, client):
        """Chat page should have settings section."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'data-section-panel="settings"' in response.text

    def test_chat_has_system_prompt_input(self, client):
        """Chat page should have system prompt input."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="systemPromptInput"' in response.text

    def test_chat_has_streaming_toggle(self, client):
        """Chat page should have streaming mode toggle."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert 'id="streamingToggle"' in response.text

    def test_system_prompt_storage_key_defined(self, client):
        """Chat page should define system prompt storage key."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "SYSTEM_PROMPT_KEY" in response.text
        assert "agent_service_system_prompt" in response.text

    def test_streaming_mode_storage_key_defined(self, client):
        """Chat page should define streaming mode storage key."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "STREAMING_MODE_KEY" in response.text
        assert "agent_service_streaming_mode" in response.text


class TestStreamingEndpoint:
    """Tests for /llm/stream SSE endpoint."""

    def test_stream_endpoint_requires_auth(self, client):
        """POST /llm/stream should require authentication."""
        response = client.post(
            "/llm/stream",
            json={"prompt": "test"}
        )
        assert response.status_code == 401

    def test_stream_endpoint_exists(self, client, auth_headers):
        """POST /llm/stream endpoint should exist."""
        # This will likely fail with 503 if Ollama isn't configured
        # but at least proves the endpoint exists
        response = client.post(
            "/llm/stream",
            json={"prompt": "test"},
            headers=auth_headers
        )
        # 503 = no provider, 400 = wrong provider, 200 = success
        assert response.status_code in [200, 400, 503]


class TestGenerateWithSystemPrompt:
    """Tests for /llm/generate with system_prompt parameter."""

    def test_generate_accepts_system_prompt(self, client, auth_headers):
        """POST /llm/generate should accept system_prompt parameter."""
        # This will fail if no provider, but validates the schema accepts it
        response = client.post(
            "/llm/generate",
            json={"prompt": "test", "system_prompt": "Be helpful"},
            headers=auth_headers
        )
        # Should not get 422 (validation error) for system_prompt
        assert response.status_code != 422


class TestOllamaProviderGuard:
    """Tests to verify Ollama provider doesn't call OpenAI."""

    def test_generate_endpoint_has_provider_check(self):
        """Generate endpoint should check provider before calling OpenAI."""
        # Read the llm.py file and verify the guard exists
        with open("/home/elhassan/agent-service/app/api/llm.py", "r") as f:
            content = f.read()
        
        # Should have explicit provider checks
        assert 'config.provider in ("ollama", "local")' in content
        assert 'config.provider == "openai"' in content

    def test_ollama_client_never_imports_openai(self):
        """Ollama client should not import OpenAI modules."""
        with open("/home/elhassan/agent-service/app/llm/providers/ollama_client.py", "r") as f:
            content = f.read()
        
        assert "import openai" not in content.lower()
        assert "from openai" not in content.lower()


class TestChatUIUsesLLMGenerate:
    """Tests that chat UI uses correct endpoints."""

    def test_chat_uses_llm_generate(self, client):
        """Chat page should use /llm/generate endpoint."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "/llm/generate" in response.text

    def test_chat_uses_llm_stream(self, client):
        """Chat page should reference /llm/stream for streaming."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "/llm/stream" in response.text

    def test_chat_has_streaming_submit_function(self, client):
        """Chat page should have submitMessageStreaming function."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "submitMessageStreaming" in response.text

    def test_chat_has_non_streaming_submit_function(self, client):
        """Chat page should have submitMessageNonStreaming function."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "submitMessageNonStreaming" in response.text


class TestStreamingUI:
    """Tests for streaming UI features."""

    def test_chat_has_streaming_cursor_style(self, client):
        """Chat page should have streaming cursor CSS."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "streaming-cursor" in response.text

    def test_chat_has_streaming_state_variable(self, client):
        """Chat page should have streamingEnabled state variable."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "streamingEnabled" in response.text
