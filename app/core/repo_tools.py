"""
GitHub repository tools for the Codebase Builder Mode.
Provides read-only access to GitHub repositories.

Security:
- Read-only operations (no writes)
- Domain allowlist (github.com, raw.githubusercontent.com)
- File size limits
- Rate limiting (respects GitHub API limits)
- No authentication secrets exposed
"""
import base64
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse, quote

import httpx

from app.core.cache import tool_cache, DEFAULT_TTL_SECONDS
from app.core.rate_limit import rate_limiter, RateLimitError

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Security: Domain allowlist
ALLOWED_DOMAINS = {
    "github.com",
    "api.github.com",
    "raw.githubusercontent.com",
}

# File size limits
MAX_FILE_SIZE = 512 * 1024  # 512KB per file
MAX_TREE_ENTRIES = 10000  # Max entries in tree response
MAX_SEARCH_RESULTS = 100  # Max search results

# Rate limits (requests per minute)
GITHUB_RATE_LIMIT_AUTHENTICATED = 60  # With token
GITHUB_RATE_LIMIT_UNAUTHENTICATED = 10  # Without token

# Timeouts
HTTP_TIMEOUT = 30  # seconds

# Cache TTL
REPO_CACHE_TTL = 300  # 5 minutes for repo metadata
FILE_CACHE_TTL = 600  # 10 minutes for file contents
TREE_CACHE_TTL = 300  # 5 minutes for tree

# User agent
USER_AGENT = "AgentService-Builder/1.0 (+https://github.com/agent-service)"


def _get_github_token() -> Optional[str]:
    """Get GitHub token from environment (optional, for higher rate limits)."""
    return os.environ.get("GITHUB_TOKEN")


def _get_http_client() -> httpx.AsyncClient:
    """Create HTTP client with GitHub headers."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    token = _get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    return httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        headers=headers,
        follow_redirects=True,
    )


def _validate_github_url(url: str) -> bool:
    """Validate that URL is from allowed GitHub domains."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        return hostname.lower() in ALLOWED_DOMAINS
    except Exception:
        return False


def _validate_repo_format(owner: str, repo: str) -> bool:
    """Validate repository owner/repo format."""
    # GitHub username/repo format: alphanumeric, hyphens, underscores
    pattern = r"^[a-zA-Z0-9_-]+$"
    return bool(re.match(pattern, owner)) and bool(re.match(pattern, repo))


