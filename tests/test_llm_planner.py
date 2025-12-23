"""
Tests for LLM planner functionality.
Uses mocks to avoid real LLM calls.
"""
import json
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Set test environment before imports
os.environ["AGENT_API_KEY"] = "test-api-key-12345"


class TestPlannerModeSelection:
    """Tests for planner mode selection based on environment."""
    
    def test_default_mode_is_rules(self):
        """Default planner mode should be rules."""
        # Clear any LLM env vars
        env_backup = {}
        for key in ["AGENT_PLANNER_MODE", "LLM_PROVIDER", "LLM_API_KEY"]:
            env_backup[key] = os.environ.pop(key, None)
        
        try:
            # Reimport to get fresh config
            from app.llm.config import get_llm_config
            config = get_llm_config()
            assert config.planner_mode == "rules"
            assert not config.llm_enabled
        finally:
            # Restore env vars
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value
    
    def test_llm_mode_without_provider_falls_back(self):
        """LLM mode without provider should fall back."""
        os.environ["AGENT_PLANNER_MODE"] = "llm"
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("LLM_API_KEY", None)
        
        try:
            from app.llm.config import get_llm_config
            config = get_llm_config()
            assert config.planner_mode == "llm"
            assert not config.llm_enabled
            assert config.fallback_reason == "LLM_PROVIDER not set"
        finally:
            os.environ.pop("AGENT_PLANNER_MODE", None)
    
    def test_llm_mode_without_api_key_falls_back(self):
        """LLM mode without API key should fall back."""
        os.environ["AGENT_PLANNER_MODE"] = "llm"
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ.pop("LLM_API_KEY", None)
        
        try:
            from app.llm.config import get_llm_config
            config = get_llm_config()
            assert config.planner_mode == "llm"
            assert not config.llm_enabled
            assert config.fallback_reason == "LLM_API_KEY not set"
        finally:
            os.environ.pop("AGENT_PLANNER_MODE", None)
            os.environ.pop("LLM_PROVIDER", None)


class TestLLMPlanValidation:
    """Tests for LLM plan validation."""
    
    def test_valid_plan_parses_correctly(self):
        """Valid LLM plan should parse correctly."""
        from app.llm.schemas import LLMPlan
        
        data = {
            "goal": "Fetch example.com",
            "steps": [
                {
                    "id": 1,
                    "tool": "http_fetch",
                    "input": {"url": "https://example.com"},
                    "why": "Fetch the page"
                }
            ]
        }
        
        plan = LLMPlan.model_validate(data)
        assert plan.goal == "Fetch example.com"
        assert len(plan.steps) == 1
        assert plan.steps[0].tool == "http_fetch"
    
    def test_invalid_tool_rejected(self):
        """Plan with invalid tool should be rejected."""
        from app.llm.schemas import LLMPlan
        from pydantic import ValidationError
        
        data = {
            "goal": "Do something",
            "steps": [
                {
                    "id": 1,
                    "tool": "shell_exec",  # Invalid tool
                    "input": {"command": "ls"},
                    "why": "List files"
                }
            ]
        }
        
        with pytest.raises(ValidationError):
            LLMPlan.model_validate(data)
    
    def test_empty_steps_rejected(self):
        """Plan with empty steps should be rejected."""
        from app.llm.schemas import LLMPlan
        from pydantic import ValidationError
        
        data = {
            "goal": "Do nothing",
            "steps": []
        }
        
        with pytest.raises(ValidationError):
            LLMPlan.model_validate(data)


