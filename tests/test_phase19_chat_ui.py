"""
Tests for Phase 19: ChatGPT-style Chat UI.

Tests cover:
- Chat route accessibility
- ChatGPT-style UI elements (sidebar, conversations list, message area)
- API key warning banner
- Test key functionality
- Keyboard shortcuts documentation
- Fetch wrapper for X-API-Key
- No raw JSON errors shown to users
"""
import pytest
from fastapi.testclient import TestClient


# Uses fixtures from conftest.py: client, auth_headers


class TestChatPageStructure:
    """Tests for ChatGPT-style chat page structure."""

    def test_chat_route_returns_200(self, client: TestClient):
        """Chat page should be accessible without auth (UI is public)."""
        response = client.get("/ui/chat")
        assert response.status_code == 200

    def test_chat_route_returns_html(self, client: TestClient):
        """Chat page should return HTML content."""
        response = client.get("/ui/chat")
        assert "text/html" in response.headers["content-type"]

    def test_chat_page_has_title(self, client: TestClient):
        """Chat page should have proper title."""
        response = client.get("/ui/chat")
        assert "Chat - Xone" in response.text

    def test_chat_page_has_sidebar(self, client: TestClient):
        """Chat page should have a sidebar element."""
        response = client.get("/ui/chat")
        assert 'id="sidebar"' in response.text

    def test_chat_page_has_conversations_list(self, client: TestClient):
        """Chat page should have a conversations list in sidebar."""
        response = client.get("/ui/chat")
        assert 'id="conversationsList"' in response.text

    def test_chat_page_has_new_chat_button(self, client: TestClient):
        """Chat page should have a New Chat button."""
        response = client.get("/ui/chat")
        assert 'id="newChatBtn"' in response.text
        assert "New Chat" in response.text

    def test_chat_page_has_messages_container(self, client: TestClient):
        """Chat page should have a messages container."""
        response = client.get("/ui/chat")
        assert 'id="messagesContainer"' in response.text

    def test_chat_page_has_messages_wrapper(self, client: TestClient):
        """Chat page should have a messages wrapper for rendered messages."""
        response = client.get("/ui/chat")
        assert 'id="messagesWrapper"' in response.text

    def test_chat_page_has_typing_indicator(self, client: TestClient):
        """Chat page should have a typing indicator element."""
        response = client.get("/ui/chat")
        assert 'id="typingIndicator"' in response.text

    def test_chat_page_has_chat_form(self, client: TestClient):
        """Chat page should have a chat form."""
        response = client.get("/ui/chat")
        assert 'id="chatForm"' in response.text

    def test_chat_page_has_message_input(self, client: TestClient):
        """Chat page should have a message input textarea."""
        response = client.get("/ui/chat")
        assert 'id="messageInput"' in response.text
        assert "<textarea" in response.text

    def test_chat_page_has_send_button(self, client: TestClient):
        """Chat page should have a send button."""
        response = client.get("/ui/chat")
        assert 'id="sendBtn"' in response.text


class TestApiKeyUI:
    """Tests for API key UI elements."""

    def test_chat_page_has_api_key_input(self, client: TestClient):
        """Chat page should have an API key input."""
        response = client.get("/ui/chat")
        assert 'id="apiKeyInput"' in response.text

    def test_chat_page_has_api_key_status(self, client: TestClient):
        """Chat page should have an API key status indicator."""
        response = client.get("/ui/chat")
        assert 'id="apiKeyStatus"' in response.text

    def test_chat_page_no_api_key_warning(self, client: TestClient):
        """Chat page should not show a global API key warning banner."""
        response = client.get("/ui/chat")
        assert 'id="apiKeyWarning"' not in response.text

    def test_chat_page_has_save_key_button(self, client: TestClient):
        """Chat page should have a save key button."""
        response = client.get("/ui/chat")
        assert 'id="saveKeyBtn"' in response.text

    def test_chat_page_has_test_key_button(self, client: TestClient):
        """Chat page should have a test key button."""
        response = client.get("/ui/chat")
        assert 'id="testKeyBtn"' in response.text
        assert "Test" in response.text


