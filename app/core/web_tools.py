"""
Web research tools for the agent.
- web_search: DuckDuckGo HTML search
- web_page_text: Fetch and extract readable text from a URL
- web_summarize: Summarize text (LLM or heuristic)

Security:
- HTTPS only
- Block local/private IPs
- Timeouts and size limits
- Safe HTML parsing (no JS execution)
"""
import logging
import re
import socket
import ipaddress
from typing import Any, Optional
from urllib.parse import urlparse, urlencode, quote_plus, parse_qs, unquote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Constants
HTTP_TIMEOUT = 15  # seconds
MAX_DOWNLOAD_SIZE = 1 * 1024 * 1024  # 1MB
MAX_TEXT_EXTRACT = 50000  # characters
DEFAULT_MAX_RESULTS = 5
DEFAULT_MAX_CHARS = 20000
DEFAULT_MAX_BULLETS = 8

USER_AGENT = (
    "Mozilla/5.0 (compatible; AgentService/1.0; +https://github.com/agent-service)"
)

# Blocked IP ranges (same as tools.py)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}


def _is_ip_blocked(ip_str: str) -> bool:
    """Check if an IP address is in a blocked range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in BLOCKED_NETWORKS:
            if ip in network:
                return True
        return False
    except ValueError:
        return True


def _validate_url(url: str) -> str:
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
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            if _is_ip_blocked(ip_str):
                raise ValueError(f"Blocked IP address for hostname: {hostname}")
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed: {e}")
    
    return url


def _get_http_client() -> httpx.AsyncClient:
    """Create an HTTP client with safety settings."""
    return httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
        max_redirects=3,
        headers={"User-Agent": USER_AGENT},
    )


def _extract_text_from_html(html: str, max_chars: int = MAX_TEXT_EXTRACT) -> tuple[str, str, bool]:
    """
    Extract readable text from HTML.
    Returns (title, text, truncated).
    """
    soup = BeautifulSoup(html, "lxml")
    
    # Get title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
    
    # Remove script and style elements
    for element in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        element.decompose()
    
    # Get text
    text = soup.get_text(separator=" ", strip=True)
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Truncate if needed
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
        # Try to break at word boundary
        last_space = text.rfind(' ', max_chars - 200)
        if last_space > max_chars // 2:
            text = text[:last_space] + "..."
    
    return title, text, truncated


async def tool_web_search(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Search the web using DuckDuckGo HTML interface.
    
    Input:
        {"query": "string", "max_results": 5}
    
    Output:
        {"results": [{"title": "...", "url": "https://...", "snippet": "..."}]}
    """
    query = input_data.get("query")
    if not query or not isinstance(query, str):
        raise ValueError("Missing or invalid 'query' in input")
    
    max_results = min(input_data.get("max_results", DEFAULT_MAX_RESULTS), 10)
    
    # DuckDuckGo HTML search
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    
    async with _get_http_client() as client:
        response = await client.get(search_url)
        response.raise_for_status()
        
        # Limit response size
        content = response.content[:MAX_DOWNLOAD_SIZE]
        html = content.decode("utf-8", errors="replace")
    
    # Parse results
    soup = BeautifulSoup(html, "lxml")
    results = []
    
    # DuckDuckGo HTML results are in divs with class "result"
    for result_div in soup.find_all("div", class_="result"):
        if len(results) >= max_results:
            break
        
        # Find link
        link_tag = result_div.find("a", class_="result__a")
        if not link_tag:
            continue
        
        title = link_tag.get_text(strip=True)
        raw_url = link_tag.get("href", "")
        
        # DuckDuckGo wraps URLs in a redirect like //duckduckgo.com/l/?uddg=https%3A%2F%2F...
        # Extract the actual URL from the uddg parameter
        url = raw_url
        if "duckduckgo.com/l/" in raw_url and "uddg=" in raw_url:
            try:
                # Parse the redirect URL
                parsed = urlparse(raw_url if raw_url.startswith("http") else f"https:{raw_url}")
                qs = parse_qs(parsed.query)
                if "uddg" in qs:
                    url = unquote(qs["uddg"][0])
            except Exception:
                continue
        
        # Skip non-HTTPS URLs
        if not url.startswith("https://"):
            continue
        
        # Get snippet
        snippet_tag = result_div.find("a", class_="result__snippet")
        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
        
        results.append({
            "title": title[:200],  # Limit title length
            "url": url,
            "snippet": snippet[:500],  # Limit snippet length
        })
    
    logger.info(f"web_search query_len={len(query)} results={len(results)}")
    
    return {"results": results}


