"""
Pydantic schemas for LLM plan output.
Strict validation to prevent prompt injection attacks.
"""
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


class LLMStep(BaseModel):
    """A single step in an LLM-generated plan."""
    id: int = Field(..., ge=1, le=100)
    tool: Literal["echo", "http_fetch"] = Field(..., description="Tool to execute")
    input: dict[str, Any] = Field(..., description="Tool input parameters")
    why: str = Field(..., max_length=500, description="Reason for this step")
    
    @field_validator("input")
    @classmethod
    def validate_input(cls, v: dict, info) -> dict:
        """Validate input based on tool type."""
        # This is a basic check; full validation happens in executor
        return v


class LLMPlan(BaseModel):
    """Complete plan from LLM."""
    goal: str = Field(..., max_length=1000, description="High-level goal")
    steps: list[LLMStep] = Field(..., min_length=1, description="Steps to execute")
    
    @field_validator("steps")
    @classmethod
    def validate_steps_limit(cls, v: list) -> list:
        """Ensure steps don't exceed maximum."""
        from app.llm.config import get_llm_config
        config = get_llm_config()
        if len(v) > config.max_plan_steps:
            raise ValueError(f"Too many steps: {len(v)} > {config.max_plan_steps}")
        return v


class PlannerResult(BaseModel):
    """Result from the planner (rules or LLM)."""
    mode: Literal["rules", "llm", "llm_fallback"] = Field(..., description="Planner mode used")
    plan: LLMPlan | None = Field(None, description="Parsed plan if successful")
    error: str | None = Field(None, description="Error message if failed")
    fallback_reason: str | None = Field(None, description="Why fallback was triggered")
