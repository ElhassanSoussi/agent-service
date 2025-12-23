# Agent Service API Documentation

## Overview

The Agent Service provides an async job execution API for running tools in the background. All endpoints (except `/health`) require API key authentication.

**Base URL:** `https://agent-x-one.com`

### Persistence

Jobs are stored in a SQLite database and persist across service restarts.

**Job Retention:** Jobs are automatically deleted after **24 hours**. No manual cleanup required.

---

## Authentication

Include the API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: YOUR_API_KEY" https://agent-x-one.com/...
```

### Responses

| Status | Meaning |
|--------|---------|
| `401`  | Missing `X-API-Key` header |
| `403`  | Invalid API key |

---

## Endpoints

### Health Check (Public)

```http
GET /health
```

**Response:**
```json
{"status": "ok"}
```

---

## Execution Modes

The API supports two execution modes:

### Tool Mode (Default)

Direct tool execution. Backwards compatible with existing clients.

```json
{"tool": "echo", "input": {"message": "hello"}}
```

### Agent Mode (New)

Natural language prompt that creates and executes a plan.

```json
{
  "mode": "agent",
  "prompt": "Fetch and summarize https://example.com",
  "max_steps": 3,
  "allowed_tools": ["echo", "http_fetch"]
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | - | Must be `"agent"` |
| `prompt` | string | required | Natural language request (max 4096 chars) |
| `max_steps` | int | 3 | Maximum steps in plan (1-5) |
| `allowed_tools` | array | all | Tools the agent can use |

---

## Endpoints

### Submit a Job

```http
POST /agent/run
Content-Type: application/json
X-API-Key: YOUR_API_KEY
```

**Tool Mode Request:**
```json
{
  "tool": "echo",
  "input": {"message": "hello"}
}
```

**Agent Mode Request:**
```json
{
  "mode": "agent",
  "prompt": "fetch https://httpbin.org/get"
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "mode": "tool",
  "created_at": "2025-12-18T00:00:00.000000Z"
}
```

---

### Check Job Status

```http
GET /agent/status/{job_id}
X-API-Key: YOUR_API_KEY
```

**Response (200 OK):**
```json
{
  "job_id": "uuid",
  "status": "done",
  "mode": "agent",
  "tool": null,
  "prompt": "fetch https://example.com",
  "created_at": "2025-12-18T00:00:00.000000Z",
  "started_at": "2025-12-18T00:00:00.000000Z",
  "completed_at": "2025-12-18T00:00:00.000001Z",
  "duration_ms": 1500,
  "output": {"result": "..."},
  "error": null,
  "step_count": 1
}
```

**Job Status Values:**
| Status | Description |
|--------|-------------|
| `queued` | Job accepted, waiting to run |
| `running` | Job is currently executing |
| `done` | Job completed successfully |
| `error` | Job failed (see `error` field) |

**Error Response (404):**
```json
{"detail": "Job not found"}
```

---

### Get Job Steps (Agent Mode)

```http
GET /agent/steps/{job_id}
X-API-Key: YOUR_API_KEY
```

Returns execution steps for an agent-mode job.

**Response (200 OK):**
```json
{
  "job_id": "uuid",
  "mode": "agent",
  "steps": [
    {
      "step_id": "uuid",
      "step_number": 1,
      "tool": "http_fetch",
      "status": "done",
      "output_summary": "{\"status_code\": 200, \"byte_length\": 1234}",
      "error": null,
      "created_at": "2025-12-18T00:00:00Z",
      "started_at": "2025-12-18T00:00:00Z",
      "completed_at": "2025-12-18T00:00:01Z",
      "duration_ms": 1500
    }
  ],
  "total_steps": 1
}
```

---

### Get Final Result

```http
GET /agent/result/{job_id}
X-API-Key: YOUR_API_KEY
```

Returns just the final output (useful for agent-mode jobs).

**Response (200 OK):**
```json
{
  "job_id": "uuid",
  "status": "done",
  "mode": "agent",
  "final_output": "Fetched URL (status 200): ...",
  "error": null
}
```

---

### List Jobs

```http
GET /agent/jobs
X-API-Key: YOUR_API_KEY
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Max items (1-100) |
| `offset` | int | 0 | Pagination offset |
| `status` | string | - | Filter: `queued`, `running`, `done`, `error` |
| `tool` | string | - | Filter: `echo`, `http_fetch` |

**Response (200 OK):**
```json
{
  "items": [
    {
      "job_id": "abc-123",
      "status": "done",
      "tool": "echo",
      "created_at": "2025-12-18T12:00:00Z",
      "started_at": "2025-12-18T12:00:00Z",
      "completed_at": "2025-12-18T12:00:01Z",
      "duration_ms": 5,
      "has_output": true,
      "has_error": false
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 1
}
```

> **Note:** List responses do NOT include `input` or `output` bodies. Use `/agent/status/{job_id}` to retrieve full details.

---

### Delete a Job

```http
DELETE /agent/jobs/{job_id}
X-API-Key: YOUR_API_KEY
```

**Response (200 OK):**
```json
{"deleted": true}
```

**Error Response (404):**
```json
{"detail": "Job not found"}
```

---

### Cancel a Job

```http
POST /agent/cancel/{job_id}
X-API-Key: YOUR_API_KEY
```

Cancels a job that is `queued` or `running`. Sets status to `error` with `error="cancelled"`.

**Response (200 OK):**
```json
{
  "job_id": "abc-123",
  "status": "error",
  "message": "Job cancelled successfully"
}
```

**Error Response (409 Conflict):**
```json
{"detail": "Cannot cancel job with status 'done'"}
```

> **Note:** Cancellation is best-effort. A running job's background task may complete before the cancellation takes effect.

---

## Available Tools

### 1. `echo`

Returns the input unchanged. Useful for testing.

**Input:**
```json
{
  "tool": "echo",
  "input": { "any": "data", "you": "want" }
}
```

**Output:**
```json
{ "any": "data", "you": "want" }
```

---

### 2. `http_fetch`

Fetches content from an HTTPS URL.

**Input:**
```json
{
  "tool": "http_fetch",
  "input": { "url": "https://example.com/api/data" }
}
```

**Output (Success):**
```json
{
  "status_code": 200,
  "content_type": "application/json",
  "body": "...",
  "truncated": false
}
```

**Security Restrictions:**
- **HTTPS only** — HTTP URLs are rejected
- **No private IPs** — Blocks `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `localhost`
- **Timeout:** 10 seconds
- **Max size:** 64 KB (truncated if exceeded)
- **No redirects:** Redirects are not followed

**Example Error:**
```json
{
  "error": "URL must use HTTPS scheme"
}
```

---

### 3. `web_search`

Search the web using DuckDuckGo (no API key required).

**Input:**
```json
{
  "tool": "web_search",
  "input": {
    "query": "Python 3.12 new features",
    "max_results": 5
  }
}
```

**Output:**
```json
{
  "results": [
    {
      "title": "What's New In Python 3.12",
      "url": "https://docs.python.org/3/whatsnew/3.12.html",
      "snippet": "This article explains the new features in Python 3.12..."
    }
  ]
}
```

**Security:** HTTPS results only. Rate limited to 10 requests/minute.

---

### 4. `web_page_text`

Fetch a web page and extract readable text content.

**Input:**
```json
{
  "tool": "web_page_text",
  "input": {
    "url": "https://example.com/article",
    "max_chars": 20000
  }
}
```

**Output:**
```json
{
  "url": "https://example.com/article",
  "title": "Article Title",
  "text": "Extracted article text content...",
  "truncated": false
}
```

**Security:** HTTPS only, private IPs blocked, 1MB max download, 15s timeout.

---

### 5. `web_summarize`

Summarize text into bullet points. Uses LLM if enabled, otherwise heuristic.

**Input:**
```json
{
  "tool": "web_summarize",
  "input": {
    "text": "Long text to summarize...",
    "max_bullets": 5
  }
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

---

## Examples

### Bash/cURL

**Submit an echo job:**
```bash
curl -X POST https://agent-x-one.com/agent/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "echo", "input": {"message": "Hello, World!"}}'
```

**Check job status:**
```bash
curl https://agent-x-one.com/agent/status/YOUR_JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

**List jobs (with filters):**
```bash
# List recent 20 jobs
curl "https://agent-x-one.com/agent/jobs" \
  -H "X-API-Key: YOUR_API_KEY"

# List failed jobs only
curl "https://agent-x-one.com/agent/jobs?status=error&limit=10" \
  -H "X-API-Key: YOUR_API_KEY"

# List jobs for a specific tool
curl "https://agent-x-one.com/agent/jobs?tool=http_fetch" \
  -H "X-API-Key: YOUR_API_KEY"
```

**Delete a job:**
```bash
curl -X DELETE https://agent-x-one.com/agent/jobs/YOUR_JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

**Cancel a job:**
```bash
curl -X POST https://agent-x-one.com/agent/cancel/YOUR_JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

**Fetch a URL:**
```bash
curl -X POST https://agent-x-one.com/agent/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "http_fetch", "input": {"url": "https://api.github.com/zen"}}'
```

**Submit an agent job (natural language):**
```bash
curl -X POST https://agent-x-one.com/agent/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode": "agent", "prompt": "fetch https://httpbin.org/get"}'
```

**Get execution steps:**
```bash
curl https://agent-x-one.com/agent/steps/YOUR_JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

**Get final result:**
```bash
curl https://agent-x-one.com/agent/result/YOUR_JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

---

### Python

```python
import httpx
import time

API_KEY = "YOUR_API_KEY"
BASE_URL = "https://agent-x-one.com"
HEADERS = {"X-API-Key": API_KEY}

def submit_job(tool: str, input_data: dict) -> str:
    """Submit a job and return the job_id."""
    resp = httpx.post(
        f"{BASE_URL}/agent/run",
        headers=HEADERS,
        json={"tool": tool, "input": input_data}
    )
    resp.raise_for_status()
    return resp.json()["job_id"]

def wait_for_job(job_id: str, timeout: int = 30) -> dict:
    """Poll until job completes or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        resp = httpx.get(f"{BASE_URL}/agent/status/{job_id}", headers=HEADERS)
        resp.raise_for_status()
        job = resp.json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.5)
    raise TimeoutError(f"Job {job_id} did not complete in {timeout}s")

# Example: Echo tool
job_id = submit_job("echo", {"hello": "world"})
result = wait_for_job(job_id)
print(result["output"])  # {"hello": "world"}

# Example: HTTP fetch
job_id = submit_job("http_fetch", {"url": "https://httpbin.org/get"})
result = wait_for_job(job_id)
print(result["output"]["status_code"])  # 200
```

---

### JavaScript (Node.js)

```javascript
const API_KEY = "YOUR_API_KEY";
const BASE_URL = "https://agent-x-one.com";

async function submitJob(tool, input) {
  const resp = await fetch(`${BASE_URL}/agent/run`, {
    method: "POST",
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ tool, input })
  });
  const data = await resp.json();
  return data.job_id;
}

async function waitForJob(jobId, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const resp = await fetch(`${BASE_URL}/agent/status/${jobId}`, {
      headers: { "X-API-Key": API_KEY }
    });
    const job = await resp.json();
    if (job.status === "done" || job.status === "error") {
      return job;
    }
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error(`Job ${jobId} timed out`);
}

// Example usage
const jobId = await submitJob("echo", { message: "Hello!" });
const result = await waitForJob(jobId);
console.log(result.output); // { message: "Hello!" }
```

---

## Rate Limits

The API enforces rate limiting:
- **10 requests/second** sustained
- **Burst:** 20 requests

Exceeding the limit returns `503 Service Temporarily Unavailable`.

---

## Error Handling

### HTTP Errors

| Status | Meaning |
|--------|---------|
| `400` | Bad request (invalid JSON, missing fields) |
| `401` | Missing API key |
| `403` | Invalid API key |
| `404` | Job not found |
| `422` | Validation error (unknown tool, bad input) |
| `503` | Rate limit exceeded |

### Job Errors

When `status` is `"error"`, the `error` field contains the error message:

```json
{
  "job_id": "...",
  "status": "error",
  "error": "Unknown tool: bad_tool",
  "output": null
}
```

---

## OpenAPI Docs

Interactive API documentation is available at:
- **Swagger UI:** `https://agent-x-one.com/docs`
- **ReDoc:** `https://agent-x-one.com/redoc`

Both require authentication via the `X-API-Key` header.

---

## Testing Persistence

Jobs persist across service restarts. To verify:

```bash
# 1. Submit a job
curl -X POST https://agent-x-one.com/agent/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "echo", "input": {"test": "persistence"}}'
# Returns: {"job_id":"<uuid>","status":"queued",...}

# 2. Note the job_id, then restart the service (admin only):
# sudo systemctl restart agent-service

# 3. Check the job still exists after restart:
curl https://agent-x-one.com/agent/status/<job_id> \
  -H "X-API-Key: YOUR_API_KEY"
# Returns: {"job_id":"<job_id>","status":"done","output":{...},...}
```

---

## Manual Test Checklist

Use this checklist to verify the API is working correctly:

### 1. Create a job
```bash
curl -X POST https://agent-x-one.com/agent/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "echo", "input": {"test": "checklist"}}'
```
✅ Should return 202 with `job_id`

### 2. Confirm job appears in list
```bash
curl "https://agent-x-one.com/agent/jobs?limit=5" \
  -H "X-API-Key: YOUR_API_KEY"
```
✅ Should see the job in `items` array with `has_output: true`

### 3. Fetch job status
```bash
curl https://agent-x-one.com/agent/status/<job_id> \
  -H "X-API-Key: YOUR_API_KEY"
```
✅ Should return full job details with `output`

### 4. Delete the job
```bash
curl -X DELETE https://agent-x-one.com/agent/jobs/<job_id> \
  -H "X-API-Key: YOUR_API_KEY"
```
✅ Should return `{"deleted": true}`

### 5. Confirm job is gone
```bash
curl https://agent-x-one.com/agent/status/<job_id> \
  -H "X-API-Key: YOUR_API_KEY"
```
✅ Should return 404 `{"detail": "Job not found"}`

### 6. Test cancellation (optional)
```bash
# Create a job
curl -X POST https://agent-x-one.com/agent/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "echo", "input": {"test": "cancel"}}'

# Immediately try to cancel (may already be done)
curl -X POST https://agent-x-one.com/agent/cancel/<job_id> \
  -H "X-API-Key: YOUR_API_KEY"
```
✅ Should return 200 with `status: error` or 409 if already completed

### 7. Test Agent Mode
```bash
# Create an agent job
curl -X POST https://agent-x-one.com/agent/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode": "agent", "prompt": "fetch https://httpbin.org/get"}'
```
✅ Should return 202 with `mode: agent`

### 8. Check agent job steps
```bash
curl https://agent-x-one.com/agent/steps/<job_id> \
  -H "X-API-Key: YOUR_API_KEY"
```
✅ Should show steps with `tool: http_fetch` and `status: done`

### 9. Get agent final result
```bash
curl https://agent-x-one.com/agent/result/<job_id> \
  -H "X-API-Key: YOUR_API_KEY"
```
✅ Should return `final_output` with fetched content summary

---

## LLM-Powered Planning (Optional)

The agent service supports optional LLM-powered planning for more intelligent execution plans.

### Enabling LLM Mode

Set environment variables on the server:

```bash
# /etc/agent-service.env
AGENT_PLANNER_MODE=llm
LLM_PROVIDER=openai          # or "anthropic"
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini        # optional
LLM_MAX_TOKENS=500           # optional
LLM_TIMEOUT_S=20             # optional
LLM_MAX_PLAN_STEPS=6         # optional
```

Then restart the service:

```bash
sudo systemctl restart agent-service
```

### Fallback Behavior

If LLM mode is enabled but fails (timeout, invalid response, security violation), the system **automatically falls back** to the rule-based planner.

### Get Plan Details

Check which planner was used and view the generated plan:

```bash
curl https://agent-x-one.com/agent/plan/{job_id} \
  -H "X-API-Key: YOUR_API_KEY"
```

**Response:**
```json
{
  "job_id": "uuid",
  "planner": {
    "mode": "llm",              // or "rules" or "llm_fallback"
    "output": {
      "planner_mode": "llm",
      "step_count": 2,
      "fallback_reason": null   // or reason if fallback occurred
    }
  },
  "plan": {
    "steps": [
      {"tool": "http_fetch", "description": "Fetch the page"},
      {"tool": "echo", "description": "Summarize content"}
    ],
    "total_steps": 2
  }
}
```

### Security Notes

- **LLM_API_KEY is never logged** - Only metadata is logged
- **Only allowlisted tools** - LLM cannot introduce new tools
- **HTTPS-only for http_fetch** - HTTP URLs are rejected
- **Private networks blocked** - localhost, 192.168.x.x, etc.
- **Step limits enforced** - Plans exceeding limits are rejected

See [docs/PHASE7.md](PHASE7.md) for full details.

---

## Multi-Tenant Support (Phase 9)

The Agent Service supports multi-tenancy with per-tenant quotas, API key management, and usage tracking.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_KEY_HASH_SECRET` | Yes (prod) | Secret for HMAC-SHA256 key hashing |
| `AGENT_ADMIN_KEY` | Yes (prod) | Admin API authentication key |
| `AGENT_API_KEY` | No | Legacy single API key (backwards compatible) |

### Authentication

The service supports two authentication methods:

1. **Legacy Mode**: Use `AGENT_API_KEY` environment variable (backwards compatible)
2. **Multi-tenant Mode**: Generate per-tenant API keys via admin API

API keys use the format: `agk_live_<48-random-chars>`

Keys are stored as HMAC-SHA256 hashes, never in plaintext.

---

## Admin API

All admin endpoints require the `X-Admin-Key` header.

### Create Tenant

```http
POST /admin/tenants
Content-Type: application/json
X-Admin-Key: YOUR_ADMIN_KEY
```

**Request:**
```json
{
  "name": "Acme Corp"
}
```

**Response (200 OK):**
```json
{
  "tenant_id": "uuid",
  "name": "Acme Corp",
  "created_at": "2025-12-19T00:00:00.000000Z",
  "max_requests_per_day": 500,
  "max_tool_calls_per_day": 200,
  "max_bytes_fetched_per_day": 5242880
}
```

---

### List Tenants

```http
GET /admin/tenants
X-Admin-Key: YOUR_ADMIN_KEY
```

**Response (200 OK):**
```json
{
  "tenants": [
    {
      "tenant_id": "uuid",
      "name": "Acme Corp",
      "created_at": "2025-12-19T00:00:00.000000Z",
      "max_requests_per_day": 500,
      "max_tool_calls_per_day": 200,
      "max_bytes_fetched_per_day": 5242880
    }
  ]
}
```

---

### Get Tenant Details

```http
GET /admin/tenants/{tenant_id}
X-Admin-Key: YOUR_ADMIN_KEY
```

**Response (200 OK):**
```json
{
  "tenant_id": "uuid",
  "name": "Acme Corp",
  "created_at": "2025-12-19T00:00:00.000000Z",
  "max_requests_per_day": 500,
  "max_tool_calls_per_day": 200,
  "max_bytes_fetched_per_day": 5242880
}
```

---

### Update Tenant Quotas

```http
PUT /admin/tenants/{tenant_id}/quotas
Content-Type: application/json
X-Admin-Key: YOUR_ADMIN_KEY
```

**Request:**
```json
{
  "max_requests_per_day": 1000,
  "max_tool_calls_per_day": 500,
  "max_bytes_fetched_per_day": 10485760
}
```

**Response (200 OK):**
```json
{
  "tenant_id": "uuid",
  "name": "Acme Corp",
  "max_requests_per_day": 1000,
  "max_tool_calls_per_day": 500,
  "max_bytes_fetched_per_day": 10485760
}
```

---

### Create API Key

```http
POST /admin/tenants/{tenant_id}/keys
Content-Type: application/json
X-Admin-Key: YOUR_ADMIN_KEY
```

**Request:**
```json
{
  "name": "Production Key"
}
```

**Response (200 OK):**
```json
{
  "api_key": "agk_live_abc123...",
  "key_prefix": "agk_live_abc123",
  "key_id": "uuid",
  "name": "Production Key",
  "created_at": "2025-12-19T00:00:00.000000Z"
}
```

> ⚠️ **IMPORTANT**: The `api_key` is only returned once. Store it securely.

---

### List API Keys

```http
GET /admin/tenants/{tenant_id}/keys
X-Admin-Key: YOUR_ADMIN_KEY
```

**Response (200 OK):**
```json
{
  "keys": [
    {
      "key_id": "uuid",
      "key_prefix": "agk_live_abc123",
      "name": "Production Key",
      "status": "active",
      "created_at": "2025-12-19T00:00:00.000000Z",
      "last_used_at": "2025-12-19T01:00:00.000000Z"
    }
  ]
}
```

---

### Rotate API Key

```http
POST /admin/tenants/{tenant_id}/keys/{key_id}/rotate
X-Admin-Key: YOUR_ADMIN_KEY
```

**Response (200 OK):**
```json
{
  "api_key": "agk_live_newkey...",
  "key_prefix": "agk_live_newkey",
  "key_id": "uuid",
  "name": "Production Key",
  "rotated_at": "2025-12-19T00:00:00.000000Z"
}
```

---

### Revoke API Key

```http
DELETE /admin/tenants/{tenant_id}/keys/{key_id}
X-Admin-Key: YOUR_ADMIN_KEY
```

**Response (200 OK):**
```json
{
  "message": "Key revoked",
  "key_id": "uuid"
}
```

---

### Get Usage Statistics

```http
GET /admin/tenants/{tenant_id}/usage
X-Admin-Key: YOUR_ADMIN_KEY
```

**Response (200 OK):**
```json
{
  "tenant_id": "uuid",
  "date": "2025-12-19",
  "usage": {
    "requests": 150,
    "jobs": 50,
    "tool_calls": 200,
    "bytes_fetched": 1048576
  },
  "quotas": {
    "max_requests_per_day": 500,
    "max_tool_calls_per_day": 200,
    "max_bytes_fetched_per_day": 5242880
  },
  "remaining": {
    "requests": 350,
    "tool_calls": 0,
    "bytes_fetched": 4194304
  }
}
```

---

## Quota Enforcement

When quotas are exceeded, the API returns `429 Too Many Requests`:

```json
{
  "detail": "Daily request quota exceeded"
}
```

| Quota | Default | Description |
|-------|---------|-------------|
| `max_requests_per_day` | 500 | API requests per day |
| `max_tool_calls_per_day` | 200 | Tool executions per day |
| `max_bytes_fetched_per_day` | 5MB | Data fetched via http_fetch |

Quotas reset daily at midnight UTC.

---

## Tenant Scoping

Jobs are scoped to the tenant that created them:

- **Cross-tenant access returns 404**: Cannot access another tenant's jobs
- **List shows only own jobs**: `/agent/jobs` returns only your tenant's jobs
- **Legacy keys bypass scoping**: For backwards compatibility

---

## Security Notes

- **Keys are hashed**: API keys are stored as HMAC-SHA256 hashes
- **Keys are never logged**: Only key prefixes appear in logs
- **Admin key required**: All tenant management requires admin authentication
- **Constant-time comparison**: Prevents timing attacks on key validation

See [docs/PHASE9.md](PHASE9.md) for full implementation details.

---

## Deployment

The Agent Service includes automated CI/CD deployment with GitHub Actions.

### Quick Deploy

```bash
# Create and push a version tag
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions will automatically deploy to your configured server.

### Manual Deploy

```bash
# On the server
cd /opt/agent-service
./scripts/deploy.sh v1.0.0
```

### Features

- **Automated backups** before each deployment
- **Health checks** with automatic retry
- **Automatic rollback** if deployment fails
- **Zero-downtime** updates

### Server Requirements

1. Docker and Docker Compose installed
2. SSH access configured for GitHub Actions
3. `.env` file with required secrets

See [docs/PHASE11.md](PHASE11.md) for complete deployment guide.

---

## Builder Mode (Phase 12)

The Builder Mode allows you to analyze GitHub repositories and generate code change patches.

### Quick Start

```bash
# Start a builder job
curl -X POST http://127.0.0.1:8000/builder/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/owner/repo",
    "prompt": "Add error handling to the database module"
  }'

# Check status
curl http://127.0.0.1:8000/builder/status/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"

# Get results
curl http://127.0.0.1:8000/builder/result/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"

# Get unified patch
curl "http://127.0.0.1:8000/builder/files/JOB_ID?format=unified" \
  -H "X-API-Key: YOUR_API_KEY"
```

### Builder Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/builder/run` | POST | Start a new builder job |
| `/builder/status/{job_id}` | GET | Get detailed job status |
| `/builder/result/{job_id}` | GET | Get job result with diffs |
| `/builder/files/{job_id}` | GET | Get files in various formats |
| `/builder/jobs` | GET | List builder jobs |
| `/builder/jobs/{job_id}` | DELETE | Delete a builder job |

### Request Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `repo_url` | string | GitHub repository URL (required) |
| `prompt` | string | Description of changes (required, 10-8192 chars) |
| `ref` | string | Git ref (default: HEAD) |
| `target_paths` | array | Limit changes to specific paths |
| `exclude_paths` | array | Exclude paths from changes |
| `max_files` | int | Max files to modify (1-50, default: 10) |

### Security

- **Read-only** - No writes to repositories
- **GitHub only** - Only github.com URLs allowed
- **Rate limited** - 60 requests/minute (GitHub API)
- **Size limits** - 512KB max file size

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | Optional GitHub token for higher rate limits |

See [docs/PHASE12.md](PHASE12.md) for full Builder Mode documentation.

---

## Scaffolder Mode (Phase 13)

Generate complete project skeletons from templates. Supports Next.js, FastAPI, and fullstack applications.

### Quick Start

```bash
# Generate a Next.js project
curl -X POST http://127.0.0.1:8000/builder/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "scaffold",
    "template": "nextjs",
    "project": {
      "name": "my-app",
      "description": "A modern web application"
    }
  }'

# Check result
curl http://127.0.0.1:8000/builder/result/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

### Templates

| Template | Description |
|----------|-------------|
| `nextjs` | Next.js + TypeScript + Tailwind CSS |
| `fastapi` | FastAPI + PostgreSQL + Alembic migrations |
| `fullstack` | Next.js frontend + FastAPI backend + Docker Compose |

### Request Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `mode` | string | Must be `"scaffold"` |
| `template` | string | Template name (required) |
| `project.name` | string | Project name (required) |
| `project.description` | string | Short description |
| `project.features` | array | Optional features to include |
| `output.format` | string | `"files"` (default) or `"patches"` |
| `output.base_path` | string | Base path for generated files |

### Output Formats

**Files Format (default):**
```json
{
  "scaffold_files": [
    {"path": "package.json", "content": "...", "size": 1234},
    {"path": "src/index.ts", "content": "...", "size": 567}
  ],
  "scaffold_total_bytes": 45678
}
```

**Patches Format:**
```json
{
  "diffs": [
    {
      "path": "package.json",
      "diff_type": "add",
      "unified_diff": "--- /dev/null\n+++ b/package.json\n@@ ...",
      "new_content": "..."
    }
  ]
}
```

### Applying Patches

Save the unified diff output and apply with `git apply`:

```bash
# Save patches to file
curl "http://127.0.0.1:8000/builder/files/JOB_ID?format=unified" \
  -H "X-API-Key: YOUR_API_KEY" \
  | jq -r '.unified_patch' > scaffold.patch

# Apply to repository
git apply scaffold.patch
```

### Size Limits

| Limit | Value |
|-------|-------|
| Max files | 80 |
| Max file size | 80 KB |
| Max total size | 1.5 MB |

---

## Project Scaffold + ZIP Artifacts (Phase 14)

Generate complete project scaffolds with downloadable ZIP artifacts. This provides a simpler, more direct approach to generating project files.

### Quick Start

```bash
# Generate a project scaffold
curl -X POST http://127.0.0.1:8000/builder/scaffold \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "fastapi_api",
    "project_name": "my-api",
    "options": {
      "use_docker": true,
      "include_ci": true
    }
  }'

# Check job status
curl http://127.0.0.1:8000/agent/status/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"

# Download ZIP artifact
curl -OJ http://127.0.0.1:8000/builder/artifact/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"

# Get artifact metadata
curl http://127.0.0.1:8000/builder/artifact/JOB_ID/info \
  -H "X-API-Key: YOUR_API_KEY"
```

### Scaffold Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/builder/scaffold` | POST | Create scaffold job |
| `/builder/artifact/{job_id}` | GET | Download ZIP artifact |
| `/builder/artifact/{job_id}/info` | GET | Get artifact metadata |

### Templates

| Template | Description |
|----------|-------------|
| `nextjs_web` | Next.js + TypeScript + ESLint |
| `fastapi_api` | FastAPI + pytest skeleton |
| `fullstack_nextjs_fastapi` | Combined web/ and api/ folders |

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `template` | string | Yes | Template name |
| `project_name` | string | Yes | Project name (alphanumeric, hyphens, underscores) |
| `options.use_docker` | boolean | No | Include Dockerfile |
| `options.include_ci` | boolean | No | Include GitHub Actions CI |

### Scaffold Response (202 Accepted)

```json
{
  "job_id": "uuid",
  "status": "queued",
  "message": "Scaffold job created",
  "template": "fastapi_api",
  "project_name": "my-api"
}
```

### Artifact Info Response

```json
{
  "job_id": "uuid",
  "artifact_name": "my-api.zip",
  "artifact_size_bytes": 12345,
  "artifact_sha256": "abc123...",
  "template": "fastapi_api",
  "project_name": "my-api",
  "download_url": "/builder/artifact/uuid"
}
```

### Artifact Limits

| Limit | Value |
|-------|-------|
| Max files | 300 |
| Max uncompressed size | 8 MB |
| Max ZIP size | 5 MB |
| Artifact retention | 24 hours |

### Security Features

- **Path traversal prevention** - All paths validated before inclusion
- **SHA256 verification** - Artifact integrity can be verified
- **Automatic cleanup** - Artifacts deleted after 24 hours
- **Size limits** - Prevent resource exhaustion

### Swagger UI Authentication

The OpenAPI docs (`/docs`) include authentication support:

1. Click the **Authorize** button in Swagger UI
2. Enter your API key:
   - For `apiKeyHeader`: Enter `YOUR_API_KEY`
   - For `bearerAuth`: Enter `Bearer YOUR_API_KEY`
3. Click **Authorize** to save

Public endpoints accessible without auth:
- `GET /health`
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

---

### Fullstack Example

Generate a complete fullstack application:

```bash
curl -X POST http://127.0.0.1:8000/builder/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "scaffold",
    "template": "fullstack",
    "project": {
      "name": "my-saas",
      "description": "A SaaS application",
      "features": ["auth_optional", "db_optional"]
    },
    "output": {
      "format": "files",
      "base_path": "/workspace/my-saas"
    }
  }'
```

---

## Issue Fixer Mode (Phase 13)

Diagnose issues in repositories and generate fix patches based on error logs, stack traces, and problem descriptions.

### Quick Start

```bash
# Analyze an issue
curl -X POST http://127.0.0.1:8000/builder/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "fix",
    "repo_url": "https://github.com/owner/repo",
    "task": {
      "prompt": "Fix the authentication bypass vulnerability",
      "context": {
        "error_log": "SecurityError: JWT validation failed",
        "stacktrace": "at validateToken (auth.js:42)"
      }
    }
  }'

# Get diagnosis and patches
curl http://127.0.0.1:8000/builder/result/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

### Request Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `mode` | string | Must be `"fix"` |
| `repo_url` | string | GitHub repository URL |
| `repo` | object | Alternative: `{owner, name, ref, path_prefix}` |
| `task.prompt` | string | Description of the issue |
| `task.context.error_log` | string | Error log output |
| `task.context.stacktrace` | string | Stack trace |
| `task.context.failing_test` | string | Failing test name |
| `task.context.expected_behavior` | string | What should happen |

### Response Fields

| Field | Description |
|-------|-------------|
| `repo_summary` | Summary of repository structure |
| `likely_cause` | Root cause analysis |
| `repro_plan` | Steps to reproduce the issue |
| `diffs` | Proposed fix patches |
| `verification_checklist` | Steps to verify the fix |
| `risk_notes` | Potential risks of proposed changes |

### Response Example

```json
{
  "job_id": "...",
  "status": "done",
  "mode": "fix",
  "repo_summary": "FastAPI application with SQLAlchemy ORM...",
  "likely_cause": "Missing JWT expiration check in auth middleware",
  "repro_plan": [
    {
      "step_number": 1,
      "description": "Clone the repository",
      "command": "git clone https://github.com/owner/repo"
    },
    {
      "step_number": 2,
      "description": "Create expired JWT token",
      "command": "python scripts/create_token.py --expired"
    }
  ],
  "diffs": [
    {
      "path": "app/auth.py",
      "diff_type": "modify",
      "description": "Add JWT expiration validation",
      "unified_diff": "--- a/app/auth.py\n+++ b/app/auth.py\n@@ ...",
      "confidence": "high"
    }
  ],
  "verification_checklist": [
    {
      "description": "Run authentication tests",
      "command": "pytest tests/test_auth.py",
      "is_manual": false
    },
    {
      "description": "Verify expired tokens are rejected",
      "is_manual": true
    }
  ],
  "risk_notes": "Changes to authentication middleware. Review carefully."
}
```

### Security Notes

- **Read-only** - Never writes to repositories
- **Patch proposals only** - Fixes must be manually reviewed and applied
- **No command execution** - Commands in repro_plan are informational only

### Applying Fix Patches

```bash
# Save the unified diff
curl "http://127.0.0.1:8000/builder/files/JOB_ID?format=unified" \
  -H "X-API-Key: YOUR_API_KEY" \
  -o fix.patch

# Review the patch
cat fix.patch

# Apply to repository
cd /path/to/repo
git apply fix.patch

# Run verification checklist
pytest tests/
```

---

## Mode Comparison

| Feature | Builder | Scaffold | Fix | Repo Builder |
|---------|---------|----------|-----|--------------|
| Repository required | Yes | No | Yes | Yes |
| Prompt required | Yes | No | Yes | No |
| Template | No | Yes | No | Yes |
| Output | Patches | Files/Patches | Patches | ZIP + Patch |
| Read-only | Yes | N/A | Yes | Yes |
| Use case | Code changes | New projects | Bug fixes | Modernize repos |

---

## Repo Builder (Phase 15)

Download a GitHub repository, apply template transforms, and generate PR-ready patches.

### Quick Start

```bash
# Create a repo builder job
curl -X POST https://agent-x-one.com/builder/from_repo \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/owner/repo",
    "ref": "main",
    "template": "fastapi_api",
    "options": {
      "add_docker": true,
      "add_github_actions": true,
      "add_readme": true
    }
  }'

# Check job status
curl https://agent-x-one.com/agent/status/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"

# Download modified repo as ZIP
curl -OJ https://agent-x-one.com/builder/from_repo/JOB_ID/download \
  -H "X-API-Key: YOUR_API_KEY"

# Get unified patch for PR
curl https://agent-x-one.com/builder/from_repo/JOB_ID/patch \
  -H "X-API-Key: YOUR_API_KEY" \
  -o changes.diff

# Get job metadata
curl https://agent-x-one.com/builder/from_repo/JOB_ID/info \
  -H "X-API-Key: YOUR_API_KEY"
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/builder/from_repo` | POST | Start a repo builder job |
| `/builder/from_repo/{job_id}/download` | GET | Download modified repo ZIP |
| `/builder/from_repo/{job_id}/patch` | GET | Get unified diff for PR |
| `/builder/from_repo/{job_id}/info` | GET | Get job metadata |

### Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_url` | string | required | GitHub repository URL |
| `ref` | string | `"main"` | Git ref (branch, tag, commit) |
| `template` | string | `"fastapi_api"` | Template to apply |
| `options.add_docker` | boolean | false | Add Dockerfile and docker-compose.yml |
| `options.add_github_actions` | boolean | false | Add .github/workflows/ci.yml |
| `options.add_readme` | boolean | false | Add/update README.md |

### Response (202 Accepted)

```json
{
  "job_id": "uuid",
  "status": "queued",
  "message": "Repo builder job created",
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",
  "template": "fastapi_api",
  "status_url": "/agent/status/uuid",
  "steps_url": "/agent/steps/uuid",
  "result_url": "/agent/result/uuid",
  "download_url": "/builder/from_repo/uuid/download",
  "patch_url": "/builder/from_repo/uuid/patch",
  "info_url": "/builder/from_repo/uuid/info"
}
```

### Job Result Output

```json
{
  "owner": "tiangolo",
  "repo": "fastapi",
  "ref": "main",
  "template": "fastapi_api",
  "files_added": ["Dockerfile", "docker-compose.yml", ".github/workflows/ci.yml"],
  "files_modified": ["README.md"],
  "files_unchanged_count": 150,
  "notes": ["Created Dockerfile", "Added CI workflow"],
  "modified_zip_sha256": "abc123...",
  "modified_zip_size": 12345,
  "patch_sha256": "def456...",
  "patch_size": 5678,
  "download_url": "/builder/from_repo/uuid/download",
  "patch_url": "/builder/from_repo/uuid/patch",
  "summary": "Applied fastapi_api template: 4 files added, 1 file modified"
}
```

### Applying Patches

```bash
# Download the patch
curl https://agent-x-one.com/builder/from_repo/JOB_ID/patch \
  -H "X-API-Key: YOUR_API_KEY" \
  -o changes.diff

# Apply to your local clone
cd /path/to/your-repo-clone
git apply changes.diff

# Create a PR
git checkout -b modernize-repo
git add .
git commit -m "Apply fastapi_api template transforms"
git push origin modernize-repo
```

### Security Features

| Feature | Description |
|---------|-------------|
| Domain Allowlist | Only github.com and codeload.github.com |
| HTTPS Only | HTTP URLs rejected |
| Size Limits | 25MB download, 80MB extracted, 10,000 files max |
| Zip-Slip Prevention | Path traversal blocked |
| No Shell Execution | Pure Python HTTP + ZIP processing |
| No Secrets | Tokens never logged or stored |

### Templates

| Template | Adds |
|----------|------|
| `fastapi_api` | Dockerfile, docker-compose.yml, CI, README, ruff config, health endpoint |

### Size Limits

| Limit | Value |
|-------|-------|
| Max download | 25 MB |
| Max extracted | 80 MB |
| Max files | 10,000 |
| Artifact retention | 24 hours |

---

## Swagger UI Authentication

The OpenAPI docs (`/docs`) include authentication support:

1. Navigate to `https://agent-x-one.com/docs`
2. Click the **Authorize** button
3. Enter your API key:
   - For `apiKeyHeader`: Enter `YOUR_API_KEY`
   - For `bearerAuth`: Enter `Bearer YOUR_API_KEY`
4. Click **Authorize** to save

### Public Endpoints (No Auth Required)

- `GET /health`
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

---

## How to Verify (Phase 15)

### Base URL

```
https://agent-x-one.com
```

Or for local development:

```
http://127.0.0.1:8000
```

### Verification Endpoints

| Endpoint | Description |
|----------|-------------|
| `/docs` | Swagger UI (public) |
| `/health` | Health check (public) |
| `/builder/from_repo` | Create repo builder job (auth required) |
| `/builder/from_repo/{job_id}/download` | Download modified ZIP (auth required) |
| `/builder/from_repo/{job_id}/patch` | Get unified diff (auth required) |
| `/builder/from_repo/{job_id}/info` | Get job metadata (auth required) |

### Verification curl Commands

```bash
# 1. Check health
curl https://agent-x-one.com/health

# 2. Create a repo builder job
curl -X POST https://agent-x-one.com/builder/from_repo \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/tiangolo/fastapi",
    "ref": "master",
    "template": "fastapi_api",
    "options": {"add_docker": true, "add_github_actions": true}
  }'

# 3. Check job status (replace JOB_ID)
curl https://agent-x-one.com/agent/status/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"

# 4. Get job result
curl https://agent-x-one.com/agent/result/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"

# 5. Download modified repo ZIP
curl -OJ https://agent-x-one.com/builder/from_repo/JOB_ID/download \
  -H "X-API-Key: YOUR_API_KEY"

# 6. Get unified patch
curl https://agent-x-one.com/builder/from_repo/JOB_ID/patch \
  -H "X-API-Key: YOUR_API_KEY"

# 7. Get job info
curl https://agent-x-one.com/builder/from_repo/JOB_ID/info \
  -H "X-API-Key: YOUR_API_KEY"
```

---

## Web UI (Agent Control Panel)

The Agent Service includes a built-in web UI for managing jobs without using curl or code.

### Access

Navigate to `/ui` with your API key in the header:

- **URL**: `https://agent-x-one.com/ui`
- **Auth Required**: Yes (same as API)

### Browser Access Options

#### Option 1: ModHeader Browser Extension
1. Install ModHeader extension
2. Add header: `X-API-Key` → `YOUR_API_KEY`  
3. Navigate to `http://localhost:8000/ui`

#### Option 2: Reverse Proxy
Configure your reverse proxy (nginx, Caddy) to inject the API key header for trusted users.

### UI Features

| Page | URL | Description |
|------|-----|-------------|
| Jobs List | `/ui/jobs` | View all jobs with filters |
| Job Detail | `/ui/jobs/{job_id}` | View job status, steps, results |
| New Job | `/ui/run` | Submit new jobs (tool/agent/builder) |

### UI Capabilities

- **View Jobs**: List, filter, paginate jobs
- **Job Details**: Status, timestamps, duration, input/output
- **Execution Steps**: Timeline view for agent jobs
- **Citations**: Source links from web searches
- **Artifacts**: Download ZIPs and patches for builder jobs
- **Curl Examples**: Copy-to-clipboard API commands

### Screenshots

See [PHASE15.md](./PHASE15.md) for detailed documentation and screenshots.

---

## Safe Build Runner (Phase 16)

The Build Runner provides a safe, deterministic way to execute CI-style pipelines (install dependencies, lint, test, build) on repositories without arbitrary command execution.

### Security Features

- **Domain Allowlist**: Only GitHub (`github.com`) and GitLab (`gitlab.com`) repositories
- **No shell=True**: All commands executed as safe subprocess lists
- **Isolated Workspaces**: Each job runs in `data/workspaces/{job_id}/` with 24h auto-cleanup
- **Command Timeouts**: 5 minutes per command, 15 minutes total
- **Sanitized Environment**: Minimal PATH, no sensitive env vars
- **No Secrets in Logs**: Build logs are sanitized

### Supported Project Types

| Type | Detection | Pipeline Steps |
|------|-----------|----------------|
| **Python** | `pyproject.toml`, `requirements.txt`, `setup.py` | Create venv → pip install → pytest |
| **Node.js** | `package.json` | npm ci → npm run lint → npm test → npm run build |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/builder/build` | Start a build runner job |
| GET | `/builder/build/{job_id}/status` | Get build status and pipeline steps |
| GET | `/builder/build/{job_id}/logs` | Get full build logs |
| GET | `/builder/build/{job_id}/logs/download` | Download build logs as file |

### curl Examples

#### Start a Build Job

```bash
# Python project
curl -X POST https://agent-x-one.com/builder/build \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/owner/my-python-repo",
    "ref": "main",
    "pipeline": "auto"
  }'

