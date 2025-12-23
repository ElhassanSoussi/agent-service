"""
LLM configuration from environment variables.
All settings are optional with safe defaults.
"""
import os
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class LLMConfig:
    """LLM configuration (immutable)."""
    planner_mode: Literal["rules", "llm"] = "rules"
    provider: Optional[Literal["openai", "anthropic", "ollama", "local"]] = None
    api_key: Optional[str] = None  # Never logged
    model: Optional[str] = None
    base_url: Optional[str] = None  # For Ollama: http://127.0.0.1:11434
    max_tokens: int = 500
    timeout_s: int = 20
    max_plan_steps: int = 6
    
    @property
    def llm_enabled(self) -> bool:
        """Check if LLM mode is properly configured."""
        if self.planner_mode != "llm":
            return False
        if not self.provider:
            return False
        # Local providers (ollama, local) don't need API key
        if self.provider in ("local", "ollama"):
            return True
        return bool(self.api_key)
    
    @property
    def fallback_reason(self) -> Optional[str]:
        """Get reason why LLM is not enabled."""
        if self.planner_mode != "llm":
            return None  # Not requested
        if not self.provider:
            return "LLM_PROVIDER not set"
        if self.provider not in ("local", "ollama") and not self.api_key:
            return "LLM_API_KEY not set"
        return None


def get_llm_config() -> LLMConfig:
    """Load LLM configuration from environment."""
    planner_mode = os.getenv("AGENT_PLANNER_MODE", "rules").lower()
    if planner_mode not in ("rules", "llm"):
        planner_mode = "rules"
    
    provider = os.getenv("LLM_PROVIDER", "").lower() or None
    if provider and provider not in ("openai", "anthropic", "ollama", "local"):
        provider = None
    
    return LLMConfig(
        planner_mode=planner_mode,  # type: ignore
        provider=provider,  # type: ignore
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL"),
        base_url=os.getenv("LLM_BASE_URL"),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "500")),
        timeout_s=int(os.getenv("LLM_TIMEOUT_S", "20")),
        max_plan_steps=int(os.getenv("LLM_MAX_PLAN_STEPS", "6")),
    )
