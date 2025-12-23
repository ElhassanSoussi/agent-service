"""
Ollama API client for local LLM inference.
Connects to a self-hosted Ollama instance.
"""
import json
import logging
import os
from typing import AsyncGenerator, Optional

import httpx

from app.llm.config import LLMConfig

logger = logging.getLogger(__name__)

# Default Ollama configuration
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1"


def get_ollama_base_url() -> str:
    """Get Ollama base URL from environment or use default."""
    return os.getenv("LLM_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")


def get_ollama_model(config: LLMConfig) -> str:
    """Get Ollama model from config or environment."""
    return config.model or os.getenv("LLM_MODEL", DEFAULT_OLLAMA_MODEL)


async def call_ollama(
    config: LLMConfig,
    system_prompt: str,
    user_prompt: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Call Ollama API for plan generation.
    
    Uses the /api/chat endpoint for chat-style completions.
    
    Returns:
        (response_text, error_message)
        - On success: (response_string, None)
        - On failure: (None, error_description)
    
    NEVER logs prompts or full responses (privacy).
    """
    base_url = get_ollama_base_url()
    model = get_ollama_model(config)
    
    # Build the chat request
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,  # Low temperature for consistent JSON
            "num_predict": config.max_tokens,
        },
    }
    
    try:
        async with httpx.AsyncClient(timeout=config.timeout_s) as client:
            logger.info(f"llm_call provider=ollama model={model} base_url={base_url}")
            
            response = await client.post(
                f"{base_url}/api/chat",
                json=payload,
            )
            
            if response.status_code != 200:
                error_text = response.text[:200] if response.text else "No response"
                logger.warning(f"llm_error provider=ollama status={response.status_code}")
                return None, f"Ollama API error: status {response.status_code} - {error_text}"
            
            data = response.json()
            
            # Extract the assistant's message content
            content = data.get("message", {}).get("content", "")
            
            if not content:
                return None, "Empty response from Ollama"
            
            logger.info("llm_success provider=ollama")
            return content, None
            
    except httpx.TimeoutException:
        logger.warning(f"llm_timeout provider=ollama timeout={config.timeout_s}s")
        return None, f"Ollama API timeout after {config.timeout_s}s"
    except httpx.ConnectError:
        logger.warning(f"llm_connect_error provider=ollama url={base_url}")
        return None, f"Cannot connect to Ollama at {base_url}. Is Ollama running?"
    except httpx.RequestError as e:
        logger.warning(f"llm_network_error provider=ollama error_type={type(e).__name__}")
        return None, f"Network error connecting to Ollama: {type(e).__name__}"
    except json.JSONDecodeError:
        logger.warning("llm_json_error provider=ollama")
        return None, "Invalid JSON response from Ollama"
    except Exception as e:
        logger.warning(f"llm_error provider=ollama error_type={type(e).__name__}")
        return None, f"Unexpected error: {type(e).__name__}"


async def check_ollama_health(base_url: Optional[str] = None) -> tuple[bool, str]:
    """
    Check if Ollama is running and responsive.
    
    Returns:
        (is_healthy, message)
    """
    url = (base_url or get_ollama_base_url()).rstrip("/")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Ollama exposes a simple endpoint at /api/tags to list models
            response = await client.get(f"{url}/api/tags")
            
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "unknown") for m in data.get("models", [])]
                model_count = len(models)
                model_list = ", ".join(models[:5])
                if model_count > 5:
                    model_list += f", ... ({model_count - 5} more)"
                return True, f"Ollama is running. Models available: {model_list or 'none'}"
            else:
                return False, f"Ollama responded with status {response.status_code}"
                
    except httpx.ConnectError:
        return False, f"Cannot connect to Ollama at {url}"
    except httpx.TimeoutException:
        return False, f"Timeout connecting to Ollama at {url}"
    except Exception as e:
        return False, f"Error checking Ollama: {type(e).__name__}"


async def generate_simple_response(
    prompt: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 60,
    system_prompt: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Simple generation endpoint for direct text responses.
    
    This bypasses the planning system for simple chat-like interactions.
    
    Returns:
        (response_text, error_message)
    """
    url = (base_url or get_ollama_base_url()).rstrip("/")
    model_name = model or os.getenv("LLM_MODEL", DEFAULT_OLLAMA_MODEL)
    
    # Use provided system prompt or default
    sys_prompt = system_prompt or "You are a helpful AI assistant. Be concise and helpful."
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 1024,
        },
    }
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            logger.info(f"llm_generate provider=ollama model={model_name}")
            
            response = await client.post(
                f"{url}/api/chat",
                json=payload,
            )
            
            if response.status_code != 200:
                return None, f"Ollama error: status {response.status_code}"
            
            data = response.json()
            content = data.get("message", {}).get("content", "")
            
            if not content:
                return None, "Empty response from Ollama"
            
            return content, None
            
    except httpx.TimeoutException:
        return None, f"Ollama timeout after {timeout}s"
    except httpx.ConnectError:
        return None, f"Cannot connect to Ollama at {url}. Is Ollama running?"
    except Exception as e:
        return None, f"Ollama error: {type(e).__name__}"


async def stream_ollama_response(
    prompt: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 120,
    system_prompt: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream response tokens from Ollama.
    
    Yields individual tokens/chunks as they arrive.
    Used for SSE streaming in the chat UI.
    """
    url = (base_url or get_ollama_base_url()).rstrip("/")
    model_name = model or os.getenv("LLM_MODEL", DEFAULT_OLLAMA_MODEL)
    
    # Use provided system prompt or default
    sys_prompt = system_prompt or "You are a helpful AI assistant. Be concise and helpful."
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_predict": 1024,
        },
    }
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            logger.info(f"llm_stream_start provider=ollama model={model_name}")
            
            async with client.stream(
                "POST",
                f"{url}/api/chat",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    yield f"[Error: Ollama status {response.status_code}]"
                    return
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        # Check if stream is done
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
            
            logger.info("llm_stream_complete provider=ollama")
            
    except httpx.TimeoutException:
        yield f"[Error: Timeout after {timeout}s]"
    except httpx.ConnectError:
        yield f"[Error: Cannot connect to Ollama at {url}]"
    except Exception as e:
        yield f"[Error: {type(e).__name__}]"