class TestLocalStorageKeys:
    """Tests for localStorage key constants."""

    def test_has_api_key_storage_key(self, client: TestClient):
        """Chat page should define API key storage key constant."""
        response = client.get("/ui/chat")
        assert "API_KEY_STORAGE_KEY" in response.text
        assert "agent_service_api_key" in response.text

    def test_has_conversations_storage_key(self, client: TestClient):
        """Chat page should define conversations storage key constant."""
        response = client.get("/ui/chat")
        assert "CONVERSATIONS_STORAGE_KEY" in response.text
        assert "agent_service_conversations" in response.text

    def test_has_current_conversation_key(self, client: TestClient):
        """Chat page should define current conversation key constant."""
        response = client.get("/ui/chat")
        assert "CURRENT_CONV_KEY" in response.text
        assert "agent_service_current_conversation" in response.text


class TestFetchWrapper:
    """Tests for fetch wrapper that adds X-API-Key."""

    def test_has_fetch_override(self, client: TestClient):
        """Chat page should override window.fetch to add API key."""
        response = client.get("/ui/chat")
        assert "originalFetch = window.fetch" in response.text
        assert "window.fetch = function" in response.text

    def test_fetch_adds_api_key_header(self, client: TestClient):
        """Fetch override should add X-API-Key header."""
        response = client.get("/ui/chat")
        assert "X-API-Key" in response.text
        assert "options.headers['X-API-Key']" in response.text or "headers.set('X-API-Key'" in response.text


class TestKeyboardShortcuts:
    """Tests for keyboard shortcut documentation."""

    def test_has_enter_to_send_hint(self, client: TestClient):
        """Chat page should mention Enter to send."""
        response = client.get("/ui/chat")
        assert "Enter to send" in response.text

    def test_has_shift_enter_hint(self, client: TestClient):
        """Chat page should mention Shift+Enter for new line."""
        response = client.get("/ui/chat")
        assert "Shift+Enter" in response.text

    def test_has_keydown_handler(self, client: TestClient):
        """Chat page should have keydown handler for Enter key."""
        response = client.get("/ui/chat")
        assert "keydown" in response.text
        assert "e.key === 'Enter'" in response.text


class TestChatFunctions:
    """Tests for chat JavaScript functions."""

    def test_has_get_api_key_function(self, client: TestClient):
        """Chat page should have getApiKey function."""
        response = client.get("/ui/chat")
        assert "function getApiKey()" in response.text

    def test_has_set_api_key_function(self, client: TestClient):
        """Chat page should have setApiKey function."""
        response = client.get("/ui/chat")
        assert "function setApiKey(" in response.text

    def test_has_test_api_key_function(self, client: TestClient):
        """Chat page should have testApiKey function."""
        response = client.get("/ui/chat")
        assert "async function testApiKey()" in response.text

    def test_has_load_conversations_function(self, client: TestClient):
        """Chat page should have loadConversations function."""
        response = client.get("/ui/chat")
        assert "function loadConversations()" in response.text

    def test_has_save_conversations_function(self, client: TestClient):
        """Chat page should have saveConversations function."""
        response = client.get("/ui/chat")
        assert "function saveConversations()" in response.text

    def test_has_create_conversation_function(self, client: TestClient):
        """Chat page should have createNewConversation function."""
        response = client.get("/ui/chat")
        assert "function createNewConversation()" in response.text

    def test_has_switch_conversation_function(self, client: TestClient):
        """Chat page should have switchConversation function."""
        response = client.get("/ui/chat")
        assert "function switchConversation(" in response.text

    def test_has_delete_conversation_function(self, client: TestClient):
        """Chat page should have deleteConversation function."""
        response = client.get("/ui/chat")
        assert "function deleteConversation(" in response.text

    def test_has_submit_message_function(self, client: TestClient):
        """Chat page should have submitMessage function."""
        response = client.get("/ui/chat")
        assert "async function submitMessage(" in response.text

    def test_has_poll_job_status_function(self, client: TestClient):
        """Chat page should have pollJobStatus function."""
        response = client.get("/ui/chat")
        assert "async function pollJobStatus(" in response.text

    def test_has_format_agent_message_function(self, client: TestClient):
        """Chat page should have formatAgentMessage function."""
        response = client.get("/ui/chat")
        assert "function formatAgentMessage(" in response.text


