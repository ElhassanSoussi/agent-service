# Phase 8: Web Research Tools

This phase adds a **Skills Pack #1** with web research capabilities to the agent service.

## New Tools

### `web_search`
Search the web using DuckDuckGo HTML interface (no API key required).

**Input:**
```json
{
  "query": "search query string",
  "max_results": 5
}
```

**Output:**
```json
{
  "results": [
    {
      "title": "Page Title",
      "url": "https://example.com",
      "snippet": "Brief description..."
    }
  ]
}
```

### `web_page_text`
Fetch a web page and extract readable text content.

**Input:**
```json
{
  "url": "https://example.com/article",
  "max_chars": 20000
}
```

**Output:**
```json
{
  "url": "https://example.com/article",
  "title": "Page Title",
  "text": "Extracted text content...",
  "truncated": false
}
```

### `web_summarize`
Summarize text into bullet points. Uses LLM if enabled, otherwise heuristic extraction.

**Input:**
```json
{
  "text": "Long text to summarize...",
  "max_bullets": 5
}
```

**Output:**
```json
{
  "bullets": [
    "Key point 1",
    "Key point 2",
    "Key point 3"
  ],
  "method": "heuristic"
}
```

## Security Features

### HTTPS Only
- All URLs must use HTTPS protocol
- HTTP URLs are rejected with an error

### Blocked IP Addresses
Private and internal IP ranges are blocked:
- `127.0.0.0/8` (localhost)
- `10.0.0.0/8` (private)
- `172.16.0.0/12` (private)
- `192.168.0.0/16` (private)
- `169.254.0.0/16` (link-local)
- `::1/128` (IPv6 localhost)
- `fc00::/7` (IPv6 private)

### Blocked Hostnames
- `localhost`
- `localhost.localdomain`

### Size Limits
- Maximum download size: 1MB
- Maximum text extraction: 50,000 characters
- Response timeout: 15 seconds
- Maximum redirects: 3

## Caching

Web tool outputs are cached in SQLite to reduce redundant requests.

### Cache TTLs
| Tool | TTL |
|------|-----|
| `web_search` | 1 hour (3600s) |
| `web_page_text` | 30 minutes (1800s) |
| `http_fetch` | 5 minutes (300s) |

### Cache Features
- SHA256 cache keys from tool name + normalized input
- Automatic cleanup of expired entries
- Maximum 5,000 cache entries
- Sensitive data (headers, tokens) stripped before caching

## Rate Limiting

Token bucket rate limiter prevents abuse and respects external service limits.

### Rate Limits (requests per minute)
| Tool | Limit |
|------|-------|
| `web_search` | 10/min |
| `web_page_text` | 20/min |
| `web_summarize` | 20/min |
| `http_fetch` | 30/min |
| `echo` | 60/min |

### Behavior
- Rate limited requests return `RateLimitError`
- Tokens refill continuously over time
- Per-tool independent buckets

## Citations Tracking

When using web tools, the agent tracks source URLs for citation purposes.

### Citation Format
```json
{
  "citations": [
    {"url": "https://example.com/article1", "title": "Article Title"},
    {"url": "https://example.com/article2", "title": null}
  ]
}
```

### Where Citations Appear
- In the `GET /agent/result/{job_id}` response
- Automatically extracted from `web_search` and `web_page_text` tool outputs

## API Updates

### Updated Endpoint: `GET /agent/result/{job_id}`

New query parameter:
- `include_steps` (boolean, default: false) - Include step details in response

New response fields:
- `bullets` - List of summary bullet points (if web_summarize was used)
- `citations` - List of source URLs with titles
- `steps` - Step details (if `include_steps=true`)

**Example Response:**
```json
{
  "job_id": "abc123",
  "status": "done",
  "mode": "agent",
  "final_output": "Summary of research findings...",
  "bullets": [
    "Key finding 1",
    "Key finding 2"
  ],
  "citations": [
    {"url": "https://example.com/source1", "title": "Source Article"},
    {"url": "https://example.com/source2", "title": null}
  ],
  "error": null
}
```

## Example Usage

### Web Search + Summarize
```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "agent",
    "prompt": "Search for recent news about Python 3.12 and summarize the key features"
  }'
```

### Fetch and Extract Page Text
```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "agent",
    "prompt": "Get the main content from https://example.com/article"
  }'
```

### Get Result with Citations
```bash
curl "http://localhost:8000/agent/result/{job_id}?include_steps=true" \
  -H "Authorization: Bearer $API_KEY"
```

## Files Added/Modified

### New Files
- `app/core/cache.py` - SQLite-backed cache with TTL
- `app/core/rate_limit.py` - Token bucket rate limiter
- `app/core/web_tools.py` - Web research tools (search, fetch, summarize)
- `tests/test_web_tools.py` - Tests for Phase 8 features
- `docs/PHASE8.md` - This documentation

### Modified Files
- `requirements.txt` - Added `beautifulsoup4`, `lxml`
- `app/schemas/agent.py` - Added `Citation` model, updated `ToolName` enum
- `app/core/tools.py` - Integrated web tools, cache, rate limiting
- `app/core/planner.py` - Added web tool planning support
- `app/core/executor.py` - Citations tracking, web tool handling
- `app/api/agent.py` - Updated result endpoint with citations

## Testing

Run the Phase 8 tests:
```bash
python -m pytest tests/test_web_tools.py -v
```

Run all tests:
```bash
python -m pytest tests/ -v
```

## Dependencies

Added to `requirements.txt`:
```
beautifulsoup4==4.12.3
lxml==5.3.0
```

Install with:
```bash
pip install -r requirements.txt
```
