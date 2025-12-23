"""
Tests for Ollama LLM provider.

All tests mock HTTP calls - no network access.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from app.llm.config import LLMConfig
from app.llm.providers.ollama_client import (
    call_ollama,
    check_ollama_health,
    generate_simple_response,
    get_ollama_base_url,
    get_ollama_model,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
)


class TestOllamaConfig:
    """Tests for Ollama configuration."""

    def test_default_base_url(self):
        """Default Ollama URL should be localhost:11434."""
        with patch.dict("os.environ", {}, clear=True):
            url = get_ollama_base_url()
            assert url == DEFAULT_OLLAMA_BASE_URL
            assert "127.0.0.1:11434" in url

    def test_custom_base_url(self):
        """LLM_BASE_URL env should override default."""
        with patch.dict("os.environ", {"LLM_BASE_URL": "http://myserver:11434"}):
            url = get_ollama_base_url()
            assert url == "http://myserver:11434"

    def test_base_url_strips_trailing_slash(self):
        """Base URL should strip trailing slash."""
        with patch.dict("os.environ", {"LLM_BASE_URL": "http://localhost:11434/"}):
            url = get_ollama_base_url()
            assert not url.endswith("/")

    def test_default_model(self):
        """Default model should be llama3.1."""
        config = LLMConfig()
        model = get_ollama_model(config)
        assert model == DEFAULT_OLLAMA_MODEL

    def test_config_model_override(self):
        """Config model should override default."""
        config = LLMConfig(model="mistral")
        model = get_ollama_model(config)
        assert model == "mistral"


class TestCallOllama:
    """Tests for call_ollama function."""

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Successful Ollama call should return response text."""
        config = LLMConfig(provider="ollama", timeout_s=30)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "role": "assistant",
                "content": '{"goal": "test", "steps": []}'
            }
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            result, error = await call_ollama(config, "system", "user")
            
            assert error is None
            assert result == '{"goal": "test", "steps": []}'

    @pytest.mark.asyncio
    async def test_api_error(self):
        """API error should return error message."""
        config = LLMConfig(provider="ollama", timeout_s=30)
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            result, error = await call_ollama(config, "system", "user")
            
            assert result is None
            assert "500" in error
            assert "Ollama API error" in error

    @pytest.mark.asyncio
    async def test_empty_response(self):
        """Empty response should return error."""
        config = LLMConfig(provider="ollama", timeout_s=30)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": ""}}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            result, error = await call_ollama(config, "system", "user")
            
            assert result is None
            assert "Empty response" in error

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Timeout should return appropriate error."""
        import httpx
        
        config = LLMConfig(provider="ollama", timeout_s=1)
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = httpx.TimeoutException("timeout")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            result, error = await call_ollama(config, "system", "user")
            
            assert result is None
            assert "timeout" in error.lower()

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Connection error should return helpful message."""
        import httpx
        
        config = LLMConfig(provider="ollama", timeout_s=30)
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = httpx.ConnectError("connection refused")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            result, error = await call_ollama(config, "system", "user")
            
            assert result is None
            assert "Cannot connect" in error
            assert "Ollama running" in error


class TestCheckOllamaHealth:
    """Tests for check_ollama_health function."""

    @pytest.mark.asyncio
    async def test_healthy_with_models(self):
        """Healthy Ollama should return ok with model list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.1"},
                {"name": "mistral"},
            ]
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            is_healthy, message = await check_ollama_health()
            
            assert is_healthy is True
            assert "running" in message.lower()
            assert "llama3.1" in message

    @pytest.mark.asyncio
    async def test_healthy_no_models(self):
        """Ollama with no models should still be healthy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            is_healthy, message = await check_ollama_health()
            
            assert is_healthy is True
            assert "none" in message.lower()

    @pytest.mark.asyncio
    async def test_connection_refused(self):
        """Connection refused should return unhealthy."""
        import httpx
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = httpx.ConnectError("refused")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            is_healthy, message = await check_ollama_health()
            
            assert is_healthy is False
            assert "Cannot connect" in message


class TestGenerateSimpleResponse:
    """Tests for generate_simple_response function."""

    @pytest.mark.asyncio
    async def test_successful_generation(self):
        """Successful generation should return text."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Hello! I'm here to help."
            }
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            result, error = await generate_simple_response("Hello")
            
            assert error is None
            assert result == "Hello! I'm here to help."

    @pytest.mark.asyncio
    async def test_custom_model(self):
        """Custom model parameter should be used."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "response"}
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            await generate_simple_response("test", model="mistral")
            
            # Check that the model was passed correctly
            call_args = mock_instance.post.call_args
            payload = call_args.kwargs.get("json", {})
            assert payload.get("model") == "mistral"


class TestLLMConfigOllama:
    """Tests for LLMConfig with Ollama provider."""

    def test_ollama_enabled_without_api_key(self):
        """Ollama should be enabled without API key."""
        config = LLMConfig(
            planner_mode="llm",
            provider="ollama",
            api_key=None,
        )
        assert config.llm_enabled is True

    def test_ollama_fallback_reason_none(self):
        """Ollama should have no fallback reason when configured."""
        config = LLMConfig(
            planner_mode="llm",
            provider="ollama",
        )
        assert config.fallback_reason is None

    def test_openai_requires_api_key(self):
        """OpenAI should require API key."""
        config = LLMConfig(
            planner_mode="llm",
            provider="openai",
            api_key=None,
        )
        assert config.llm_enabled is False
        assert "API_KEY" in config.fallback_reason