class TestPollingConfiguration:
    """Tests for polling configuration."""

    def test_has_max_poll_time(self, client: TestClient):
        """Chat page should define max poll time."""
        response = client.get("/ui/chat")
        assert "MAX_POLL_TIME" in response.text
        assert "60000" in response.text

    def test_has_poll_interval(self, client: TestClient):
        """Chat page should define poll interval."""
        response = client.get("/ui/chat")
        assert "POLL_INTERVAL" in response.text
        assert "1000" in response.text


class TestApiEndpoints:
    """Tests for API endpoint references."""

    def test_references_llm_generate(self, client: TestClient):
        """Chat page should reference /llm/generate endpoint for direct LLM chat."""
        response = client.get("/ui/chat")
        assert "/llm/generate" in response.text

    def test_references_agent_status(self, client: TestClient):
        """Chat page should reference /agent/status endpoint."""
        response = client.get("/ui/chat")
        assert "/agent/status/" in response.text

    def test_references_health_endpoint(self, client: TestClient):
        """Chat page should reference /health endpoint for key testing."""
        response = client.get("/ui/chat")
        assert "/health" in response.text


class TestNavigationLinks:
    """Tests for navigation links in chat sidebar."""

    def test_has_jobs_dashboard_link(self, client: TestClient):
        """Chat page should have link to jobs dashboard."""
        response = client.get("/ui/chat")
        assert 'href="/ui/jobs"' in response.text
        assert "Jobs Dashboard" in response.text

    def test_has_api_docs_link(self, client: TestClient):
        """Chat page should have link to API docs."""
        response = client.get("/ui/chat")
        assert 'href="/docs"' in response.text
        assert "API Docs" in response.text


class TestMessageFormatting:
    """Tests for message formatting capabilities."""

    def test_handles_code_blocks(self, client: TestClient):
        """Chat page should handle code block formatting."""
        response = client.get("/ui/chat")
        # Check for code block regex pattern
        assert "```" in response.text

    def test_handles_inline_code(self, client: TestClient):
        """Chat page should handle inline code formatting."""
        response = client.get("/ui/chat")
        # Check for inline code handling
        assert "`" in response.text

    def test_handles_bold_text(self, client: TestClient):
        """Chat page should handle bold text formatting."""
        response = client.get("/ui/chat")
        assert "**" in response.text or "<strong>" in response.text

    def test_escapes_html(self, client: TestClient):
        """Chat page should escape HTML to prevent XSS."""
        response = client.get("/ui/chat")
        assert "escapeHtml" in response.text


class TestEmptyState:
    """Tests for empty state display."""

    def test_has_empty_state_element(self, client: TestClient):
        """Chat page should have empty state element."""
        response = client.get("/ui/chat")
        assert 'id="emptyState"' in response.text

    def test_empty_state_has_helpful_text(self, client: TestClient):
        """Empty state should have helpful text."""
        response = client.get("/ui/chat")
        assert "How can I help you today?" in response.text


class TestNoRawJsonErrors:
    """Tests to ensure no raw JSON errors are shown."""

    def test_chat_page_no_json_error_content(self, client: TestClient):
        """Chat page should not contain raw JSON error strings."""
        response = client.get("/ui/chat")
        # The page should never show raw {"detail":"..."} to users
        assert '{"detail":' not in response.text

    def test_error_handling_exists(self, client: TestClient):
        """Chat page should have error handling for API responses."""
        response = client.get("/ui/chat")
        assert "catch" in response.text
        assert "error" in response.text.lower()