# Response:
{
  "job_id": "abc123...",
  "status": "queued",
  "message": "Build runner job created",
  "repo_url": "https://github.com/owner/my-python-repo",
  "ref": "main",
  "pipeline": "auto",
  "status_url": "/builder/build/abc123.../status",
  "logs_url": "/builder/build/abc123.../logs"
}
```

#### Check Build Status

```bash
curl https://agent-x-one.com/builder/build/{job_id}/status \
  -H "X-API-Key: YOUR_API_KEY"

# Response:
{
  "job_id": "abc123...",
  "status": "done",
  "repo_url": "https://github.com/owner/my-python-repo",
  "ref": "main",
  "project_type": "python",
  "pipeline_steps": [
    {
      "name": "setup",
      "description": "Create Python virtual environment",
      "status": "success",
      "duration_ms": 2500,
      "error": null,
      "commands": [{"command": "python3 -m venv...", "exit_code": 0}]
    },
    {
      "name": "install",
      "description": "Install Python dependencies",
      "status": "success",
      "duration_ms": 15000,
      "error": null
    },
    {
      "name": "test",
      "description": "Run pytest tests",
      "status": "success",
      "duration_ms": 5000,
      "error": null
    }
  ],
  "overall_status": "success",
  "total_duration_ms": 22500,
  "notes": ["Downloaded 50 files", "Detected project type: python"]
}
```

#### Get Build Logs

```bash
curl https://agent-x-one.com/builder/build/{job_id}/logs \
  -H "X-API-Key: YOUR_API_KEY"

