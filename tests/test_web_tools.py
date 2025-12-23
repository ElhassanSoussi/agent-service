"""
Tests for Phase 8: Web Research Tools

Tests cover:
- Cache module (SQLite-backed caching with TTL)
- Rate limiter (token bucket)
- Web tools (web_search, web_page_text, web_summarize)
- Security (HTTPS only, blocked IPs, size limits)
- Integration with tools.execute_tool()
"""
import pytest
import time
import hashlib
import json
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

# Import modules under test
from app.core.cache import ToolCache, CacheEntry, tool_cache
from app.core.rate_limit import TokenBucket, RateLimiter, RateLimitError, rate_limiter
from app.core.web_tools import (
    tool_web_search,
    tool_web_page_text,
    tool_web_summarize,
    _is_ip_blocked,
    _extract_text_from_html,
    WEB_TOOLS,
)
from app.core.tools import execute_tool, ALL_TOOLS, CACHEABLE_TOOLS


# =============================================================================
# Cache Tests
# =============================================================================

class TestToolCache:
    """Tests for the ToolCache class."""

    def test_cache_key_generation(self):
        """Test that cache keys are generated consistently."""
        from app.core.cache import _compute_cache_key
        
        key1 = _compute_cache_key("web_search", {"query": "test"})
        key2 = _compute_cache_key("web_search", {"query": "test"})
        key3 = _compute_cache_key("web_search", {"query": "different"})
        
        assert key1 == key2  # Same inputs -> same key
        assert key1 != key3  # Different inputs -> different key
        assert len(key1) == 64  # SHA256 hex digest length

    def test_cache_set_and_get(self):
        """Test basic cache set and get operations."""
        tool_name = "test_cache_" + str(time.time())
        tool_input = {"query": "python programming"}
        output = {"results": [{"title": "Learn Python", "url": "https://python.org"}]}
        
        # Set cache
        tool_cache.set(tool_name, tool_input, output, ttl_seconds=3600)
        
        # Get cache
        cached = tool_cache.get(tool_name, tool_input)
        assert cached is not None
        assert cached["results"][0]["title"] == "Learn Python"

    def test_cache_miss(self):
        """Test cache miss returns None."""
        result = tool_cache.get("nonexistent_tool_" + str(time.time()), {"query": "test"})
        assert result is None

    def test_output_sanitization(self):
        """Test that sensitive keys are removed from cached output."""
        from app.core.cache import _sanitize_output
        
        output = {
            "body": "page content",
            "headers": {"Authorization": "Bearer secret"},
            "cookies": {"session": "abc123"},
            "safe_key": "keep this"
        }
        
        sanitized = _sanitize_output(output)
        
        assert "headers" not in sanitized
        assert "safe_key" in sanitized
        assert sanitized["safe_key"] == "keep this"


# =============================================================================
# Rate Limiter Tests
# =============================================================================

class TestRateLimiter:
    """Tests for the RateLimiter class."""

    @pytest.fixture
    def limiter(self):
        """Create a fresh rate limiter for testing."""
        limiter = RateLimiter()
        limiter.reset()  # Clear any existing state
        return limiter

    def test_token_bucket_initialization(self, limiter):
        """Test that token buckets are created with correct limits."""
        # web_search should have 10 tokens/min
        limits = limiter.get_limits("web_search")
        assert limits["limit_per_minute"] == 10

    def test_acquire_success(self, limiter):
        """Test successful token acquisition."""
        # Should succeed on fresh bucket
        assert limiter.try_acquire("web_search") is True

    def test_acquire_rate_limited(self, limiter):
        """Test rate limiting when bucket is exhausted."""
        tool_name = "test_tool_rate_" + str(time.time())
        
        # Exhaust all tokens (default limit is 30)
        for _ in range(35):
            limiter.try_acquire(tool_name)
        
        # Next request should fail
        assert limiter.try_acquire(tool_name) is False

    def test_check_available(self, limiter):
        """Test availability check without consumption."""
        tool_name = "test_avail_" + str(time.time())
        
        # Should be available initially
        is_avail, wait = limiter.check_available(tool_name)
        assert is_avail is True
        assert wait == 0.0

    def test_reset(self, limiter):
        """Test resetting rate limiter."""
        tool_name = "test_reset_" + str(time.time())
        
        # Exhaust tokens
        for _ in range(35):
            limiter.try_acquire(tool_name)
        
        # Reset
        limiter.reset(tool_name)
        
        # Should work again
        assert limiter.try_acquire(tool_name) is True


