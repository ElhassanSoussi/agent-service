"""
Agent planner: converts user prompts into execution plans.
Supports rule-based (default) and LLM-based (optional) planning.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from app.llm.config import get_llm_config
from app.llm.client import get_llm_client
from app.llm.schemas import PlannerResult

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """A single step in the execution plan."""
    tool: str
    input: dict[str, Any]
    description: str


@dataclass
class Plan:
    """Execution plan for an agent job."""
    steps: list[PlanStep]
    reasoning: str  # Brief explanation of why this plan was chosen
    planner_mode: str = "rules"  # "rules", "llm", or "llm_fallback"
    llm_error: Optional[str] = None  # Error from LLM if any


@dataclass
class PlanMetadata:
    """Metadata about the planning process (safe to store)."""
    mode: str  # "rules", "llm", "llm_fallback"
    step_count: int
    fallback_reason: Optional[str] = None
    error: Optional[str] = None  # Never contains secrets


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    # Simple URL pattern for https URLs
    url_pattern = r'https://[^\s<>"\')\]]+(?<![.,!?;:])'
    urls = re.findall(url_pattern, text, re.IGNORECASE)
    return urls


def is_fetch_request(prompt: str) -> bool:
    """Check if prompt is asking to fetch/get/retrieve content from a URL."""
    fetch_keywords = [
        "fetch", "get", "retrieve", "download", "read", "load",
        "scrape", "crawl", "access", "visit", "open", "check",
        "what is at", "what's at", "content of", "contents of",
        "summarize", "summary of"
    ]
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in fetch_keywords)


def is_echo_request(prompt: str) -> bool:
    """Check if prompt is asking for echo/repeat/format."""
    echo_keywords = [
        "echo", "repeat", "say", "return", "format", "transform",
        "convert", "rephrase", "reword"
    ]
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in echo_keywords)


def is_search_request(prompt: str) -> bool:
    """Check if prompt is asking for web search/research."""
    search_keywords = [
        "search", "find", "look up", "lookup", "research", "discover",
        "what is", "what are", "who is", "when did", "where is", "how to",
        "latest", "recent", "news about", "information about", "info about",
        "tell me about", "learn about"
    ]
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in search_keywords)


def is_summarize_request(prompt: str) -> bool:
    """Check if prompt is asking for summarization."""
    summarize_keywords = [
        "summarize", "summary", "summarise", "brief", "tldr", "tl;dr",
        "key points", "main points", "overview", "digest"
    ]
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in summarize_keywords)


def is_build_request(prompt: str) -> bool:
    """Check if prompt is asking for build/test/verify operations."""
    build_keywords = [
        "run tests", "run the tests", "execute tests", "run test",
        "verify build", "check build", "build project", "build the project",
        "run ci", "run pipeline", "execute pipeline",
        "test this repo", "test the repo", "test repository",
        "run pytest", "run npm test", "npm test", "pytest",
        "verify code", "check tests", "run lint", "lint code",
        "build and test", "test and build",
    ]
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in build_keywords)


def extract_repo_url_for_build(prompt: str) -> Optional[str]:
    """Extract GitHub/GitLab repository URL from prompt for build operations."""
    import re
    # Pattern for GitHub/GitLab URLs
    pattern = r'https://(?:github\.com|gitlab\.com)/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:\.git)?'
    matches = re.findall(pattern, prompt, re.IGNORECASE)
    if matches:
        url = matches[0]
        # Remove .git suffix if present
        if url.endswith('.git'):
            url = url[:-4]
        return url
    return None


def create_rule_based_plan(
    prompt: str,
    allowed_tools: list[str],
    max_steps: int
) -> Plan:
    """
    Create a plan using rule-based heuristics.
    This is the default planner, no external calls required.
    Supports: echo, http_fetch, web_search, web_page_text, web_summarize
    """
    urls = extract_urls(prompt)
    steps: list[PlanStep] = []
    reasoning = ""
    
    has_web_search = "web_search" in allowed_tools
    has_web_page_text = "web_page_text" in allowed_tools
    has_web_summarize = "web_summarize" in allowed_tools
    has_http_fetch = "http_fetch" in allowed_tools
    has_echo = "echo" in allowed_tools
    has_build_tool = "build_tool" in allowed_tools
    
    want_summary = is_summarize_request(prompt)
    want_search = is_search_request(prompt)
    want_fetch = is_fetch_request(prompt)
    want_build = is_build_request(prompt)
    
    # Case 1: Web research request (search + read + summarize)
    if want_search and has_web_search and not urls:
        # Extract search query from prompt
        query = prompt
        # Remove common prefix phrases
        for prefix in ["search for", "find", "look up", "research", "tell me about", "what is", "what are"]:
            if query.lower().startswith(prefix):
                query = query[len(prefix):].strip()
        
        steps.append(PlanStep(
            tool="web_search",
            input={"query": query, "max_results": 3},
            description=f"Search the web for: {query[:50]}"
        ))
        
        # If we can read pages, add step to fetch top result
        if has_web_page_text and len(steps) < max_steps:
            steps.append(PlanStep(
                tool="web_page_text",
                input={"url": "{{search_result_0_url}}", "max_chars": 15000},
                description="Fetch and extract text from top search result"
            ))
        
        # Add summarization if requested
        if want_summary and has_web_summarize and len(steps) < max_steps:
            steps.append(PlanStep(
                tool="web_summarize",
                input={"text": "{{previous_text}}", "max_bullets": 5},
                description="Summarize the fetched content"
            ))
        
        reasoning = f"Web research plan for query: {query[:50]}"
    
    # Case 2: URL provided - fetch and optionally summarize
    elif urls and (want_fetch or want_summary):
        url = urls[0]
        
        # Prefer web_page_text over http_fetch for better text extraction
        if has_web_page_text:
            steps.append(PlanStep(
                tool="web_page_text",
                input={"url": url, "max_chars": 20000},
                description=f"Fetch and extract text from {url}"
            ))
        elif has_http_fetch:
            steps.append(PlanStep(
                tool="http_fetch",
                input={"url": url},
                description=f"Fetch content from {url}"
            ))
        
        # Add summarization if requested
        if want_summary and has_web_summarize and len(steps) < max_steps:
            steps.append(PlanStep(
                tool="web_summarize",
                input={"text": "{{previous_text}}", "max_bullets": 5},
                description="Summarize the fetched content"
            ))
        
        reasoning = f"Fetch and process URL: {url}"
    
    # Case 3: Build/test request with repo URL (check before generic URL handling)
    elif want_build and has_build_tool:
        repo_url = extract_repo_url_for_build(prompt)
        if repo_url:
            steps.append(PlanStep(
                tool="build_tool",
                input={"repo_url": repo_url},
                description=f"Run build/test operations for repository: {repo_url}"
            ))
            reasoning = f"Build/test plan for repository: {repo_url}"
        else:
            steps.append(PlanStep(
                tool="echo",
                input={
                    "prompt": prompt,
                    "note": "Unable to determine repository URL for build/test operations",
                    "suggestion": "Try including a GitHub/GitLab repository URL in the prompt"
                },
                description="Return clarification for build/test request"
            ))
            reasoning = "Could not determine repository URL for build/test request"
    
    # Case 4: URL found but no explicit action
    elif urls:
        url = urls[0]
        if has_web_page_text:
            steps.append(PlanStep(
                tool="web_page_text",
                input={"url": url, "max_chars": 20000},
                description=f"Fetch and extract text from {url}"
            ))
        elif has_http_fetch:
            steps.append(PlanStep(
                tool="http_fetch",
                input={"url": url},
                description=f"Fetch content from {url}"
            ))
        reasoning = f"Found URL in prompt, fetching: {url}"
    
    # Case 4: Echo/repeat request
    elif is_echo_request(prompt) and has_echo:
        steps.append(PlanStep(
            tool="echo",
            input={"prompt": prompt, "action": "process"},
            description="Process and return the requested content"
        ))
        reasoning = "Detected echo/format request"
    
    # Case 5: General search request without specific URL
    elif want_search and has_web_search:
        query = prompt
        steps.append(PlanStep(
            tool="web_search",
            input={"query": query, "max_results": 5},
            description=f"Search the web for: {query[:50]}"
        ))
        reasoning = f"General web search for: {query[:50]}"
    
    # Default case: clarify intent
    else:
        if has_echo:
            steps.append(PlanStep(
                tool="echo",
                input={
                    "prompt": prompt,
                    "note": "Unable to determine specific action from prompt",
                    "suggestion": "Try: 'search for X', 'summarize URL', or include a URL"
                },
                description="Return clarification with the prompt"
            ))
        reasoning = "Could not determine specific action, returning clarification"
    
    # Limit to max_steps
    steps = steps[:max_steps]
    
    return Plan(steps=steps, reasoning=reasoning, planner_mode="rules")


def _llm_plan_to_plan(result: PlannerResult, prompt: str) -> Plan:
    """Convert LLM PlannerResult to internal Plan format."""
    if result.plan is None:
        # Should not happen if called correctly, but handle gracefully
        return create_rule_based_plan(prompt, ["echo", "http_fetch"], 3)
    
    steps = []
    for llm_step in result.plan.steps:
        steps.append(PlanStep(
            tool=llm_step.tool,
            input=llm_step.input,
            description=llm_step.why,
        ))
    
    return Plan(
        steps=steps,
        reasoning=result.plan.goal,
        planner_mode="llm",
        llm_error=None,
    )


async def create_llm_plan_async(
    prompt: str,
    allowed_tools: list[str],
    max_steps: int
) -> tuple[Optional[Plan], PlanMetadata]:
    """
    Create a plan using LLM asynchronously.
    
    Returns:
        (plan, metadata) - plan is None if LLM failed and we should fallback
    """
    config = get_llm_config()
    
    # If not in LLM mode, don't even try
    if config.planner_mode != "llm":
        return None, PlanMetadata(
            mode="rules",
            step_count=0,
            fallback_reason=None,
        )
    
    # Get LLM client and generate plan
    client = get_llm_client()
    result = await client.generate_plan(
        prompt=prompt,
        allowed_tools=allowed_tools,
        max_steps=max_steps,
    )
    
    # Check result
    if result.mode == "llm" and result.plan:
        plan = _llm_plan_to_plan(result, prompt)
        metadata = PlanMetadata(
            mode="llm",
            step_count=len(plan.steps),
        )
        logger.info(f"planner_llm_success steps={len(plan.steps)}")
        return plan, metadata
    
    # LLM failed or fell back
    logger.info(f"planner_llm_fallback reason={result.fallback_reason}")
    metadata = PlanMetadata(
        mode="llm_fallback",
        step_count=0,
        fallback_reason=result.fallback_reason,
        error=result.error,
    )
    return None, metadata


def create_plan(
    prompt: str,
    allowed_tools: list[str],
    max_steps: int = 3,
) -> tuple[Plan, PlanMetadata]:
    """
    Create an execution plan for the given prompt (synchronous wrapper).
    
    Args:
        prompt: User's natural language request
        allowed_tools: List of tool names that can be used
        max_steps: Maximum number of steps in the plan
    
    Returns:
        (Plan, PlanMetadata) tuple
    """
    config = get_llm_config()
    
    # Try LLM planner if configured
    if config.planner_mode == "llm":
        # Run async function synchronously
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        plan, metadata = loop.run_until_complete(
            create_llm_plan_async(prompt, allowed_tools, max_steps)
        )
        
        if plan:
            return plan, metadata
        
        # Fallback to rules if LLM failed
        rules_plan = create_rule_based_plan(prompt, allowed_tools, max_steps)
        rules_plan.planner_mode = "llm_fallback"
        rules_plan.llm_error = metadata.error
        metadata.step_count = len(rules_plan.steps)
        return rules_plan, metadata
    
    # Default: rule-based planner
    plan = create_rule_based_plan(prompt, allowed_tools, max_steps)
    metadata = PlanMetadata(
        mode="rules",
        step_count=len(plan.steps),
    )
    logger.info(f"planner_rules steps={len(plan.steps)}")
    return plan, metadata


async def create_plan_async(
    prompt: str,
    allowed_tools: list[str],
    max_steps: int = 3,
) -> tuple[Plan, PlanMetadata]:
    """
    Create an execution plan for the given prompt (async version).
    
    Args:
        prompt: User's natural language request
        allowed_tools: List of tool names that can be used
        max_steps: Maximum number of steps in the plan
    
    Returns:
        (Plan, PlanMetadata) tuple
    """
    config = get_llm_config()
    
    # Try LLM planner if configured
    if config.planner_mode == "llm":
        plan, metadata = await create_llm_plan_async(prompt, allowed_tools, max_steps)
        
        if plan:
            return plan, metadata
        
        # Fallback to rules if LLM failed
        rules_plan = create_rule_based_plan(prompt, allowed_tools, max_steps)
        rules_plan.planner_mode = "llm_fallback"
        rules_plan.llm_error = metadata.error
        metadata.step_count = len(rules_plan.steps)
        return rules_plan, metadata
    
    # Default: rule-based planner
    plan = create_rule_based_plan(prompt, allowed_tools, max_steps)
    metadata = PlanMetadata(
        mode="rules",
        step_count=len(plan.steps),
    )
    logger.info(f"planner_rules steps={len(plan.steps)}")
    return plan, metadata


def summarize_content(content: str, max_length: int = 500) -> str:
    """
    Create a simple summary of content.
    Uses basic heuristics (no LLM required).
    """
    if not content:
        return ""
    
    # Remove extra whitespace
    content = " ".join(content.split())
    
    # If content is short enough, return as-is
    if len(content) <= max_length:
        return content
    
    # Try to break at sentence boundary
    truncated = content[:max_length]
    
    # Find last sentence ending
    for end in [". ", "! ", "? ", "\n"]:
        last_end = truncated.rfind(end)
        if last_end > max_length // 2:
            return truncated[:last_end + 1].strip() + "..."
    
    # No sentence boundary, just truncate at word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_length // 2:
        return truncated[:last_space].strip() + "..."
    
    return truncated + "..."