def _compute_cache_key(operation: str, params: dict[str, Any]) -> str:
    """Compute cache key for repository operations."""
    normalized = json.dumps({"op": operation, **params}, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()


# =============================================================================
# Repository Tools
# =============================================================================

async def repo_get_tree(
    owner: str,
    repo: str,
    ref: str = "HEAD",
    path: str = "",
    recursive: bool = True,
) -> dict[str, Any]:
    """
    Get the file tree of a GitHub repository.
    
    Args:
        owner: Repository owner (username or org)
        repo: Repository name
        ref: Git reference (branch, tag, or commit SHA)
        path: Subdirectory path (optional)
        recursive: Include subdirectories recursively
    
    Returns:
        {
            "owner": "...",
            "repo": "...",
            "ref": "...",
            "path": "...",
            "tree": [
                {"path": "src/main.py", "type": "file", "size": 1234},
                {"path": "src/utils/", "type": "dir"},
                ...
            ],
            "truncated": false,
            "total_entries": 42
        }
    """
    # Validate inputs
    if not _validate_repo_format(owner, repo):
        return {"error": "Invalid repository format"}
    
    # Check rate limit
    rate_key = "github_api"
    if not rate_limiter.try_acquire(rate_key):
        return {"error": "Rate limit exceeded for GitHub API"}
    
    # Check cache
    cache_key = _compute_cache_key("tree", {"owner": owner, "repo": repo, "ref": ref, "path": path})
    cached = tool_cache.get("repo_tree", {"key": cache_key})
    if cached:
        return cached
    
    async with _get_http_client() as client:
        try:
            # First get the ref SHA if needed
            if ref == "HEAD":
                ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/main"
                ref_resp = await client.get(ref_url)
                if ref_resp.status_code == 404:
                    # Try master branch
                    ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/master"
                    ref_resp = await client.get(ref_url)
                
                if ref_resp.status_code != 200:
                    return {"error": f"Failed to resolve ref: {ref_resp.status_code}"}
                
                ref_data = ref_resp.json()
                sha = ref_data.get("object", {}).get("sha", "")
            else:
                sha = ref
            
            # Get tree
            recursive_param = "1" if recursive else "0"
            tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{sha}?recursive={recursive_param}"
            
            resp = await client.get(tree_url)
            
            if resp.status_code == 404:
                return {"error": f"Repository or ref not found: {owner}/{repo}@{ref}"}
            elif resp.status_code == 403:
                return {"error": "GitHub API rate limit exceeded"}
            elif resp.status_code != 200:
                return {"error": f"GitHub API error: {resp.status_code}"}
            
            data = resp.json()
            
            # Filter by path if specified
            tree_items = data.get("tree", [])
            if path:
                path_prefix = path.rstrip("/") + "/"
                tree_items = [
                    item for item in tree_items
                    if item.get("path", "").startswith(path_prefix) or item.get("path") == path.rstrip("/")
                ]
            
            # Limit entries
            truncated = len(tree_items) > MAX_TREE_ENTRIES
            tree_items = tree_items[:MAX_TREE_ENTRIES]
            
            # Format output
            formatted_tree = []
            for item in tree_items:
                entry = {
                    "path": item.get("path", ""),
                    "type": "dir" if item.get("type") == "tree" else "file",
                }
                if item.get("size"):
                    entry["size"] = item["size"]
                formatted_tree.append(entry)
            
            result = {
                "owner": owner,
                "repo": repo,
                "ref": sha[:12] if len(sha) > 12 else sha,
                "path": path,
                "tree": formatted_tree,
                "truncated": truncated or data.get("truncated", False),
                "total_entries": len(formatted_tree),
            }
            
            # Cache result
            tool_cache.set("repo_tree", {"key": cache_key}, result, ttl_seconds=TREE_CACHE_TTL)
            
            return result
            
        except httpx.TimeoutException:
            return {"error": "GitHub API request timed out"}
        except Exception as e:
            logger.error(f"repo_tree_error: {type(e).__name__}")
            return {"error": f"Failed to fetch repository tree: {type(e).__name__}"}


async def repo_get_file(
    owner: str,
    repo: str,
    path: str,
    ref: str = "HEAD",
) -> dict[str, Any]:
    """
    Get the contents of a file from a GitHub repository.
    
    Args:
        owner: Repository owner
        repo: Repository name
        path: File path within the repository
        ref: Git reference (branch, tag, or commit SHA)
    
    Returns:
        {
            "owner": "...",
            "repo": "...",
            "path": "...",
            "ref": "...",
            "content": "file contents...",
            "encoding": "utf-8",
            "size": 1234,
            "truncated": false
        }
    """
    # Validate inputs
    if not _validate_repo_format(owner, repo):
        return {"error": "Invalid repository format"}
    
    if not path or path.startswith("/"):
        return {"error": "Invalid file path"}
    
    # Check rate limit
    rate_key = "github_api"
    if not rate_limiter.try_acquire(rate_key):
        return {"error": "Rate limit exceeded for GitHub API"}
    
    # Check cache
    cache_key = _compute_cache_key("file", {"owner": owner, "repo": repo, "path": path, "ref": ref})
    cached = tool_cache.get("repo_file", {"key": cache_key})
    if cached:
        return cached
    
    async with _get_http_client() as client:
        try:
            # Use contents API
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(path)}"
            params = {}
            if ref != "HEAD":
                params["ref"] = ref
            
            resp = await client.get(url, params=params)
            
            if resp.status_code == 404:
                return {"error": f"File not found: {path}"}
            elif resp.status_code == 403:
                return {"error": "GitHub API rate limit exceeded"}
            elif resp.status_code != 200:
                return {"error": f"GitHub API error: {resp.status_code}"}
            
            data = resp.json()
            
            # Check if it's a file (not directory)
            if data.get("type") != "file":
                return {"error": f"Path is not a file: {path}"}
            
            # Check file size
            size = data.get("size", 0)
            if size > MAX_FILE_SIZE:
                return {
                    "error": f"File too large: {size} bytes (max {MAX_FILE_SIZE})",
                    "size": size,
                    "truncated": True,
                }
            
            # Decode content
            content_b64 = data.get("content", "")
            encoding = data.get("encoding", "base64")
            
            if encoding == "base64":
                try:
                    content = base64.b64decode(content_b64).decode("utf-8")
                except UnicodeDecodeError:
                    return {"error": "File is not valid UTF-8 text", "size": size}
            else:
                content = content_b64
            
            result = {
                "owner": owner,
                "repo": repo,
                "path": path,
                "ref": ref,
                "content": content,
                "encoding": "utf-8",
                "size": size,
                "truncated": False,
            }
            
            # Cache result
            tool_cache.set("repo_file", {"key": cache_key}, result, ttl_seconds=FILE_CACHE_TTL)
            
            return result
            
        except httpx.TimeoutException:
            return {"error": "GitHub API request timed out"}
        except Exception as e:
            logger.error(f"repo_file_error: {type(e).__name__}")
            return {"error": f"Failed to fetch file: {type(e).__name__}"}