class TestAgentEndpointAuth:
    """Tests for agent endpoint authentication (used by chat)."""

    def test_agent_run_requires_auth(self, client: TestClient):
        """POST /agent/run should require authentication."""
        response = client.post(
            "/agent/run",
            json={"mode": "agent", "prompt": "test prompt"}
        )
        assert response.status_code == 401

    def test_agent_run_with_auth(self, client: TestClient, auth_headers):
        """POST /agent/run should work with valid auth."""
        response = client.post(
            "/agent/run",
            json={"mode": "agent", "prompt": "test prompt"},
            headers=auth_headers
        )
        assert response.status_code in [200, 202]
        data = response.json()
        assert "job_id" in data

    def test_agent_status_requires_auth(self, client: TestClient):
        """GET /agent/status/{job_id} should require authentication."""
        response = client.get("/agent/status/nonexistent-job-id")
        assert response.status_code == 401

    def test_agent_status_with_auth_nonexistent_job(self, client: TestClient, auth_headers):
        """GET /agent/status with auth for nonexistent job should return 404."""
        response = client.get(
            "/agent/status/nonexistent-job-id",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestUIStyles:
    """Tests for UI styling elements."""

    def test_uses_tailwind(self, client: TestClient):
        """Chat page should use Tailwind CSS."""
        response = client.get("/ui/chat")
        assert "tailwindcss" in response.text

    def test_has_custom_scrollbar_styles(self, client: TestClient):
        """Chat page should have custom scrollbar styles."""
        response = client.get("/ui/chat")
        assert "custom-scrollbar" in response.text

    def test_has_typing_animation(self, client: TestClient):
        """Chat page should have typing animation styles."""
        response = client.get("/ui/chat")
        assert "typing-dot" in response.text
        assert "typingBounce" in response.text

    def test_has_fade_in_animation(self, client: TestClient):
        """Chat page should have fade-in animation."""
        response = client.get("/ui/chat")
        assert "fade-in" in response.text
        assert "fadeIn" in response.text


class TestResponsiveDesign:
    """Tests for responsive design elements."""

    def test_has_toggle_sidebar_button(self, client: TestClient):
        """Chat page should have toggle sidebar button for mobile."""
        response = client.get("/ui/chat")
        assert 'id="toggleSidebar"' in response.text

    def test_has_responsive_classes(self, client: TestClient):
        """Chat page should use responsive Tailwind classes."""
        response = client.get("/ui/chat")
        assert "lg:hidden" in response.text or "md:" in response.text


class TestDarkMode:
    """Tests for dark mode functionality."""

    def test_has_dark_mode_toggle(self, client: TestClient):
        """Chat page should have dark mode toggle button."""
        response = client.get("/ui/chat")
        assert 'id="darkModeToggle"' in response.text

    def test_has_dark_mode_storage_key(self, client: TestClient):
        """Chat page should have dark mode storage key."""
        response = client.get("/ui/chat")
        assert "DARK_MODE_KEY" in response.text
        assert "agent_service_dark_mode" in response.text

    def test_has_dark_mode_classes(self, client: TestClient):
        """Chat page should have dark mode Tailwind classes."""
        response = client.get("/ui/chat")
        assert "dark:" in response.text

    def test_has_init_dark_mode_function(self, client: TestClient):
        """Chat page should have initDarkMode function."""
        response = client.get("/ui/chat")
        assert "initDarkMode" in response.text

    def test_has_toggle_dark_mode_function(self, client: TestClient):
        """Chat page should have toggleDarkMode function."""
        response = client.get("/ui/chat")
        assert "toggleDarkMode" in response.text


class TestCopyFunctionality:
    """Tests for copy message functionality."""

    def test_has_copy_message_function(self, client: TestClient):
        """Chat page should have copyMessage function."""
        response = client.get("/ui/chat")
        assert "copyMessage" in response.text

    def test_has_copy_code_block_function(self, client: TestClient):
        """Chat page should have copyCodeBlock function."""
        response = client.get("/ui/chat")
        assert "copyCodeBlock" in response.text

    def test_has_copy_button_class(self, client: TestClient):
        """Chat page should have copy button styling."""
        response = client.get("/ui/chat")
        assert "copy-btn" in response.text


class TestPromptSuggestions:
    """Tests for prompt suggestion buttons."""

    def test_has_prompt_suggestion_function(self, client: TestClient):
        """Chat page should have usePromptSuggestion function."""
        response = client.get("/ui/chat")
        assert "usePromptSuggestion" in response.text

    def test_has_suggestion_buttons(self, client: TestClient):
        """Chat page should have suggestion buttons in empty state."""
        response = client.get("/ui/chat")
        # Check for suggestion buttons
        assert "Get Started" in response.text or "Web Search" in response.text


class TestExtractOutputText:
    """Tests for extractOutputText function that prevents [object Object] display."""

    def test_has_extract_output_text_function(self, client: TestClient):
        """Chat page should have extractOutputText function."""
        response = client.get("/ui/chat")
        assert "extractOutputText" in response.text

    def test_extract_output_handles_string(self, client: TestClient):
        """extractOutputText should handle string content."""
        response = client.get("/ui/chat")
        # Check function handles string type
        assert "typeof output === 'string'" in response.text

    def test_extract_output_handles_object(self, client: TestClient):
        """extractOutputText should handle object content."""
        response = client.get("/ui/chat")
        # Check function handles object type
        assert "typeof output === 'object'" in response.text

    def test_extract_output_checks_final_output(self, client: TestClient):
        """extractOutputText should check for final_output field."""
        response = client.get("/ui/chat")
        assert "output.final_output" in response.text

    def test_extract_output_used_in_add_message(self, client: TestClient):
        """extractOutputText should be used in addMessage for safety."""
        response = client.get("/ui/chat")
        # The function should be called in addMessage to safely extract text
        assert "extractOutputText(content)" in response.text

    def test_add_message_ensures_string_content(self, client: TestClient):
        """addMessage should ensure content is always a string."""
        response = client.get("/ui/chat")
        # The function should convert non-string content to string
        assert "typeof content !== 'string'" in response.text


class TestNoCacheHeaders:
    """Tests for no-cache headers on UI routes."""

    def test_chat_route_has_cache_control_header(self, client: TestClient):
        """Chat page should have Cache-Control no-cache header."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "no-store" in response.headers.get("cache-control", "").lower()
        assert "no-cache" in response.headers.get("cache-control", "").lower()

    def test_chat_route_has_pragma_header(self, client: TestClient):
        """Chat page should have Pragma no-cache header."""
        response = client.get("/ui/chat")
        assert response.headers.get("pragma", "").lower() == "no-cache"

    def test_chat_route_has_expires_header(self, client: TestClient):
        """Chat page should have Expires: 0 header."""
        response = client.get("/ui/chat")
        assert response.headers.get("expires") == "0"

    def test_command_center_route_has_cache_control_header(self, client: TestClient):
        """Command center page should have Cache-Control no-cache header."""
        response = client.get("/ui/command-center")
        assert response.status_code == 200
        assert "no-store" in response.headers.get("cache-control", "").lower()

    def test_command_center_route_has_pragma_header(self, client: TestClient):
        """Command center page should have Pragma no-cache header."""
        response = client.get("/ui/command-center")
        assert response.headers.get("pragma", "").lower() == "no-cache"

    def test_chat_and_command_center_serve_same_content(self, client: TestClient):
        """/ui/chat and /ui/command-center should serve identical content."""
        chat_response = client.get("/ui/chat")
        command_response = client.get("/ui/command-center")
        assert chat_response.status_code == 200
        assert command_response.status_code == 200
        # Both should serve the Command Center UI
        assert "Chat - Xone" in chat_response.text
        assert "Chat - Xone" in command_response.text
        # Content should be identical
        assert chat_response.text == command_response.text
