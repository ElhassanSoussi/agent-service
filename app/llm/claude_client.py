"""
Claude API Client - The Brain of Xone

Single-user AI agent with:
- Async streaming responses
- Tool use support
- Memory integration
- Approval workflow
"""
import os
import logging
from typing import Optional, AsyncGenerator, List, Dict, Any
from anthropic import AsyncAnthropic
from anthropic.types import Message, TextBlock, ToolUseBlock

logger = logging.getLogger(__name__)

# Default model
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

# Global client (initialized once)
_client: Optional[AsyncAnthropic] = None


def get_claude_client() -> AsyncAnthropic:
    """Get or create Claude client singleton."""
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        _client = AsyncAnthropic(api_key=api_key)
    return _client


# =============================================================================
# Core Claude Functions
# =============================================================================

async def send_message(
    messages: List[Dict[str, Any]],
    system: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 1.0,
) -> Message:
    """
    Send a message to Claude and get a response.

    Args:
        messages: List of message dicts with 'role' and 'content'
        system: System prompt
        model: Claude model to use
        max_tokens: Max tokens in response
        tools: Optional list of tool definitions
        temperature: Sampling temperature (0-1)

    Returns:
        Message object from Claude
    """
    client = get_claude_client()

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
    }

    if system:
        kwargs["system"] = system

    if tools:
        kwargs["tools"] = tools

    logger.info(f"claude_request model={model} messages={len(messages)}")

    try:
        response = await client.messages.create(**kwargs)
        logger.info(f"claude_response tokens_in={response.usage.input_tokens} tokens_out={response.usage.output_tokens}")
        return response
    except Exception as e:
        logger.error(f"claude_error: {type(e).__name__}: {str(e)}")
        raise


async def stream_message(
    messages: List[Dict[str, Any]],
    system: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 1.0,
) -> AsyncGenerator[str, None]:
    """
    Stream a message response from Claude.

    Yields text chunks as they arrive.

    Args:
        Same as send_message

    Yields:
        Text chunks from Claude's response
    """
    client = get_claude_client()

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
    }

    if system:
        kwargs["system"] = system

    if tools:
        kwargs["tools"] = tools

    logger.info(f"claude_stream_request model={model} messages={len(messages)}")

    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

        # Log final message after stream completes
        final_message = await stream.get_final_message()
        logger.info(f"claude_stream_complete tokens_in={final_message.usage.input_tokens} tokens_out={final_message.usage.output_tokens}")

    except Exception as e:
        logger.error(f"claude_stream_error: {type(e).__name__}: {str(e)}")
        raise


# =============================================================================
# Tool Use Helpers
# =============================================================================

def extract_tool_uses(message: Message) -> List[ToolUseBlock]:
    """
    Extract tool use blocks from Claude's response.

    Args:
        message: Claude Message object

    Returns:
        List of ToolUseBlock objects
    """
    tool_uses = []
    for block in message.content:
        if isinstance(block, ToolUseBlock):
            tool_uses.append(block)
    return tool_uses


def extract_text(message: Message) -> str:
    """
    Extract text content from Claude's response.

    Args:
        message: Claude Message object

    Returns:
        Combined text from all TextBlock elements
    """
    text_parts = []
    for block in message.content:
        if isinstance(block, TextBlock):
            text_parts.append(block.text)
    return "".join(text_parts)


def has_tool_use(message: Message) -> bool:
    """Check if message contains any tool use blocks."""
    return any(isinstance(block, ToolUseBlock) for block in message.content)


# =============================================================================
# System Prompts
# =============================================================================

XONE_SYSTEM_PROMPT = """You are Xone, an autonomous AI agent created by Elhassan Soussi.

You are a private, single-user agent with full access to the owner's development environment.

Core capabilities:
- File operations (create, read, edit, delete)
- Shell command execution
- Code analysis and generation
- Long-term memory storage and retrieval
- Multi-step planning and execution

Important rules:
1. NEVER execute tools automatically - you must propose actions first
2. When proposing tool use, explain what you'll do and why
3. Wait for explicit approval before executing
4. Be concise but thorough in explanations
5. Store important insights in memory for future reference

You are not a chatbot - you are an autonomous operator who plans, proposes, gets approval, then acts.
"""

DEVELOPER_SYSTEM_PROMPT = """You are Developer Xone, a senior software engineer AI agent.

You help Elhassan build, modify, and maintain software projects.

When given a task:
1. Analyze what needs to be done
2. Plan the implementation steps
3. Propose specific file changes
4. Wait for approval
5. Execute the approved changes
6. Verify the results

Always show:
- What files will be created/modified
- Code diffs for changes
- Potential risks or side effects
- How to verify the changes worked

You have access to:
- create_file: Create new files
- edit_file: Modify existing files
- read_file: Read file contents
- run_command: Execute shell commands
- list_files: Browse directories

Never execute destructive operations without explicit approval.
"""
