"""
Web tools for autonomous agents.

Enables agents to:
- Search the web (DuckDuckGo - free, no API key needed)
- Fetch and read web pages
- Extract structured data
- Browse like a human
"""
import logging
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

# =============================================================================
# Web Search (DuckDuckGo - Free)
# =============================================================================

def web_search(query: str, num_results: int = 10, region: str = "wt-wt") -> List[Dict[str, str]]:
    """
    Search the web using DuckDuckGo (free, no API key).

    Args:
        query: Search query
        num_results: Number of results to return (max 50)
        region: Region code (wt-wt = worldwide, us-en = US, etc.)

    Returns:
        List of search results with title, url, snippet
    """
    try:
        results = []

        with DDGS() as ddgs:
            search_results = ddgs.text(
                keywords=query,
                region=region,
                safesearch="off",
                max_results=min(num_results, 50)
            )

            for r in search_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })

        logger.info(f"web_search query='{query}' results={len(results)}")
        return results

    except Exception as e:
        logger.error(f"web_search_error query='{query}': {type(e).__name__}: {str(e)}")
        return []


def web_search_news(query: str, num_results: int = 10) -> List[Dict[str, str]]:
    """
    Search for news articles using DuckDuckGo.

    Args:
        query: Search query
        num_results: Number of results

    Returns:
        List of news results
    """
    try:
        results = []

        with DDGS() as ddgs:
            news_results = ddgs.news(
                keywords=query,
                safesearch="off",
                max_results=min(num_results, 50)
            )

            for r in news_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("body", ""),
                    "date": r.get("date", ""),
                    "source": r.get("source", ""),
                })

        logger.info(f"web_search_news query='{query}' results={len(results)}")
        return results

    except Exception as e:
        logger.error(f"web_search_news_error query='{query}': {type(e).__name__}: {str(e)}")
        return []


# =============================================================================
# Web Fetching & Extraction
# =============================================================================

