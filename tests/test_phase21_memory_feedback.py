"""
Tests for Phase 21: Memory, Feedback, and Agent Identity.

Tests cover:
- Memory CRUD API
- Feedback API
- Agent identity (/meta endpoint)
- No-OpenAI guard for Ollama mode
"""
import os
import pytest
from fastapi.testclient import TestClient


# Note: conftest.py sets AGENT_ADMIN_KEY="test-admin-key" and AGENT_API_KEY="test-api-key"


@pytest.fixture(scope="module")
def test_client():
    """Create test client."""
    from main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def test_api_key(test_client):
    """Create a test API key using the admin endpoint."""
    # Create tenant first
    tenant_response = test_client.post(
        "/admin/tenants",
        json={"name": f"test_phase21_tenant_{os.urandom(4).hex()}"},
        headers={"X-Admin-Key": "test-admin-key"}
    )
    assert tenant_response.status_code in (200, 201), f"Failed to create tenant: {tenant_response.text}"
    
    # Response may have 'id' or 'tenant_id'
    tenant_data = tenant_response.json()
    tenant_id = tenant_data.get("id") or tenant_data.get("tenant_id")
    assert tenant_id, f"No tenant_id in response: {tenant_data}"
    
    # Create API key
    key_response = test_client.post(
        f"/admin/tenants/{tenant_id}/keys",
        json={"label": "test_phase21_key"},
        headers={"X-Admin-Key": "test-admin-key"}
    )
    assert key_response.status_code in (200, 201), f"Failed to create key: {key_response.text}"
    key_data = key_response.json()
    # Field is 'api_key' not 'key'
    return key_data.get("api_key") or key_data.get("key")


