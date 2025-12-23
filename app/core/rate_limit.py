"""
Token bucket rate limiter for tools.
In-memory implementation with per-tool limits.
"""
import logging
import time
import threading
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Default rate limits (requests per minute)
DEFAULT_RATE_LIMIT = 30  # General tools
TOOL_RATE_LIMITS = {
    "web_search": 10,      # Tighter limit for search
    "web_page_text": 20,   # Medium limit for page fetching
    "web_summarize": 20,   # Medium limit for summarization
    "http_fetch": 30,      # Existing tool
    "echo": 60,            # Very permissive for echo
    # GitHub API limits (Phase 12)
    "github_api": 60,      # Authenticated GitHub API
    "github_search": 10,   # GitHub code search (stricter)
}


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""
    tokens: float
    max_tokens: float
    refill_rate: float  # tokens per second
    last_refill: float
    
    def try_consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.
        Returns True if successful, False if rate limited.
        """
        now = time.time()
        
        # Refill tokens based on time elapsed
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        
        return False
    
    def time_until_available(self, tokens: int = 1) -> float:
        """Return seconds until tokens are available."""
        if self.tokens >= tokens:
            return 0.0
        
        needed = tokens - self.tokens
        return needed / self.refill_rate


class RateLimiter:
    """Rate limiter with per-tool token buckets."""
    
    def __init__(self):
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
    
    def _get_or_create_bucket(self, tool_name: str) -> TokenBucket:
        """Get or create a token bucket for a tool."""
        with self._lock:
            if tool_name not in self._buckets:
                # Get rate limit for tool (requests per minute)
                rpm = TOOL_RATE_LIMITS.get(tool_name, DEFAULT_RATE_LIMIT)
                
                # Convert to tokens per second
                refill_rate = rpm / 60.0
                
                self._buckets[tool_name] = TokenBucket(
                    tokens=float(rpm),  # Start with full bucket
                    max_tokens=float(rpm),
                    refill_rate=refill_rate,
                    last_refill=time.time(),
                )
            
            return self._buckets[tool_name]
    
    def try_acquire(self, tool_name: str, tokens: int = 1) -> bool:
        """
        Try to acquire tokens for a tool call.
        Returns True if allowed, False if rate limited.
        """
        bucket = self._get_or_create_bucket(tool_name)
        
        with self._lock:
            allowed = bucket.try_consume(tokens)
        
        if not allowed:
            logger.warning(f"rate_limited tool={tool_name}")
        
        return allowed
    
    def check_available(self, tool_name: str, tokens: int = 1) -> tuple[bool, float]:
        """
        Check if tokens are available without consuming.
        Returns (is_available, seconds_until_available).
        """
        bucket = self._get_or_create_bucket(tool_name)
        
        with self._lock:
            # Refill first
            now = time.time()
            elapsed = now - bucket.last_refill
            bucket.tokens = min(bucket.max_tokens, bucket.tokens + elapsed * bucket.refill_rate)
            bucket.last_refill = now
            
            if bucket.tokens >= tokens:
                return True, 0.0
            
            wait_time = bucket.time_until_available(tokens)
            return False, wait_time
    
    def get_limits(self, tool_name: str) -> dict:
        """Get rate limit info for a tool."""
        rpm = TOOL_RATE_LIMITS.get(tool_name, DEFAULT_RATE_LIMIT)
        bucket = self._get_or_create_bucket(tool_name)
        
        with self._lock:
            return {
                "tool": tool_name,
                "limit_per_minute": rpm,
                "tokens_available": int(bucket.tokens),
            }
    
    def reset(self, tool_name: Optional[str] = None) -> None:
        """Reset rate limiter for a tool or all tools."""
        with self._lock:
            if tool_name:
                if tool_name in self._buckets:
                    del self._buckets[tool_name]
            else:
                self._buckets.clear()


# Global rate limiter instance
rate_limiter = RateLimiter()


class RateLimitError(Exception):
    """Raised when a tool call is rate limited."""
    
    def __init__(self, tool_name: str, wait_seconds: float):
        self.tool_name = tool_name
        self.wait_seconds = wait_seconds
        super().__init__(
            f"Rate limited: {tool_name}. Retry after {wait_seconds:.1f} seconds."
        )
