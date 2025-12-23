"""
LLM client interface and factory.
Provides a unified interface for different LLM providers.
"""
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import ValidationError

from app.llm.config import LLMConfig, get_llm_config
from app.llm.prompts import get_system_prompt, get_user_prompt
from app.llm.schemas import LLMPlan, LLMStep, PlannerResult

logger = logging.getLogger(__name__)

# Patterns for detecting unsafe URLs
PRIVATE_IP_PATTERNS = [
    r"^https?://127\.",
    r"^https?://localhost",
    r"^https?://192\.168\.",
    r"^https?://10\.",
    r"^https?://172\.(1[6-9]|2[0-9]|3[0-1])\.",
    r"^https?://\[::1\]",
    r"^https?://0\.0\.0\.0",
]


class LLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    @abstractmethod
    async def generate_plan(
        self,
        prompt: str,
        allowed_tools: list[str],
        max_steps: int,
    ) -> PlannerResult:
        """Generate an execution plan from a prompt."""
        pass


class RulesClient(LLMClient):
    """Dummy client that always returns fallback to rules."""
    
    async def generate_plan(
        self,
        prompt: str,
        allowed_tools: list[str],
        max_steps: int,
    ) -> PlannerResult:
        return PlannerResult(
            mode="rules",
            plan=None,
            error=None,
            fallback_reason=None,
        )


class LLMProviderClient(LLMClient):
    """Client that calls actual LLM providers."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
    
    async def generate_plan(
        self,
        prompt: str,
        allowed_tools: list[str],
        max_steps: int,
    ) -> PlannerResult:
        """Generate plan using configured LLM provider."""
        
        # Check if LLM is properly configured
        if not self.config.llm_enabled:
            reason = self.config.fallback_reason or "LLM not configured"
            logger.info(f"llm_fallback reason={reason}")
            return PlannerResult(
                mode="llm_fallback",
                plan=None,
                error=None,
                fallback_reason=reason,
            )
        
        # Build prompts
        system_prompt = get_system_prompt(max_steps=max_steps)
        user_prompt = get_user_prompt(
            prompt=prompt,
            allowed_tools=allowed_tools,
            max_steps=max_steps,
        )
        
        # Call the appropriate provider
        response_text, error = await self._call_provider(system_prompt, user_prompt)
        
        if error:
            logger.info(f"llm_fallback reason=provider_error")
            return PlannerResult(
                mode="llm_fallback",
                plan=None,
                error=error,
                fallback_reason=f"LLM error: {error}",
            )
        
        # Parse and validate the response
        return self._parse_response(response_text, allowed_tools, max_steps)
    
    async def _call_provider(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Call the configured LLM provider."""
        
        if self.config.provider == "openai":
            from app.llm.providers.openai_client import call_openai
            return await call_openai(self.config, system_prompt, user_prompt)
        
        elif self.config.provider == "anthropic":
            from app.llm.providers.anthropic_client import call_anthropic
            return await call_anthropic(self.config, system_prompt, user_prompt)
        
        elif self.config.provider == "ollama":
            from app.llm.providers.ollama_client import call_ollama
            return await call_ollama(self.config, system_prompt, user_prompt)
        
        elif self.config.provider == "local":
            # Legacy local provider - same as ollama
            from app.llm.providers.ollama_client import call_ollama
            return await call_ollama(self.config, system_prompt, user_prompt)
        
        else:
            return None, f"Unknown provider: {self.config.provider}"
    
    def _parse_response(
        self,
        response_text: Optional[str],
        allowed_tools: list[str],
        max_steps: int,
    ) -> PlannerResult:
        """Parse and validate LLM response."""
        
        if not response_text:
            return PlannerResult(
                mode="llm_fallback",
                plan=None,
                error="Empty LLM response",
                fallback_reason="Empty response from LLM",
            )
        
        # Try to extract JSON from response (handle markdown code blocks)
        json_text = response_text.strip()
        if json_text.startswith("```"):
            # Remove markdown code block
            lines = json_text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            json_text = "\n".join(json_lines)
        
        # Parse JSON
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning("llm_parse_error type=json")
            return PlannerResult(
                mode="llm_fallback",
                plan=None,
                error=f"Invalid JSON: {str(e)[:100]}",
                fallback_reason="LLM returned invalid JSON",
            )
        
        # Validate with Pydantic
        try:
            plan = LLMPlan.model_validate(data)
        except ValidationError as e:
            logger.warning("llm_parse_error type=validation")
            return PlannerResult(
                mode="llm_fallback",
                plan=None,
                error=f"Validation error: {str(e)[:200]}",
                fallback_reason="LLM plan failed validation",
            )
        
        # Security validation: check all steps
        for step in plan.steps:
            # Check tool is allowed
            if step.tool not in allowed_tools:
                logger.warning(f"llm_security tool={step.tool} rejected=not_allowed")
                return PlannerResult(
                    mode="llm_fallback",
                    plan=None,
                    error=f"Disallowed tool: {step.tool}",
                    fallback_reason=f"LLM suggested disallowed tool: {step.tool}",
                )
            
            # Check http_fetch URLs
            if step.tool == "http_fetch":
                url = step.input.get("url", "")
                
                # Must be HTTPS
                if not url.startswith("https://"):
                    logger.warning("llm_security rejected=non_https")
                    return PlannerResult(
                        mode="llm_fallback",
                        plan=None,
                        error="http_fetch requires https:// URL",
                        fallback_reason="LLM suggested non-HTTPS URL",
                    )
                
                # Check for private/local networks
                for pattern in PRIVATE_IP_PATTERNS:
                    if re.match(pattern, url, re.IGNORECASE):
                        logger.warning("llm_security rejected=private_network")
                        return PlannerResult(
                            mode="llm_fallback",
                            plan=None,
                            error="Cannot access private/local networks",
                            fallback_reason="LLM suggested private network access",
                        )
        
        # Check step count
        if len(plan.steps) > max_steps:
            logger.warning(f"llm_security rejected=too_many_steps count={len(plan.steps)}")
            return PlannerResult(
                mode="llm_fallback",
                plan=None,
                error=f"Too many steps: {len(plan.steps)} > {max_steps}",
                fallback_reason="LLM plan has too many steps",
            )
        
        logger.info(f"llm_plan_valid steps={len(plan.steps)}")
        return PlannerResult(
            mode="llm",
            plan=plan,
            error=None,
            fallback_reason=None,
        )


def get_llm_client() -> LLMClient:
    """Factory function to get the appropriate LLM client."""
    config = get_llm_config()
    
    if config.planner_mode == "rules":
        return RulesClient()
    
    return LLMProviderClient(config)
