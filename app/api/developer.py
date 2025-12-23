"""
Developer Xone chat endpoint.

Provides /api/developer/chat for a dedicated developer assistant.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm.config import get_llm_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/developer", tags=["developer"])

DEFAULT_DEVELOPER_SYSTEM_PROMPT = (
    "You are Developer Xone, a senior engineering assistant for Elhassan Soussi. "
    "You propose clear plans, ask for approval before executing, and never act autonomously. "
    "Never create bank accounts, payment accounts, or real-world accounts. "
    "Focus on implementation steps, risks, and verification." 
)


class DeveloperChatRequest(BaseModel):
    """Request for developer chat."""
    prompt: str = Field(..., min_length=1, max_length=4096, description="User prompt")
    model: Optional[str] = Field(None, description="Override model")
    timeout: int = Field(120, ge=5, le=600, description="Timeout in seconds")
    system_prompt: Optional[str] = Field(None, max_length=2048, description="Additional system prompt")
    stream: bool = Field(False, description="Enable SSE streaming")


class DeveloperChatResponse(BaseModel):
    """Response for developer chat."""
    status: str
    response: Optional[str]
    error: Optional[str] = None
    provider: str
    model: str


@router.post("/chat", response_model=DeveloperChatResponse)
async def developer_chat(request: DeveloperChatRequest, http_request: Request):
    """
    Developer chat endpoint using Ollama only.

    Returns JSON by default. If stream=true, returns SSE.
    """
    config = get_llm_config()

    if not config.provider:
        raise HTTPException(
            status_code=503,
            detail="No LLM provider configured. Set LLM_PROVIDER environment variable.",
        )

    if config.provider not in ("ollama", "local"):
        raise HTTPException(
            status_code=503,
            detail="Developer chat is available only with Ollama provider.",
        )

    from app.llm.providers.ollama_client import (
        generate_simple_response,
        stream_ollama_response,
        get_ollama_model,
    )

    model = request.model or get_ollama_model(config)
    system_prompt = DEFAULT_DEVELOPER_SYSTEM_PROMPT
    if request.system_prompt:
        system_prompt = f"{system_prompt}\n\nAdditional instructions:\n{request.system_prompt}"

    if request.stream:
        async def event_generator():
            try:
                async for chunk in stream_ollama_response(
                    prompt=request.prompt,
                    model=model,
                    base_url=config.base_url,
                    timeout=request.timeout,
                    system_prompt=system_prompt,
                ):
                    yield f"data: {chunk}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:
                logger.error("Developer stream error: %s", exc)
                yield f"data: [ERROR: {str(exc)}]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    response_text, error = await generate_simple_response(
        prompt=request.prompt,
        model=model,
        base_url=config.base_url,
        timeout=request.timeout,
        system_prompt=system_prompt,
    )

    if error:
        return DeveloperChatResponse(
            status="error",
            response=None,
            error=error,
            provider="ollama",
            model=model,
        )

    return DeveloperChatResponse(
        status="ok",
        response=response_text,
        error=None,
        provider="ollama",
        model=model,
    )