class TestLLMClientValidation:
    """Tests for LLM client security validation."""
    
    @pytest.mark.asyncio
    async def test_http_url_rejected(self):
        """http:// URLs should be rejected."""
        from app.llm.client import LLMProviderClient
        from app.llm.config import LLMConfig
        
        config = LLMConfig(
            planner_mode="llm",
            provider="openai",
            api_key="test-key",
        )
        client = LLMProviderClient(config)
        
        # Mock response with http:// URL
        response_json = json.dumps({
            "goal": "Fetch insecure URL",
            "steps": [
                {
                    "id": 1,
                    "tool": "http_fetch",
                    "input": {"url": "http://example.com"},  # http:// not https://
                    "why": "Fetch"
                }
            ]
        })
        
        result = client._parse_response(response_json, ["http_fetch"], 6)
        
        assert result.mode == "llm_fallback"
        assert "https://" in result.fallback_reason.lower() or "non-https" in result.fallback_reason.lower()
    
    @pytest.mark.asyncio
    async def test_localhost_rejected(self):
        """localhost URLs should be rejected."""
        from app.llm.client import LLMProviderClient
        from app.llm.config import LLMConfig
        
        config = LLMConfig(
            planner_mode="llm",
            provider="openai",
            api_key="test-key",
        )
        client = LLMProviderClient(config)
        
        # Mock response with localhost URL
        response_json = json.dumps({
            "goal": "Access localhost",
            "steps": [
                {
                    "id": 1,
                    "tool": "http_fetch",
                    "input": {"url": "https://localhost/secret"},
                    "why": "Access local"
                }
            ]
        })
        
        result = client._parse_response(response_json, ["http_fetch"], 6)
        
        assert result.mode == "llm_fallback"
        assert "private" in result.fallback_reason.lower()
    
    @pytest.mark.asyncio
    async def test_private_ip_rejected(self):
        """Private IP URLs should be rejected."""
        from app.llm.client import LLMProviderClient
        from app.llm.config import LLMConfig
        
        config = LLMConfig(
            planner_mode="llm",
            provider="openai",
            api_key="test-key",
        )
        client = LLMProviderClient(config)
        
        # Test various private IPs
        private_urls = [
            "https://192.168.1.1/admin",
            "https://10.0.0.1/internal",
            "https://172.16.0.1/private",
            "https://127.0.0.1/local",
        ]
        
        for url in private_urls:
            response_json = json.dumps({
                "goal": "Access private network",
                "steps": [
                    {
                        "id": 1,
                        "tool": "http_fetch",
                        "input": {"url": url},
                        "why": "Access"
                    }
                ]
            })
            
            result = client._parse_response(response_json, ["http_fetch"], 6)
            assert result.mode == "llm_fallback", f"Should reject {url}"
    
    @pytest.mark.asyncio
    async def test_disallowed_tool_rejected(self):
        """Tools not in allowed list should be rejected."""
        from app.llm.client import LLMProviderClient
        from app.llm.config import LLMConfig
        
        config = LLMConfig(
            planner_mode="llm",
            provider="openai",
            api_key="test-key",
        )
        client = LLMProviderClient(config)
        
        response_json = json.dumps({
            "goal": "Use http_fetch",
            "steps": [
                {
                    "id": 1,
                    "tool": "http_fetch",
                    "input": {"url": "https://example.com"},
                    "why": "Fetch"
                }
            ]
        })
        
        # Only allow echo, not http_fetch
        result = client._parse_response(response_json, ["echo"], 6)
        
        assert result.mode == "llm_fallback"
        assert "disallowed" in result.fallback_reason.lower()
    
    @pytest.mark.asyncio
    async def test_valid_plan_accepted(self):
        """Valid plan should be accepted."""
        from app.llm.client import LLMProviderClient
        from app.llm.config import LLMConfig
        
        config = LLMConfig(
            planner_mode="llm",
            provider="openai",
            api_key="test-key",
        )
        client = LLMProviderClient(config)
        
        response_json = json.dumps({
            "goal": "Fetch example.com",
            "steps": [
                {
                    "id": 1,
                    "tool": "http_fetch",
                    "input": {"url": "https://example.com"},
                    "why": "Fetch the page"
                }
            ]
        })
        
        result = client._parse_response(response_json, ["echo", "http_fetch"], 6)
        
        assert result.mode == "llm"
        assert result.plan is not None
        assert len(result.plan.steps) == 1
    
    @pytest.mark.asyncio
    async def test_invalid_json_falls_back(self):
        """Invalid JSON should trigger fallback."""
        from app.llm.client import LLMProviderClient
        from app.llm.config import LLMConfig
        
        config = LLMConfig(
            planner_mode="llm",
            provider="openai",
            api_key="test-key",
        )
        client = LLMProviderClient(config)
        
        result = client._parse_response("not valid json {{{", ["echo"], 6)
        
        assert result.mode == "llm_fallback"
        assert "json" in result.fallback_reason.lower()