async def tool_web_page_text(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a web page and extract readable text.
    
    Input:
        {"url": "https://...", "max_chars": 20000}
    
    Output:
        {"url": "...", "title": "...", "text": "...", "truncated": true|false}
    """
    url = input_data.get("url")
    if not url or not isinstance(url, str):
        raise ValueError("Missing or invalid 'url' in input")
    
    max_chars = min(input_data.get("max_chars", DEFAULT_MAX_CHARS), MAX_TEXT_EXTRACT)
    
    # Validate URL (HTTPS only, no local IPs)
    validated_url = _validate_url(url)
    
    async with _get_http_client() as client:
        response = await client.get(validated_url)
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower() and "text/plain" not in content_type.lower():
            raise ValueError(f"Unsupported content type: {content_type}")
        
        # Limit response size
        content = response.content[:MAX_DOWNLOAD_SIZE]
        
        # Try to decode
        try:
            html = content.decode("utf-8")
        except UnicodeDecodeError:
            html = content.decode("latin-1", errors="replace")
    
    # Extract text
    title, text, truncated = _extract_text_from_html(html, max_chars)
    
    logger.info(f"web_page_text url={url} text_len={len(text)} truncated={truncated}")
    
    return {
        "url": url,
        "title": title[:200],
        "text": text,
        "truncated": truncated,
    }


def _heuristic_summarize(text: str, max_bullets: int) -> list[str]:
    """
    Create a heuristic summary by extracting key sentences.
    Uses sentence scoring based on position, length, and keywords.
    """
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Filter and clean sentences
    candidates = []
    for i, sent in enumerate(sentences):
        sent = sent.strip()
        # Skip very short or very long sentences
        if len(sent) < 20 or len(sent) > 300:
            continue
        # Skip sentences that look like navigation/boilerplate
        if any(x in sent.lower() for x in ["click here", "read more", "subscribe", "cookie", "privacy policy"]):
            continue
        
        # Score sentence
        score = 0
        # Position bonus (first sentences often important)
        if i < 5:
            score += 5 - i
        # Length bonus (medium length preferred)
        if 50 < len(sent) < 200:
            score += 2
        # Keyword bonus
        keywords = ["important", "key", "main", "significant", "research", "study", "found", "shows", "according"]
        for kw in keywords:
            if kw in sent.lower():
                score += 1
        
        candidates.append((score, sent))
    
    # Sort by score and dedupe similar sentences
    candidates.sort(key=lambda x: -x[0])
    
    selected = []
    for score, sent in candidates:
        if len(selected) >= max_bullets:
            break
        # Simple deduplication: skip if too similar to existing
        is_duplicate = False
        for existing in selected:
            # Check word overlap
            sent_words = set(sent.lower().split())
            exist_words = set(existing.lower().split())
            overlap = len(sent_words & exist_words) / max(len(sent_words), 1)
            if overlap > 0.7:
                is_duplicate = True
                break
        
        if not is_duplicate:
            selected.append(sent)
    
    return selected


async def _llm_summarize(text: str, max_bullets: int) -> Optional[list[str]]:
    """
    Create an LLM-powered summary.
    Returns None if LLM is not available or fails.
    """
    try:
        from app.llm.config import get_llm_config
        from app.llm.client import get_llm_client
        
        config = get_llm_config()
        if config.planner_mode != "llm" or not config.api_key:
            return None
        
        client = get_llm_client()
        
        # Truncate text for LLM
        truncated_text = text[:8000]
        
        prompt = f"""Summarize the following text in exactly {max_bullets} bullet points.
Each bullet should be a complete, informative sentence.
Return ONLY a JSON array of strings, nothing else.

Text:
{truncated_text}

JSON array:"""
        
        # Use the LLM client to generate
        import json
        import httpx
        
        if config.provider == "openai":
            api_url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.model or "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.3,
            }
            
            async with httpx.AsyncClient(timeout=20) as http_client:
                response = await http_client.post(api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                
                # Parse JSON array
                bullets = json.loads(content)
                if isinstance(bullets, list) and all(isinstance(b, str) for b in bullets):
                    return bullets[:max_bullets]
        
        return None
        
    except Exception as e:
        logger.warning(f"llm_summarize_failed error_type={type(e).__name__}")
        return None


async def tool_web_summarize(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Summarize text into bullet points.
    Uses LLM if available, otherwise heuristic.
    
    Input:
        {"text": "plain text...", "max_bullets": 8}
    
    Output:
        {"bullets": ["..."], "notes": "...", "method": "llm" | "heuristic"}
    """
    text = input_data.get("text")
    if not text or not isinstance(text, str):
        raise ValueError("Missing or invalid 'text' in input")
    
    max_bullets = min(input_data.get("max_bullets", DEFAULT_MAX_BULLETS), 15)
    
    # Try LLM first
    bullets = await _llm_summarize(text, max_bullets)
    method = "llm"
    notes = None
    
    if bullets is None:
        # Fall back to heuristic
        bullets = _heuristic_summarize(text, max_bullets)
        method = "heuristic"
        notes = "Summary generated using text extraction heuristics."
    
    logger.info(f"web_summarize text_len={len(text)} bullets={len(bullets)} method={method}")
    
    result = {
        "bullets": bullets,
        "method": method,
    }
    if notes:
        result["notes"] = notes
    
    return result


# Tool registry for web tools
WEB_TOOLS = {
    "web_search": tool_web_search,
    "web_page_text": tool_web_page_text,
    "web_summarize": tool_web_summarize,
}