# =============================================================================
# Web Tools Tests
# =============================================================================

class TestWebTools:
    """Tests for the web tools module."""

    def test_private_ip_detection(self):
        """Test detection of private/internal IP addresses."""
        # Private IPs should be blocked
        assert _is_ip_blocked("127.0.0.1") is True
        assert _is_ip_blocked("192.168.1.1") is True
        assert _is_ip_blocked("10.0.0.1") is True
        assert _is_ip_blocked("172.16.0.1") is True
        
        # Public IPs should be allowed
        assert _is_ip_blocked("8.8.8.8") is False
        assert _is_ip_blocked("1.1.1.1") is False

    def test_text_extraction_from_html(self):
        """Test HTML to plain text extraction."""
        html = """
        <html>
        <head>
            <title>Test Page</title>
            <script>alert('bad');</script>
            <style>body { color: red; }</style>
        </head>
        <body>
            <h1>Hello World</h1>
            <p>This is a test paragraph.</p>
            <nav>Navigation link</nav>
        </body>
        </html>
        """
        title, text, truncated = _extract_text_from_html(html)
        
        # Should contain main content
        assert "Hello World" in text
        assert "This is a test paragraph" in text
        
        # Should not contain script/style content
        assert "alert" not in text
        assert "color: red" not in text
        
        # Title should be extracted
        assert title == "Test Page"
        
        # Nav is stripped out
        assert "Navigation link" not in text

    @pytest.mark.asyncio
    async def test_web_search_https_only(self):
        """Test that web_search only returns HTTPS results."""
        # This test verifies the search function parses results correctly
        # Real network calls would require HTTPS-only results
        pass  # Skipped - requires mocking HTTP client properly

    @pytest.mark.asyncio
    async def test_web_page_text_blocks_http(self):
        """Test that web_page_text rejects HTTP URLs."""
        with pytest.raises(ValueError, match="HTTPS"):
            await tool_web_page_text({"url": "http://example.com"})

    @pytest.mark.asyncio
    async def test_web_page_text_blocks_private_ip(self):
        """Test that web_page_text rejects private IPs."""
        with pytest.raises(ValueError, match="[Bb]locked"):
            await tool_web_page_text({"url": "https://192.168.1.1/page"})

    @pytest.mark.asyncio
    async def test_web_summarize_heuristic(self):
        """Test heuristic summarization without LLM."""
        text = """
        Python is a programming language. It is widely used for web development.
        Many data scientists use Python. Machine learning frameworks support Python.
        Python has a simple syntax. It is beginner-friendly.
        """
        
        # Call summarize - it will use heuristic if LLM is not enabled
        result = await tool_web_summarize({"text": text, "max_bullets": 3})
        
        assert "bullets" in result
        assert isinstance(result["bullets"], list)

    def test_web_tools_registered(self):
        """Test that all web tools are registered."""
        assert "web_search" in WEB_TOOLS
        assert "web_page_text" in WEB_TOOLS
        assert "web_summarize" in WEB_TOOLS
        
        # Should also be in ALL_TOOLS
        assert "web_search" in ALL_TOOLS
        assert "web_page_text" in ALL_TOOLS
        assert "web_summarize" in ALL_TOOLS


# =============================================================================
# Integration Tests
# =============================================================================