# Response:
{
  "job_id": "abc123...",
  "log_content": "Build Log for Job: abc123...\n=====...\n## Step: setup\n...",
  "log_size": 15000,
  "log_sha256": "abc123..."
}
```

#### Download Build Logs

```bash
curl -OJ https://agent-x-one.com/builder/build/{job_id}/logs/download \
  -H "X-API-Key: YOUR_API_KEY"
```

### Node.js Project Example

```bash
curl -X POST https://agent-x-one.com/builder/build \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/owner/my-node-repo",
    "ref": "develop",
    "pipeline": "node"
  }'
```

Pipeline steps for Node.js:
1. **install**: `npm ci` (or `npm install` if no package-lock.json)
2. **lint**: `npm run lint` (if script exists in package.json)
3. **test**: `npm test` (if script exists)
4. **build**: `npm run build` (if script exists)

### Web UI

The Build Runner is integrated into the Agent Control Panel:

1. Navigate to `/ui/run`
2. Click the **"Build Runner"** tab
3. Enter repository URL, branch, and pipeline type
4. Click **"🚀 Run Build Pipeline"**
5. View results on the job detail page

### Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `Domain not allowed` | Repository is not on GitHub or GitLab | Use an allowed repository |
| `Only HTTPS URLs are allowed` | HTTP URL provided | Use HTTPS |
| `Could not detect project type` | No pyproject.toml, requirements.txt, or package.json | Add project files |
| `Download timed out` | Repository too large or slow | Try smaller ref |
| `Test execution timed out` | Tests take too long | Optimize tests or increase timeout |

### Planner Integration

The agent planner automatically detects build/test requests:

```bash
# Natural language → Build Runner
curl -X POST https://agent-x-one.com/agent/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "run tests on https://github.com/owner/repo",
    "mode": "agent"
  }'
```

Detected keywords:
- "run tests", "execute tests", "run pytest", "npm test"
- "verify build", "check build", "build project"
- "run ci", "run pipeline", "lint code"

---

## Chat UI (Single Entrypoint)

The Agent Service provides a unified chat interface for interacting with Xone.

### Access

**URL**: `/ui/chat` (single entrypoint)

This route serves the **Command Center UI** which includes:
- Chat interface for talking to Xone
- Right drawer with tabs: Approvals, Jobs, Memory, Audit, Settings
- Left sidebar for conversation management
- PWA support for mobile installation

### No-Cache Headers

The UI routes include anti-cache headers to ensure you always see the latest version:
- `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`
- `Pragma: no-cache`
- `Expires: 0`

### Clearing Browser Cache

If you see an old version of the UI:
1. **Hard refresh**: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
2. **Clear site data**: Developer Tools → Application → Clear site data
3. **Unregister service worker**: Developer Tools → Application → Service Workers → Unregister

### URLs

| Route | Description |
|-------|-------------|
| `/ui/chat` | **Primary entrypoint** - Command Center UI |
| `/ui/command-center` | Same as `/ui/chat` |
| `/ui/jobs` | Jobs dashboard |
| `/ui/run` | Submit new jobs |