async def repo_search_code(
    owner: str,
    repo: str,
    query: str,
    path: Optional[str] = None,
    extension: Optional[str] = None,
    max_results: int = 30,
) -> dict[str, Any]:
    """
    Search for code in a GitHub repository.
    
    Args:
        owner: Repository owner
        repo: Repository name
        query: Search query
        path: Limit search to path (optional)
        extension: Limit to file extension (optional)
        max_results: Maximum results to return
    
    Returns:
        {
            "owner": "...",
            "repo": "...",
            "query": "...",
            "results": [
                {
                    "path": "src/main.py",
                    "matches": ["line with match...", ...],
                    "url": "https://github.com/..."
                }
            ],
            "total_count": 42
        }
    """
    # Validate inputs
    if not _validate_repo_format(owner, repo):
        return {"error": "Invalid repository format"}
    
    if not query or len(query) < 2:
        return {"error": "Search query must be at least 2 characters"}
    
    # Check rate limit (search is more expensive)
    rate_key = "github_search"
    if not rate_limiter.try_acquire(rate_key, tokens=2):
        return {"error": "Rate limit exceeded for GitHub Search API"}
    
    # Build search query
    search_query = f"{query} repo:{owner}/{repo}"
    if path:
        search_query += f" path:{path}"
    if extension:
        search_query += f" extension:{extension}"
    
    # Check cache
    cache_key = _compute_cache_key("search", {"q": search_query, "max": max_results})
    cached = tool_cache.get("repo_search", {"key": cache_key})
    if cached:
        return cached
    
    async with _get_http_client() as client:
        try:
            url = "https://api.github.com/search/code"
            params = {
                "q": search_query,
                "per_page": min(max_results, MAX_SEARCH_RESULTS),
            }
            
            resp = await client.get(url, params=params)
            
            if resp.status_code == 403:
                return {"error": "GitHub API rate limit exceeded"}
            elif resp.status_code == 422:
                return {"error": "Invalid search query"}
            elif resp.status_code != 200:
                return {"error": f"GitHub API error: {resp.status_code}"}
            
            data = resp.json()
            
            # Format results
            results = []
            for item in data.get("items", [])[:max_results]:
                results.append({
                    "path": item.get("path", ""),
                    "name": item.get("name", ""),
                    "url": item.get("html_url", ""),
                    "sha": item.get("sha", "")[:12],
                })
            
            result = {
                "owner": owner,
                "repo": repo,
                "query": query,
                "results": results,
                "total_count": data.get("total_count", 0),
            }
            
            # Cache result
            tool_cache.set("repo_search", {"key": cache_key}, result, ttl_seconds=REPO_CACHE_TTL)
            
            return result
            
        except httpx.TimeoutException:
            return {"error": "GitHub API request timed out"}
        except Exception as e:
            logger.error(f"repo_search_error: {type(e).__name__}")
            return {"error": f"Failed to search repository: {type(e).__name__}"}