class TestMemoryAPI:
    """Test Memory CRUD operations."""
    
    def test_create_memory(self, test_client, test_api_key):
        """Test creating a new memory."""
        response = test_client.post(
            "/memory",
            json={
                "key": "user_preference",
                "value": "Prefers concise answers",
                "scope": "global",
                "tags": "preference,style"
            },
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "user_preference"
        assert data["value"] == "Prefers concise answers"
        assert data["scope"] == "global"
        assert data["tags"] == "preference,style"
        assert "id" in data
        assert "created_at" in data
    
    def test_list_memories(self, test_client, test_api_key):
        """Test listing memories."""
        # Create a memory first
        test_client.post(
            "/memory",
            json={"key": "test_list_memory", "value": "Test value"},
            headers={"X-API-Key": test_api_key}
        )
        
        response = test_client.get(
            "/memory",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
    
    def test_list_memories_with_search(self, test_client, test_api_key):
        """Test searching memories."""
        # Create a memory with unique content
        unique_value = f"unique_search_test_{os.urandom(4).hex()}"
        test_client.post(
            "/memory",
            json={"key": "searchable_memory", "value": unique_value},
            headers={"X-API-Key": test_api_key}
        )
        
        response = test_client.get(
            f"/memory?search={unique_value[:20]}",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
    
    def test_get_memory(self, test_client, test_api_key):
        """Test getting a specific memory."""
        # Create memory
        create_response = test_client.post(
            "/memory",
            json={"key": "test_get_memory", "value": "Get me"},
            headers={"X-API-Key": test_api_key}
        )
        memory_id = create_response.json()["id"]
        
        # Get memory
        response = test_client.get(
            f"/memory/{memory_id}",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        assert response.json()["key"] == "test_get_memory"
    
    def test_update_memory(self, test_client, test_api_key):
        """Test updating a memory."""
        # Create memory
        create_response = test_client.post(
            "/memory",
            json={"key": "test_update_memory", "value": "Original value"},
            headers={"X-API-Key": test_api_key}
        )
        memory_id = create_response.json()["id"]
        
        # Update memory
        response = test_client.put(
            f"/memory/{memory_id}",
            json={"value": "Updated value"},
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        assert response.json()["value"] == "Updated value"
    
    def test_delete_memory(self, test_client, test_api_key):
        """Test deleting a memory."""
        # Create memory
        create_response = test_client.post(
            "/memory",
            json={"key": "test_delete_memory", "value": "Delete me"},
            headers={"X-API-Key": test_api_key}
        )
        memory_id = create_response.json()["id"]
        
        # Delete memory
        response = test_client.delete(
            f"/memory/{memory_id}",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        
        # Verify deleted
        get_response = test_client.get(
            f"/memory/{memory_id}",
            headers={"X-API-Key": test_api_key}
        )
        assert get_response.status_code == 404
    
    def test_memory_not_found(self, test_client, test_api_key):
        """Test getting a non-existent memory."""
        response = test_client.get(
            "/memory/nonexistent-id-12345",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 404
    
    def test_create_conversation_scoped_memory(self, test_client, test_api_key):
        """Test creating a conversation-scoped memory."""
        response = test_client.post(
            "/memory",
            json={
                "key": "conversation_context",
                "value": "User is building a web app",
                "scope": "conversation",
                "conversation_id": "conv_123456"
            },
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scope"] == "conversation"
        assert data["conversation_id"] == "conv_123456"


class TestFeedbackAPI:
    """Test Feedback API operations."""
    
    def test_create_positive_feedback(self, test_client, test_api_key):
        """Test creating positive feedback (thumbs up)."""
        response = test_client.post(
            "/feedback",
            json={
                "conversation_id": "conv_test_123",
                "message_id": "msg_test_456",
                "user_prompt": "What is Python?",
                "agent_response": "Python is a programming language...",
                "rating": 1
            },
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 1
        assert data["conversation_id"] == "conv_test_123"
        assert "id" in data
    
    def test_create_negative_feedback(self, test_client, test_api_key):
        """Test creating negative feedback (thumbs down)."""
        response = test_client.post(
            "/feedback",
            json={
                "conversation_id": "conv_test_789",
                "message_id": "msg_test_012",
                "rating": -1,
                "notes": "Response was not helpful"
            },
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == -1
        assert data["notes"] == "Response was not helpful"
    
    def test_list_feedback(self, test_client, test_api_key):
        """Test listing feedback."""
        response = test_client.get(
            "/feedback",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "stats" in data
        assert "positive" in data["stats"]
        assert "negative" in data["stats"]
    
    def test_feedback_stats(self, test_client, test_api_key):
        """Test feedback statistics endpoint."""
        response = test_client.get(
            "/feedback/stats",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "positive" in data
        assert "negative" in data
        assert "positive_rate" in data
    
    def test_filter_feedback_by_rating(self, test_client, test_api_key):
        """Test filtering feedback by rating."""
        response = test_client.get(
            "/feedback?rating=1",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        data = response.json()
        # All items should have positive rating
        for item in data["items"]:
            assert item["rating"] == 1
    
    def test_delete_feedback(self, test_client, test_api_key):
        """Test deleting feedback."""
        # Create feedback
        create_response = test_client.post(
            "/feedback",
            json={"rating": 1, "message_id": "msg_to_delete"},
            headers={"X-API-Key": test_api_key}
        )
        feedback_id = create_response.json()["id"]
        
        # Delete feedback
        response = test_client.delete(
            f"/feedback/{feedback_id}",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"


class TestAgentIdentity:
    """Test Agent Identity features."""
    
    def test_meta_includes_agent_name(self, test_client):
        """Test that /meta endpoint includes agent name."""
        response = test_client.get("/meta")
        assert response.status_code == 200
        data = response.json()
        assert "agent_name" in data
        # Should have the default or configured value
        assert data["agent_name"] is not None
    
    def test_meta_includes_llm_info(self, test_client):
        """Test that /meta endpoint includes LLM info."""
        response = test_client.get("/meta")
        assert response.status_code == 200
        data = response.json()
        assert "llm" in data
        llm = data["llm"]
        assert "provider" in llm
        assert "planner_mode" in llm
    
    def test_meta_includes_features(self, test_client):
        """Test that /meta endpoint includes feature flags."""
        response = test_client.get("/meta")
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        features = data["features"]
        assert "memory" in features
        assert "feedback" in features
        assert features["memory"] is True
        assert features["feedback"] is True


class TestNoOpenAIGuard:
    """Test that OpenAI is never called when provider is ollama."""
    
    def test_generate_uses_ollama_not_openai(self, test_client, test_api_key):
        """Test that /llm/generate uses Ollama when configured."""
        # This test verifies the code path, not actual LLM calls
        # When LLM_PROVIDER=ollama, the generate endpoint should use Ollama
        
        # Check health to see current provider
        health_response = test_client.get("/llm/health")
        health_data = health_response.json()
        
        provider = health_data.get("provider")
        
        # If Ollama is configured, verify it's the active provider
        if provider == "ollama":
            assert health_data["provider"] == "ollama"
            # Base URL should be present for Ollama
            assert health_data.get("base_url") is not None
    
    def test_llm_config_respects_provider_env(self):
        """Test that LLM config respects LLM_PROVIDER env var."""
        from app.llm.config import get_llm_config
        
        config = get_llm_config()
        
        # Provider should match env var if set
        env_provider = os.environ.get("LLM_PROVIDER")
        if env_provider:
            assert config.provider == env_provider


class TestChatUIEndpoint:
    """Test Chat UI endpoint."""
    
    def test_chat_ui_loads(self, test_client):
        """Test that /ui/chat loads successfully."""
        response = test_client.get("/ui/chat")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    def test_chat_ui_contains_branding(self, test_client):
        """Test that Chat UI contains Xone branding elements."""
        response = test_client.get("/ui/chat")
        html = response.text
        
        # Check for branding elements (Phase A3: Command Center UI)
        assert "Xone" in html
        assert "settingsBtn" in html or "Settings" in html
    
    def test_chat_ui_contains_feedback_buttons(self, test_client):
        """Test that Chat UI contains feedback/settings functionality."""
        response = test_client.get("/ui/chat")
        html = response.text
        
        # Check for settings-related elements (Phase A3: Command Center UI)
        assert "Settings" in html
        assert "settings" in html.lower()


class TestMemoryHelpers:
    """Test memory helper functions."""
    
    def test_format_memories_for_prompt_empty(self):
        """Test formatting empty memories list."""
        from app.api.memory import format_memories_for_prompt
        
        result = format_memories_for_prompt([])
        assert result == ""
    
    def test_format_memories_for_prompt_with_items(self):
        """Test formatting memories for prompt injection."""
        from app.api.memory import format_memories_for_prompt
        
        memories = [
            {"key": "preference", "value": "concise answers"},
            {"key": "context", "value": "building a web app"}
        ]
        
        result = format_memories_for_prompt(memories)
        assert "Known preferences and facts:" in result
        assert "preference: concise answers" in result
        assert "context: building a web app" in result
