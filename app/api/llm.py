"""
LLM API routes for health checks, direct generation, and streaming.
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm.config import get_llm_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])

# Default system prompt for Xone identity
DEFAULT_SYSTEM_PROMPT = os.environ.get(
    "AGENT_SYSTEM_PROMPT_DEFAULT",
    "You are Xone, an AI assistant created by Elhassan Soussi. When asked about your name or who you are, always respond that your name is 'Xone by Elhassan Soussi'. Be concise, accurate, and helpful."
)


class LLMHealthResponse(BaseModel):
    """Response for LLM health check."""
    status: str = Field(..., description="ok or error")
    provider: Optional[str] = Field(None, description="Configured LLM provider")
    model: Optional[str] = Field(None, description="Configured model")
    base_url: Optional[str] = Field(None, description="Base URL (for Ollama)")
    message: str = Field(..., description="Status message")
    planner_mode: str = Field(..., description="Current planner mode")


class GenerateRequest(BaseModel):
    """Request for direct LLM generation."""
    prompt: str = Field(..., min_length=1, max_length=4096, description="User prompt")
    model: Optional[str] = Field(None, description="Override model")
    timeout: int = Field(60, ge=5, le=300, description="Timeout in seconds")
    system_prompt: Optional[str] = Field(None, max_length=2048, description="Custom system prompt")


class GenerateResponse(BaseModel):
    """Response from direct LLM generation."""
    status: str = Field(..., description="ok or error")
    response: Optional[str] = Field(None, description="LLM response text")
    error: Optional[str] = Field(None, description="Error message if failed")
    provider: str = Field(..., description="Provider used")
    model: str = Field(..., description="Model used")


@router.get("/health", response_model=LLMHealthResponse)
async def llm_health() -> LLMHealthResponse:
    """
    Check LLM service health.
    
    For Ollama, attempts to connect and list models.
    For cloud providers (OpenAI, Anthropic), just checks configuration.
    
    This endpoint is public (no auth required) for monitoring.
    """
    config = get_llm_config()
    
    # Check if any LLM is configured
    if not config.provider:
        return LLMHealthResponse(
            status="not_configured",
            provider=None,
            model=None,
            base_url=None,
            message="No LLM provider configured. Set LLM_PROVIDER environment variable.",
            planner_mode=config.planner_mode,
        )
    
    # For Ollama, actually check the connection
    if config.provider == "ollama":
        from app.llm.providers.ollama_client import check_ollama_health, get_ollama_base_url, get_ollama_model
        
        base_url = config.base_url or get_ollama_base_url()
        model = get_ollama_model(config)
        
        is_healthy, message = await check_ollama_health(base_url)
        
        return LLMHealthResponse(
            status="ok" if is_healthy else "error",
            provider="ollama",
            model=model,
            base_url=base_url,
            message=message,
            planner_mode=config.planner_mode,
        )
    
    # For cloud providers, just check config
    if config.provider == "openai":
        has_key = bool(config.api_key)
        return LLMHealthResponse(
            status="ok" if has_key else "error",
            provider="openai",
            model=config.model or "gpt-4o-mini",
            base_url=None,
            message="OpenAI configured" if has_key else "OpenAI API key not set",
            planner_mode=config.planner_mode,
        )
    
    if config.provider == "anthropic":
        has_key = bool(config.api_key)
        return LLMHealthResponse(
            status="ok" if has_key else "error",
            provider="anthropic",
            model=config.model or "claude-3-haiku-20240307",
            base_url=None,
            message="Anthropic configured" if has_key else "Anthropic API key not set",
            planner_mode=config.planner_mode,
        )
    
    return LLMHealthResponse(
        status="error",
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        message=f"Unknown provider: {config.provider}",
        planner_mode=config.planner_mode,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_text(request: GenerateRequest, http_request: Request) -> GenerateResponse:
    """
    Direct LLM text generation (for chat responses).
    
    Bypasses the planning system for simple chat-like interactions.
    Uses the configured LLM provider.
    
    Requires authentication.
    """
    config = get_llm_config()
    
    if not config.provider:
        raise HTTPException(
            status_code=503,
            detail="No LLM provider configured. Set LLM_PROVIDER environment variable."
        )
    
    # For Ollama - NEVER call OpenAI when provider is ollama
    if config.provider in ("ollama", "local"):
        from app.llm.providers.ollama_client import generate_simple_response, get_ollama_model
        
        model = request.model or get_ollama_model(config)
        # Use provided system prompt or default Xone identity
        system_prompt = request.system_prompt or DEFAULT_SYSTEM_PROMPT
        
        response_text, error = await generate_simple_response(
            prompt=request.prompt,
            model=model,
            base_url=config.base_url,
            timeout=request.timeout,
            system_prompt=system_prompt,
        )
        
        if error:
            return GenerateResponse(
                status="error",
                response=None,
                error=error,
                provider="ollama",
                model=model,
            )
        
        return GenerateResponse(
            status="ok",
            response=response_text,
            error=None,
            provider="ollama",
            model=model,
        )
    
    # For OpenAI - only if explicitly configured
    if config.provider == "openai":
        if not config.api_key:
            raise HTTPException(status_code=503, detail="OpenAI API key not configured")
        
        from app.llm.providers.openai_client import call_openai
        
        model = request.model or config.model or "gpt-4o-mini"
        system_prompt = request.system_prompt or DEFAULT_SYSTEM_PROMPT
        
        response_text, error = await call_openai(config, system_prompt, request.prompt)
        
        if error:
            return GenerateResponse(
                status="error",
                response=None,
                error=error,
                provider="openai",
                model=model,
            )
        
        return GenerateResponse(
            status="ok",
            response=response_text,
            error=None,
            provider="openai",
            model=model,
        )
    
    # For Anthropic - only if explicitly configured
    if config.provider == "anthropic":
        if not config.api_key:
            raise HTTPException(status_code=503, detail="Anthropic API key not configured")
        
        from app.llm.providers.anthropic_client import call_anthropic
        
        model = request.model or config.model or "claude-3-haiku-20240307"
        system_prompt = request.system_prompt or "You are a helpful AI assistant. Be concise and helpful."
        
        response_text, error = await call_anthropic(config, system_prompt, request.prompt)
        
        if error:
            return GenerateResponse(
                status="error",
                response=None,
                error=error,
                provider="anthropic",
                model=model,
            )
        
        return GenerateResponse(
            status="ok",
            response=response_text,
            error=None,
            provider="anthropic",
            model=model,
        )
    
    raise HTTPException(status_code=503, detail=f"Unknown LLM provider: {config.provider}")


class StreamRequest(BaseModel):
    """Request for streaming LLM generation."""
    prompt: str = Field(..., min_length=1, max_length=4096, description="User prompt")
    model: Optional[str] = Field(None, description="Override model")
    timeout: int = Field(120, ge=5, le=600, description="Timeout in seconds")
    system_prompt: Optional[str] = Field(None, max_length=2048, description="Custom system prompt")


@router.post("/stream")
async def stream_text(request: StreamRequest, http_request: Request) -> StreamingResponse:
    """
    Stream LLM text generation via Server-Sent Events (SSE).
    
    Only supported for Ollama provider currently.
    Streams tokens as they are generated for real-time UI updates.
    
    Requires authentication.
    """
    config = get_llm_config()
    
    if not config.provider:
        raise HTTPException(
            status_code=503,
            detail="No LLM provider configured. Set LLM_PROVIDER environment variable."
        )
    
    # Currently only Ollama supports streaming
    if config.provider not in ("ollama", "local"):
        raise HTTPException(
            status_code=400,
            detail=f"Streaming not supported for provider: {config.provider}. Use /llm/generate instead."
        )
    
    from app.llm.providers.ollama_client import stream_ollama_response, get_ollama_model
    
    model = request.model or get_ollama_model(config)
    # Use provided system prompt or default Xone identity
    system_prompt = request.system_prompt or DEFAULT_SYSTEM_PROMPT
    
    async def event_generator():
        """Generate SSE events from Ollama stream."""
        try:
            async for chunk in stream_ollama_response(
                prompt=request.prompt,
                model=model,
                base_url=config.base_url,
                timeout=request.timeout,
                system_prompt=system_prompt,
            ):
                # SSE format: data: <content>\n\n
                yield f"data: {chunk}\n\n"
            
            # Send done event
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: [ERROR: {str(e)}]\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
