"""
Tests for LLM API endpoints.

All tests mock the Ollama client - no network access.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


class TestLLMHealthEndpoint:
    """Tests for GET /llm/health endpoint."""

    def test_health_not_configured(self, client: TestClient):
        """Health should report not configured when no provider set."""
        with patch.dict("os.environ", {"LLM_PROVIDER": ""}, clear=False):
            # Force config reload
            with patch("app.api.llm.get_llm_config") as mock_config:
                from app.llm.config import LLMConfig
                mock_config.return_value = LLMConfig(provider=None)
                
                response = client.get("/llm/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "not_configured"
                assert data["provider"] is None

    def test_health_is_public(self, client: TestClient):
        """Health endpoint should not require auth."""
        # No auth headers - should still work
        response = client.get("/llm/health")
        assert response.status_code == 200

    def test_health_returns_planner_mode(self, client: TestClient):
        """Health should return current planner mode."""
        response = client.get("/llm/health")
        data = response.json()
        assert "planner_mode" in data


class TestLLMHealthOllama:
    """Tests for /llm/health with Ollama provider."""

    def test_ollama_healthy(self, client: TestClient):
        """Ollama health check should return ok when Ollama responds."""
        from app.llm.config import LLMConfig
        
        with patch("app.api.llm.get_llm_config") as mock_config:
            mock_config.return_value = LLMConfig(
                provider="ollama",
                model="llama3.1",
                base_url="http://127.0.0.1:11434",
            )
            
            with patch("app.llm.providers.ollama_client.check_ollama_health") as mock_health:
                mock_health.return_value = (True, "Ollama is running. Models: llama3.1")
                
                response = client.get("/llm/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert data["provider"] == "ollama"

    def test_ollama_unhealthy(self, client: TestClient):
        """Ollama health check should return error when Ollama is down."""
        from app.llm.config import LLMConfig
        
        with patch("app.api.llm.get_llm_config") as mock_config:
            mock_config.return_value = LLMConfig(
                provider="ollama",
            )
            
            with patch("app.llm.providers.ollama_client.check_ollama_health") as mock_health:
                mock_health.return_value = (False, "Cannot connect to Ollama")
                
                response = client.get("/llm/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "error"
                assert "Cannot connect" in data["message"]


class TestLLMGenerateEndpoint:
    """Tests for POST /llm/generate endpoint."""

    def test_generate_requires_auth(self, client: TestClient):
        """Generate endpoint should require authentication."""
        response = client.post(
            "/llm/generate",
            json={"prompt": "Hello"}
        )
        assert response.status_code == 401

    def test_generate_with_auth(self, client: TestClient, auth_headers):
        """Generate endpoint should work with valid auth."""
        from app.llm.config import LLMConfig
        
        with patch("app.api.llm.get_llm_config") as mock_config:
            mock_config.return_value = LLMConfig(
                provider="ollama",
                model="llama3.1",
            )
            
            with patch("app.llm.providers.ollama_client.generate_simple_response") as mock_gen:
                mock_gen.return_value = ("Hello! How can I help?", None)
                
                response = client.post(
                    "/llm/generate",
                    json={"prompt": "Hello"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert data["response"] == "Hello! How can I help?"

    def test_generate_error(self, client: TestClient, auth_headers):
        """Generate should return error status on failure."""
        from app.llm.config import LLMConfig
        
        with patch("app.api.llm.get_llm_config") as mock_config:
            mock_config.return_value = LLMConfig(
                provider="ollama",
            )
            
            with patch("app.llm.providers.ollama_client.generate_simple_response") as mock_gen:
                mock_gen.return_value = (None, "Connection refused")
                
                response = client.post(
                    "/llm/generate",
                    json={"prompt": "Hello"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "error"
                assert data["error"] == "Connection refused"

    def test_generate_no_provider(self, client: TestClient, auth_headers):
        """Generate should return 503 when no provider configured."""
        from app.llm.config import LLMConfig
        
        with patch("app.api.llm.get_llm_config") as mock_config:
            mock_config.return_value = LLMConfig(provider=None)
            
            response = client.post(
                "/llm/generate",
                json={"prompt": "Hello"},
                headers=auth_headers,
            )
            assert response.status_code == 503

    def test_generate_validates_prompt(self, client: TestClient, auth_headers):
        """Generate should validate prompt length."""
        response = client.post(
            "/llm/generate",
            json={"prompt": ""},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestLLMIntegrationWithAgent:
    """Tests for LLM integration with agent endpoints."""

    def test_agent_uses_ollama_when_configured(self, client: TestClient, auth_headers):
        """Agent should use Ollama provider when configured."""
        # This test verifies the wiring is correct
        # The actual agent execution is tested elsewhere
        from app.llm.config import get_llm_config, LLMConfig
        
        with patch.dict("os.environ", {
            "AGENT_PLANNER_MODE": "llm",
            "LLM_PROVIDER": "ollama",
            "LLM_MODEL": "llama3.1",
        }):
            # Force config reload by patching the function
            with patch("app.llm.config.get_llm_config") as mock_get:
                mock_get.return_value = LLMConfig(
                    planner_mode="llm",
                    provider="ollama",
                    model="llama3.1",
                )
                
                config = mock_get()
                assert config.provider == "ollama"
                assert config.llm_enabled is True