async def fetch_url(url: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Fetch a web page and extract its content.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Dict with title, text, links, and metadata
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            if response.status_code != 200:
                logger.warning(f"fetch_url status={response.status_code} url={url}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "url": url,
                }

            # Parse HTML
            soup = BeautifulSoup(response.text, "lxml")

            # Extract title
            title = soup.title.string if soup.title else ""

            # Extract main text (remove scripts, styles)
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            text = soup.get_text(separator="\n", strip=True)

            # Extract links
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http"):
                    links.append({
                        "text": a.get_text(strip=True),
                        "url": href,
                    })

            # Extract metadata
            meta_description = ""
            meta_desc_tag = soup.find("meta", attrs={"name": "description"})
            if meta_desc_tag and meta_desc_tag.get("content"):
                meta_description = meta_desc_tag["content"]

            logger.info(f"fetch_url success url={url} text_length={len(text)}")

            return {
                "success": True,
                "url": url,
                "title": title,
                "text": text[:50000],  # Limit to 50k chars
                "meta_description": meta_description,
                "links": links[:100],  # Limit to 100 links
                "text_length": len(text),
            }

    except httpx.TimeoutException:
        logger.warning(f"fetch_url timeout url={url}")
        return {
            "success": False,
            "error": "Timeout",
            "url": url,
        }
    except Exception as e:
        logger.error(f"fetch_url_error url={url}: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "url": url,
        }


async def extract_data(url: str, selectors: Dict[str, str]) -> Dict[str, Any]:
    """
    Extract structured data from a web page using CSS selectors.

    Args:
        url: URL to scrape
        selectors: Dict of {field_name: css_selector}

    Returns:
        Dict with extracted data
    """
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                }

            soup = BeautifulSoup(response.text, "lxml")

            data = {}
            for field, selector in selectors.items():
                elements = soup.select(selector)
                if elements:
                    if len(elements) == 1:
                        data[field] = elements[0].get_text(strip=True)
                    else:
                        data[field] = [el.get_text(strip=True) for el in elements]
                else:
                    data[field] = None

            logger.info(f"extract_data url={url} fields={list(data.keys())}")

            return {
                "success": True,
                "url": url,
                "data": data,
            }

    except Exception as e:
        logger.error(f"extract_data_error url={url}: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Platform-Specific Searches
# =============================================================================

def search_freelance_jobs(keywords: str, platform: str = "all") -> List[Dict[str, str]]:
    """
    Search for freelance jobs on platforms like Upwork, Fiverr, Freelancer.

    Args:
        keywords: Job keywords (e.g., "python developer", "content writer")
        platform: "upwork", "fiverr", "freelancer", or "all"

    Returns:
        List of job opportunities
    """
    queries = []

    if platform in ["upwork", "all"]:
        queries.append(f"site:upwork.com {keywords}")
    if platform in ["fiverr", "all"]:
        queries.append(f"site:fiverr.com {keywords} gigs")
    if platform in ["freelancer", "all"]:
        queries.append(f"site:freelancer.com {keywords} jobs")

    all_results = []

    for query in queries:
        results = web_search(query, num_results=10)
        all_results.extend(results)
        time.sleep(1)  # Rate limiting

    logger.info(f"search_freelance_jobs keywords='{keywords}' platform={platform} results={len(all_results)}")
    return all_results


def search_content_platforms(topic: str) -> List[Dict[str, str]]:
    """
    Search for content opportunities on Medium, Dev.to, Hashnode, etc.

    Args:
        topic: Content topic

    Returns:
        List of platform opportunities
    """
    queries = [
        f"site:medium.com {topic} programming",
        f"site:dev.to {topic}",
        f"site:hashnode.com {topic}",
    ]

    all_results = []

    for query in queries:
        results = web_search(query, num_results=5)
        all_results.extend(results)
        time.sleep(1)

    logger.info(f"search_content_platforms topic='{topic}' results={len(all_results)}")
    return all_results


def search_saas_ideas(niche: str = "") -> List[Dict[str, str]]:
    """
    Search for SaaS ideas and opportunities.

    Args:
        niche: Specific niche (optional)

    Returns:
        List of SaaS opportunities
    """
    queries = [
        f"SaaS ideas {niche} 2025",
        f"micro SaaS opportunities {niche}",
        f"profitable SaaS {niche}",
        f"indie hacker SaaS {niche}",
    ]

    all_results = []

    for query in queries:
        results = web_search(query.strip(), num_results=10)
        all_results.extend(results)
        time.sleep(1)

    logger.info(f"search_saas_ideas niche='{niche}' results={len(all_results)}")
    return all_results


# =============================================================================
# Market Research Helpers
# =============================================================================

async def analyze_competitor(url: str) -> Dict[str, Any]:
    """
    Analyze a competitor's website.

    Args:
        url: Competitor URL

    Returns:
        Analysis with pricing, features, etc.
    """
    result = await fetch_url(url)

    if not result.get("success"):
        return result

    text = result.get("text", "").lower()

    # Extract pricing signals
    pricing = {
        "has_pricing": any(word in text for word in ["price", "pricing", "$", "buy", "subscribe"]),
        "has_free_tier": any(word in text for word in ["free", "trial", "free plan"]),
        "monthly_mentioned": "month" in text or "/mo" in text,
    }

    # Extract feature signals
    features = {
        "has_api": "api" in text,
        "has_integrations": "integration" in text,
        "has_automation": "automat" in text,
    }

    return {
        "success": True,
        "url": url,
        "title": result.get("title"),
        "pricing_signals": pricing,
        "feature_signals": features,
        "text_sample": result.get("text", "")[:1000],
    }


def find_trending_topics(category: str = "tech") -> List[str]:
    """
    Find trending topics in a category.

    Args:
        category: Category (tech, business, finance, etc.)

    Returns:
        List of trending topics
    """
    queries = [
        f"{category} trends 2025",
        f"what's trending in {category}",
        f"{category} growth opportunities",
    ]

    topics = set()

    for query in queries:
        results = web_search(query, num_results=5)
        for r in results:
            # Extract potential topics from titles
            title_words = r["title"].split()
            for word in title_words:
                if len(word) > 5 and word[0].isupper():
                    topics.add(word)
        time.sleep(1)

    trending = list(topics)[:20]
    logger.info(f"find_trending_topics category={category} topics={len(trending)}")
    return trending