async def repo_get_readme(
    owner: str,
    repo: str,
    ref: str = "HEAD",
) -> dict[str, Any]:
    """
    Get the README file from a GitHub repository.
    
    Args:
        owner: Repository owner
        repo: Repository name
        ref: Git reference
    
    Returns:
        {
            "owner": "...",
            "repo": "...",
            "path": "README.md",
            "content": "# Project...",
            "size": 1234
        }
    """
    # Validate inputs
    if not _validate_repo_format(owner, repo):
        return {"error": "Invalid repository format"}
    
    # Check rate limit
    if not rate_limiter.try_acquire("github_api"):
        return {"error": "Rate limit exceeded for GitHub API"}
    
    async with _get_http_client() as client:
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/readme"
            params = {}
            if ref != "HEAD":
                params["ref"] = ref
            
            resp = await client.get(url, params=params)
            
            if resp.status_code == 404:
                return {"error": "README not found"}
            elif resp.status_code == 403:
                return {"error": "GitHub API rate limit exceeded"}
            elif resp.status_code != 200:
                return {"error": f"GitHub API error: {resp.status_code}"}
            
            data = resp.json()
            
            # Decode content
            content_b64 = data.get("content", "")
            try:
                content = base64.b64decode(content_b64).decode("utf-8")
            except Exception:
                return {"error": "Failed to decode README content"}
            
            return {
                "owner": owner,
                "repo": repo,
                "path": data.get("path", "README.md"),
                "content": content,
                "size": data.get("size", len(content)),
            }
            
        except httpx.TimeoutException:
            return {"error": "GitHub API request timed out"}
        except Exception as e:
            logger.error(f"repo_readme_error: {type(e).__name__}")
            return {"error": f"Failed to fetch README: {type(e).__name__}"}


async def repo_get_info(
    owner: str,
    repo: str,
) -> dict[str, Any]:
    """
    Get basic information about a GitHub repository.
    
    Args:
        owner: Repository owner
        repo: Repository name
    
    Returns:
        {
            "owner": "...",
            "repo": "...",
            "description": "...",
            "language": "Python",
            "default_branch": "main",
            "stars": 1234,
            "forks": 56,
            "topics": ["python", "api"],
            "is_private": false
        }
    """
    # Validate inputs
    if not _validate_repo_format(owner, repo):
        return {"error": "Invalid repository format"}
    
    # Check rate limit
    if not rate_limiter.try_acquire("github_api"):
        return {"error": "Rate limit exceeded for GitHub API"}
    
    # Check cache
    cache_key = _compute_cache_key("info", {"owner": owner, "repo": repo})
    cached = tool_cache.get("repo_info", {"key": cache_key})
    if cached:
        return cached
    
    async with _get_http_client() as client:
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            resp = await client.get(url)
            
            if resp.status_code == 404:
                return {"error": f"Repository not found: {owner}/{repo}"}
            elif resp.status_code == 403:
                return {"error": "GitHub API rate limit exceeded"}
            elif resp.status_code != 200:
                return {"error": f"GitHub API error: {resp.status_code}"}
            
            data = resp.json()
            
            result = {
                "owner": owner,
                "repo": repo,
                "full_name": data.get("full_name", f"{owner}/{repo}"),
                "description": data.get("description", ""),
                "language": data.get("language"),
                "default_branch": data.get("default_branch", "main"),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "topics": data.get("topics", []),
                "is_private": data.get("private", False),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            }
            
            # Cache result
            tool_cache.set("repo_info", {"key": cache_key}, result, ttl_seconds=REPO_CACHE_TTL)
            
            return result
            
        except httpx.TimeoutException:
            return {"error": "GitHub API request timed out"}
        except Exception as e:
            logger.error(f"repo_info_error: {type(e).__name__}")
            return {"error": f"Failed to fetch repository info: {type(e).__name__}"}


# =============================================================================
# Tool Registry for Builder Mode
# =============================================================================

REPO_TOOLS = {
    "repo_get_tree": repo_get_tree,
    "repo_get_file": repo_get_file,
    "repo_search_code": repo_search_code,
    "repo_get_readme": repo_get_readme,
    "repo_get_info": repo_get_info,
}


async def execute_repo_tool(tool_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute a repository tool by name."""
    if tool_name not in REPO_TOOLS:
        return {"error": f"Unknown repository tool: {tool_name}"}
    
    tool_func = REPO_TOOLS[tool_name]
    return await tool_func(**input_data)