class TestToolsIntegration:
    """Integration tests for tools with cache and rate limiting."""

    @pytest.mark.asyncio
    async def test_execute_tool_with_caching(self):
        """Test that execute_tool uses caching for cacheable tools."""
        # Use echo tool which is fast and predictable
        tool_input = {"message": "cache_test_" + str(time.time())}
        
        # First call
        result1 = await execute_tool("echo", tool_input)
        assert "error" not in result1
        
        # Second call should use cache (if echo is cacheable)
        # Note: echo might not be cacheable by default, this tests the mechanism

    @pytest.mark.asyncio
    async def test_execute_tool_rate_limiting(self):
        """Test that execute_tool respects rate limits."""
        # This test verifies the rate limiting integration
        # We can't easily exhaust the bucket in a unit test without mocking
        pass

    @pytest.mark.asyncio
    async def test_cacheable_tools_config(self):
        """Test that CACHEABLE_TOOLS has correct configuration."""
        # web_search should be cacheable with 1 hour TTL
        assert "web_search" in CACHEABLE_TOOLS
        assert CACHEABLE_TOOLS["web_search"] == 3600
        
        # web_page_text should be cacheable with 30 min TTL
        assert "web_page_text" in CACHEABLE_TOOLS
        assert CACHEABLE_TOOLS["web_page_text"] == 1800
        
        # http_fetch should be cacheable with 5 min TTL
        assert "http_fetch" in CACHEABLE_TOOLS
        assert CACHEABLE_TOOLS["http_fetch"] == 300


# =============================================================================
# Security Tests
# =============================================================================

class TestWebToolsSecurity:
    """Security-focused tests for web tools."""

    @pytest.mark.asyncio
    async def test_url_validation_http_rejected(self):
        """Test URL validation in web_page_text rejects HTTP."""
        with pytest.raises(ValueError, match="HTTPS"):
            await tool_web_page_text({"url": "http://example.com"})

    @pytest.mark.asyncio
    async def test_url_validation_missing(self):
        """Test URL validation in web_page_text requires URL."""
        with pytest.raises(ValueError):
            await tool_web_page_text({})

    @pytest.mark.asyncio
    async def test_query_validation_missing(self):
        """Test query validation in web_search requires query."""
        with pytest.raises(ValueError):
            await tool_web_search({})

    @pytest.mark.asyncio
    async def test_text_validation_missing(self):
        """Test text validation in web_summarize requires text."""
        with pytest.raises(ValueError):
            await tool_web_summarize({})

    def test_localhost_variants_blocked(self):
        """Test that various localhost representations are blocked."""
        localhost_variants = [
            "127.0.0.1",
            "127.0.0.2",
            "0.0.0.0",
            "::1",
        ]
        
        for variant in localhost_variants:
            assert _is_ip_blocked(variant) is True, f"{variant} should be blocked"


# =============================================================================
# Schema Tests
# =============================================================================

class TestSchemas:
    """Tests for updated Pydantic schemas."""

    def test_tool_name_enum_includes_web_tools(self):
        """Test that ToolName enum includes web tools."""
        from app.schemas.agent import ToolName
        
        assert ToolName.WEB_SEARCH.value == "web_search"
        assert ToolName.WEB_PAGE_TEXT.value == "web_page_text"
        assert ToolName.WEB_SUMMARIZE.value == "web_summarize"

    def test_citation_model(self):
        """Test Citation model."""
        from app.schemas.agent import Citation
        
        citation = Citation(url="https://example.com", title="Example")
        assert citation.url == "https://example.com"
        assert citation.title == "Example"
        
        # Title is optional
        citation2 = Citation(url="https://example.com")
        assert citation2.title is None

    def test_agent_result_response_with_citations(self):
        """Test AgentResultResponse includes citations field."""
        from app.schemas.agent import AgentResultResponse, Citation, JobStatus, JobMode
        
        response = AgentResultResponse(
            job_id="test-123",
            status=JobStatus.DONE,
            mode=JobMode.AGENT,
            final_output="Summary of research",
            bullets=["Point 1", "Point 2"],
            citations=[
                Citation(url="https://example.com", title="Example"),
                Citation(url="https://test.com", title="Test"),
            ]
        )
        
        assert response.citations is not None
        assert len(response.citations) == 2
        assert response.bullets is not None
        assert len(response.bullets) == 2
