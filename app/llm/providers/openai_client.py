"""
OpenAI API client using httpx.
Minimal implementation - no heavy dependencies.
"""
import json
import logging
from typing import Optional

import httpx

from app.llm.config import LLMConfig

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"


async def call_openai(
    config: LLMConfig,
    system_prompt: str,
    user_prompt: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Call OpenAI API for plan generation.
    
    Returns:
        (response_text, error_message)
        - On success: (json_string, None)
        - On failure: (None, error_description)
    
    NEVER logs API key or request bodies.
    """
    if not config.api_key:
        return None, "OpenAI API key not configured"
    
    model = config.model or DEFAULT_MODEL
    
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": config.max_tokens,
        "temperature": 0.1,  # Low temperature for consistent JSON
        "response_format": {"type": "json_object"},
    }
    
    try:
        async with httpx.AsyncClient(timeout=config.timeout_s) as client:
            # Log only that we're making a call, not the content
            logger.info(f"llm_call provider=openai model={model}")
            
            response = await client.post(
                OPENAI_API_URL,
                headers=headers,
                json=payload,
            )
            
            if response.status_code != 200:
                # Don't log response body - might contain sensitive info
                logger.warning(f"llm_error provider=openai status={response.status_code}")
                return None, f"OpenAI API error: status {response.status_code}"
            
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not content:
                return None, "Empty response from OpenAI"
            
            logger.info("llm_success provider=openai")
            return content, None
            
    except httpx.TimeoutException:
        logger.warning("llm_timeout provider=openai")
        return None, "OpenAI API timeout"
    except httpx.RequestError as e:
        logger.warning(f"llm_network_error provider=openai error_type={type(e).__name__}")
        return None, f"Network error: {type(e).__name__}"
    except json.JSONDecodeError:
        logger.warning("llm_json_error provider=openai")
        return None, "Invalid JSON response from OpenAI"
    except Exception as e:
        # Catch-all, but don't log exception details (might contain secrets)
        logger.warning(f"llm_error provider=openai error_type={type(e).__name__}")
        return None, f"Unexpected error: {type(e).__name__}"
