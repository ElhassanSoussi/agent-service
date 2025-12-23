"""
Anthropic Claude API client using httpx.
Minimal implementation - no heavy dependencies.
"""
import json
import logging
from typing import Optional

import httpx

from app.llm.config import LLMConfig

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-3-haiku-20240307"


async def call_anthropic(
    config: LLMConfig,
    system_prompt: str,
    user_prompt: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Call Anthropic API for plan generation.
    
    Returns:
        (response_text, error_message)
        - On success: (json_string, None)
        - On failure: (None, error_description)
    
    NEVER logs API key or request bodies.
    """
    if not config.api_key:
        return None, "Anthropic API key not configured"
    
    model = config.model or DEFAULT_MODEL
    
    headers = {
        "x-api-key": config.api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    
    payload = {
        "model": model,
        "max_tokens": config.max_tokens,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }
    
    try:
        async with httpx.AsyncClient(timeout=config.timeout_s) as client:
            # Log only that we're making a call, not the content
            logger.info(f"llm_call provider=anthropic model={model}")
            
            response = await client.post(
                ANTHROPIC_API_URL,
                headers=headers,
                json=payload,
            )
            
            if response.status_code != 200:
                # Don't log response body - might contain sensitive info
                logger.warning(f"llm_error provider=anthropic status={response.status_code}")
                return None, f"Anthropic API error: status {response.status_code}"
            
            data = response.json()
            content_blocks = data.get("content", [])
            
            # Extract text from content blocks
            text_content = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text_content += block.get("text", "")
            
            if not text_content:
                return None, "Empty response from Anthropic"
            
            logger.info("llm_success provider=anthropic")
            return text_content, None
            
    except httpx.TimeoutException:
        logger.warning("llm_timeout provider=anthropic")
        return None, "Anthropic API timeout"
    except httpx.RequestError as e:
        logger.warning(f"llm_network_error provider=anthropic error_type={type(e).__name__}")
        return None, f"Network error: {type(e).__name__}"
    except json.JSONDecodeError:
        logger.warning("llm_json_error provider=anthropic")
        return None, "Invalid JSON response from Anthropic"
    except Exception as e:
        # Catch-all, but don't log exception details (might contain secrets)
        logger.warning(f"llm_error provider=anthropic error_type={type(e).__name__}")
        return None, f"Unexpected error: {type(e).__name__}"