class TestRulesPlanner:
    """Tests for rule-based planner."""
    
    @pytest.mark.asyncio
    async def test_rules_planner_with_url(self):
        """Rules planner should detect URLs."""
        # Ensure rules mode
        os.environ.pop("AGENT_PLANNER_MODE", None)
        
        from app.core.planner import create_plan_async
        
        plan, metadata = await create_plan_async(
            prompt="fetch https://example.com",
            allowed_tools=["echo", "http_fetch"],
            max_steps=3,
        )
        
        assert metadata.mode == "rules"
        assert len(plan.steps) >= 1
        assert plan.steps[0].tool == "http_fetch"
    
    @pytest.mark.asyncio
    async def test_rules_planner_with_echo(self):
        """Rules planner should handle echo requests."""
        os.environ.pop("AGENT_PLANNER_MODE", None)
        
        from app.core.planner import create_plan_async
        
        plan, metadata = await create_plan_async(
            prompt="echo hello world",
            allowed_tools=["echo", "http_fetch"],
            max_steps=3,
        )
        
        assert metadata.mode == "rules"
        assert len(plan.steps) >= 1
        assert plan.steps[0].tool == "echo"


class TestIntegrationWithMockedLLM:
    """Integration tests with mocked LLM provider."""
    
    @pytest.mark.asyncio
    async def test_llm_planner_with_mock(self):
        """Test LLM planner with mocked provider call."""
        # Set up LLM mode
        os.environ["AGENT_PLANNER_MODE"] = "llm"
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["LLM_API_KEY"] = "fake-key"
        
        try:
            from app.llm.client import LLMProviderClient
            from app.llm.config import get_llm_config
            
            config = get_llm_config()
            client = LLMProviderClient(config)
            
            # Mock the provider call
            mock_response = json.dumps({
                "goal": "Echo a greeting",
                "steps": [
                    {
                        "id": 1,
                        "tool": "echo",
                        "input": {"message": "Hello from LLM!"},
                        "why": "Respond to user"
                    }
                ]
            })
            
            with patch.object(client, '_call_provider', new_callable=AsyncMock) as mock_call:
                mock_call.return_value = (mock_response, None)
                
                result = await client.generate_plan(
                    prompt="say hello",
                    allowed_tools=["echo", "http_fetch"],
                    max_steps=3,
                )
                
                assert result.mode == "llm"
                assert result.plan is not None
                assert len(result.plan.steps) == 1
                assert result.plan.steps[0].tool == "echo"
        finally:
            os.environ.pop("AGENT_PLANNER_MODE", None)
            os.environ.pop("LLM_PROVIDER", None)
            os.environ.pop("LLM_API_KEY", None)
    
    @pytest.mark.asyncio
    async def test_llm_timeout_falls_back(self):
        """LLM timeout should fall back to rules."""
        os.environ["AGENT_PLANNER_MODE"] = "llm"
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["LLM_API_KEY"] = "fake-key"
        
        try:
            from app.llm.client import LLMProviderClient
            from app.llm.config import get_llm_config
            
            config = get_llm_config()
            client = LLMProviderClient(config)
            
            # Mock timeout error
            with patch.object(client, '_call_provider', new_callable=AsyncMock) as mock_call:
                mock_call.return_value = (None, "OpenAI API timeout")
                
                result = await client.generate_plan(
                    prompt="fetch https://example.com",
                    allowed_tools=["echo", "http_fetch"],
                    max_steps=3,
                )
                
                assert result.mode == "llm_fallback"
                assert "timeout" in result.fallback_reason.lower()
        finally:
            os.environ.pop("AGENT_PLANNER_MODE", None)
            os.environ.pop("LLM_PROVIDER", None)
            os.environ.pop("LLM_API_KEY", None)
