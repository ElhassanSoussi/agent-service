"""
Agent tools: echo, http_fetch, and web research tools.
Safety constraints enforced:
- HTTPS only
- Block local/private IPs
- Timeout <= 15s
- Max response size limits
- Cache and rate limiting
"""
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.cache import tool_cache
from app.core.rate_limit import rate_limiter, RateLimitError
from app.core.web_tools import WEB_TOOLS

logger = logging.getLogger(__name__)

# Constants
MAX_INPUT_SIZE = 32 * 1024  # 32KB
MAX_RESPONSE_SIZE = 64 * 1024  # 64KB
HTTP_TIMEOUT = 10  # seconds

# Blocked IP ranges (private/local networks)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),    # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),   # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 private
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]

BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}


def is_ip_blocked(ip_str: str) -> bool:
    """Check if an IP address is in a blocked range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in BLOCKED_NETWORKS:
            if ip in network:
                return True
        return False
    except ValueError:
        return True  # Invalid IP = blocked


def resolve_and_validate_url(url: str) -> str:
    """
    Validate URL and resolve hostname to check for blocked IPs.
    Returns the URL if valid, raises ValueError if blocked.
    """
    parsed = urlparse(url)
    
    # HTTPS only
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS URLs are allowed")
    
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: no hostname")
    
    # Check blocked hostnames
    if hostname.lower() in BLOCKED_HOSTNAMES:
        raise ValueError(f"Blocked hostname: {hostname}")
    
    # Resolve hostname and check IP
    try:
        # Get all IPs for hostname
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            if is_ip_blocked(ip_str):
                raise ValueError(f"Blocked IP address for hostname: {hostname}")
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed: {e}")
    
    return url


async def tool_echo(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Echo tool: returns the input data back.
    Max input size enforced at API level.
    """
    return {"result": input_data}


async def tool_http_fetch(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    HTTP fetch tool: fetches content from an HTTPS URL.
    
    Input:
        {"url": "https://example.com/api"}
    
    Output:
        {"status_code": 200, "body": "...", "content_type": "..."}
    
    Safety:
        - HTTPS only
        - Blocked: local/private IPs
        - Timeout: 10s
        - Max response: 64KB
    """
    url = input_data.get("url")
    if not url:
        raise ValueError("Missing 'url' in input")
    
    if not isinstance(url, str):
        raise ValueError("'url' must be a string")
    
    # Validate URL and check for blocked IPs
    validated_url = resolve_and_validate_url(url)
    
    # Fetch with safety constraints
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        follow_redirects=False,  # Don't follow redirects (could redirect to blocked IP)
        max_redirects=0,
    ) as client:
        response = await client.get(validated_url)
        
        # Limit response size
        content = response.content[:MAX_RESPONSE_SIZE]
        
        # Try to decode as text, fallback to indicating binary
        try:
            body = content.decode("utf-8")
        except UnicodeDecodeError:
            body = f"<binary data, {len(content)} bytes>"
        
        return {
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "unknown"),
            "body": body,
            "truncated": len(response.content) > MAX_RESPONSE_SIZE,
        }


# Tool registry (basic tools)
BASIC_TOOLS = {
    "echo": tool_echo,
    "http_fetch": tool_http_fetch,
}

# All tools including web tools
ALL_TOOLS = {**BASIC_TOOLS, **WEB_TOOLS}

# Tool allowlist for agent planning
ALLOWED_TOOLS = ["echo", "http_fetch", "web_search", "web_page_text", "web_summarize"]

# Tools that should be cached (with TTL in seconds)
CACHEABLE_TOOLS = {
    "web_search": 3600,       # 1 hour
    "web_page_text": 1800,    # 30 minutes
    "http_fetch": 300,        # 5 minutes
}


async def execute_tool(
    tool_name: str,
    input_data: dict[str, Any],
    use_cache: bool = True,
    use_rate_limit: bool = True,
) -> dict[str, Any]:
    """
    Execute a tool by name with given input.
    Applies caching and rate limiting.
    
    Args:
        tool_name: Name of the tool to execute
        input_data: Input data for the tool
        use_cache: Whether to use caching (default True)
        use_rate_limit: Whether to apply rate limiting (default True)
    
    Returns:
        Tool output dict
    
    Raises:
        ValueError: If tool is unknown
        RateLimitError: If rate limited
    """
    tool_fn = ALL_TOOLS.get(tool_name)
    if not tool_fn:
        raise ValueError(f"Unknown tool: {tool_name}")
    
    # Check rate limit
    if use_rate_limit:
        if not rate_limiter.try_acquire(tool_name):
            available, wait_time = rate_limiter.check_available(tool_name)
            raise RateLimitError(tool_name, wait_time)
    
    # Check cache
    if use_cache and tool_name in CACHEABLE_TOOLS:
        cached = tool_cache.get(tool_name, input_data)
        if cached is not None:
            logger.debug(f"tool_cache_hit tool={tool_name}")
            return cached
    
    # Execute tool
    result = await tool_fn(input_data)
    
    # Store in cache
    if use_cache and tool_name in CACHEABLE_TOOLS:
        ttl = CACHEABLE_TOOLS[tool_name]
        tool_cache.set(tool_name, input_data, result, ttl_seconds=ttl)
    
    return result
