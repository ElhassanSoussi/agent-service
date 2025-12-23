# Phase 12: Codebase Builder Mode

This document describes the Codebase Builder Mode feature for the Agent Service.

## Overview

The Codebase Builder Mode allows users to analyze GitHub repositories and generate code changes as unified diff patches. This feature provides:

- **Read-only GitHub access** - Fetch repository structure, files, and search code
- **Safe by design** - No writes, domain allowlist, size limits, rate limiting
- **Unified diff output** - Generate patches that can be reviewed and applied manually
- **LLM-powered planning** - (Future) Use LLM to determine which files to modify

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  POST /builder/run  │────▶│  Background Worker  │────▶│  GitHub API         │
│                     │     │                     │     │  (read-only)        │
│  - repo_url         │     │  1. Analyze repo    │     │                     │
│  - prompt           │     │  2. Plan changes    │     │  - Trees            │
│  - constraints      │     │  3. Generate diffs  │     │  - Contents         │
└─────────────────────┘     └─────────────────────┘     │  - Search           │
                                      │                 └─────────────────────┘
                                      ▼
                            ┌─────────────────────┐
                            │  Unified Diff       │
                            │  Patches            │
                            │                     │
                            │  GET /builder/      │
                            │    result/{job_id}  │
                            └─────────────────────┘
```

## Quick Start

### 1. Start a Builder Job

```bash
curl -X POST http://127.0.0.1:8000/builder/run \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/owner/repo",
    "prompt": "Add error handling to the database module",
    "max_files": 5
  }'
```

**Response (202 Accepted):**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "repo_url": "https://github.com/owner/repo",
  "created_at": "2025-12-19T00:00:00.000000Z"
}
```

### 2. Check Job Status

```bash
curl http://127.0.0.1:8000/builder/status/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "analyzing",
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",
  "prompt": "Add error handling...",
  "current_phase": "analyzing",
  "progress_pct": 30,
  "analysis_steps": [
    {"step_number": 1, "action": "get_info", "status": "done"},
    {"step_number": 2, "action": "get_tree", "status": "done"},
    {"step_number": 3, "action": "get_readme", "status": "pending"}
  ]
}
```

### 3. Get Results

```bash
curl http://127.0.0.1:8000/builder/result/JOB_ID \
  -H "X-API-Key: YOUR_API_KEY"
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "done",
  "repo_url": "https://github.com/owner/repo",
  "files_analyzed": 42,
  "files_modified": 3,
  "diffs": [
    {
      "path": "src/database.py",
      "diff_type": "modify",
      "unified_diff": "--- a/src/database.py\n+++ b/src/database.py\n..."
    }
  ],
  "summary": "Added error handling to 3 files..."
}
```

### 4. Get Unified Patch

```bash
curl "http://127.0.0.1:8000/builder/files/JOB_ID?format=unified" \
  -H "X-API-Key: YOUR_API_KEY"
```

**Response:**
```json
{
  "job_id": "uuid",
  "format": "unified",
  "unified_patch": "--- a/src/database.py\n+++ b/src/database.py\n...",
  "total_files": 3,
  "total_lines_added": 45,
  "total_lines_removed": 12
}
```

---

## API Endpoints

### POST /builder/run

Start a new builder job.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo_url` | string | Yes | GitHub repository URL |
| `prompt` | string | Yes | Description of changes (10-8192 chars) |
| `ref` | string | No | Git ref (default: HEAD) |
| `target_paths` | array | No | Limit changes to paths |
| `exclude_paths` | array | No | Exclude paths from changes |
| `max_files` | int | No | Max files to modify (1-50, default: 10) |
| `model` | string | No | LLM model override |

**Example:**
```json
{
  "repo_url": "https://github.com/owner/repo",
  "prompt": "Add comprehensive error handling to all database operations",
  "ref": "main",
  "target_paths": ["src/db/", "src/models/"],
  "exclude_paths": ["src/db/migrations/"],
  "max_files": 10
}
```

---

### GET /builder/status/{job_id}

Get detailed status of a builder job.

**Response Fields:**

| Field | Description |
|-------|-------------|
| `job_id` | Unique job identifier |
| `status` | Job status: queued, analyzing, planning, generating, done, error |
| `current_phase` | Current execution phase |
| `progress_pct` | Progress percentage (0-100) |
| `analysis_steps` | List of analysis steps with status |

---

### GET /builder/result/{job_id}

Get the result of a completed builder job.

**Response Fields:**

| Field | Description |
|-------|-------------|
| `files_analyzed` | Number of files analyzed |
| `files_modified` | Number of files with changes |
| `diffs` | List of file diffs |
| `summary` | AI-generated summary of changes |
| `error` | Error message if failed |

---

### GET /builder/files/{job_id}

Get generated files in various formats.

**Query Parameters:**

| Parameter | Values | Description |
|-----------|--------|-------------|
| `format` | `unified` | Single unified diff patch (default) |
| `format` | `files` | List of file contents |

---

### GET /builder/jobs

List builder jobs for the current tenant.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results (1-100, default: 20) |
| `offset` | int | Pagination offset |
| `status` | string | Filter by status |

---

### DELETE /builder/jobs/{job_id}

Delete a builder job.

---

## Repository Tools

The builder mode uses these read-only tools internally:

### repo_get_info

Get basic repository information.

```python
{
    "owner": "...",
    "repo": "...",
    "description": "...",
    "language": "Python",
    "default_branch": "main",
    "stars": 1234,
    "topics": ["python", "api"]
}
```

### repo_get_tree

Get the file tree of a repository.

```python
{
    "tree": [
        {"path": "src/main.py", "type": "file", "size": 1234},
        {"path": "src/utils/", "type": "dir"}
    ],
    "total_entries": 42
}
```

### repo_get_file

Get contents of a single file.

```python
{
    "path": "src/main.py",
    "content": "import...",
    "size": 1234,
    "encoding": "utf-8"
}
```

### repo_search_code

Search for code in a repository.

```python
{
    "query": "database connection",
    "results": [
        {"path": "src/db.py", "name": "db.py", "url": "..."}
    ],
    "total_count": 5
}
```

### repo_get_readme

Get the repository README.

```python
{
    "path": "README.md",
    "content": "# Project..."
}
```

---

## Security

### Domain Allowlist

Only these domains are allowed:
- `github.com`
- `api.github.com`
- `raw.githubusercontent.com`

### Size Limits

| Limit | Value |
|-------|-------|
| Max file size | 512 KB |
| Max tree entries | 10,000 |
| Max search results | 100 |

### Rate Limiting

| Operation | Limit |
|-----------|-------|
| GitHub API | 60/minute |
| GitHub Search | 10/minute |

Rate limits are higher with `GITHUB_TOKEN` environment variable.

### Read-Only

The builder mode is **completely read-only**:
- No repository writes
- No file modifications
- No branch/PR creation
- Output is unified diff only

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_TOKEN` | GitHub API token (optional, higher rate limits) | None |

### Getting a GitHub Token

1. Go to https://github.com/settings/tokens
2. Generate new token (classic) with `public_repo` scope
3. Set `GITHUB_TOKEN` in your environment

```bash
# .env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

---

## Caching

Repository data is cached to reduce API calls:

| Data | TTL |
|------|-----|
| Repository info | 5 minutes |
| File tree | 5 minutes |
| File contents | 10 minutes |
| Search results | 5 minutes |

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| Repository not found | Invalid owner/repo or private repo | Check URL, use GITHUB_TOKEN for private repos |
| Rate limit exceeded | Too many requests | Wait or use GITHUB_TOKEN |
| File too large | File exceeds 512KB limit | Target smaller files |
| Invalid URL | URL not from github.com | Use full GitHub URL |

### Error Response

```json
{
  "job_id": "uuid",
  "status": "error",
  "error": "Repository not found: owner/repo"
}
```

---

## Examples

### Python Client

```python
import httpx
import time

API_KEY = "your-api-key"
BASE_URL = "http://127.0.0.1:8000"

def run_builder(repo_url: str, prompt: str) -> dict:
    """Run a builder job and wait for results."""
    
    # Start job
    resp = httpx.post(
        f"{BASE_URL}/builder/run",
        headers={"X-API-Key": API_KEY},
        json={"repo_url": repo_url, "prompt": prompt}
    )
    job_id = resp.json()["job_id"]
    
    # Poll for completion
    while True:
        resp = httpx.get(
            f"{BASE_URL}/builder/status/{job_id}",
            headers={"X-API-Key": API_KEY}
        )
        status = resp.json()["status"]
        
        if status in ("done", "error"):
            break
        
        time.sleep(2)
    
    # Get results
    return httpx.get(
        f"{BASE_URL}/builder/result/{job_id}",
        headers={"X-API-Key": API_KEY}
    ).json()

# Usage
result = run_builder(
    "https://github.com/owner/repo",
    "Add type hints to all functions"
)
print(result["summary"])
```

### Applying Patches

Get the unified patch and apply with `git apply`:

```bash
# Get patch
curl -s "http://127.0.0.1:8000/builder/files/JOB_ID?format=unified" \
  -H "X-API-Key: YOUR_KEY" \
  | jq -r '.unified_patch' > changes.patch

# Review patch
cat changes.patch

# Apply patch (dry run)
git apply --check changes.patch

# Apply patch
git apply changes.patch
```

---

## Limitations

### Current Limitations

1. **No LLM integration yet** - Currently uses heuristic file selection
2. **No actual code generation** - Returns analyzed files without modifications
3. **Public repos only** - Unless GITHUB_TOKEN is set for private repos
4. **Single repository** - Cannot analyze multiple repos in one job

### Planned Features

- [ ] LLM-powered code generation
- [ ] Multi-file context awareness
- [ ] Dependency analysis
- [ ] Test generation
- [ ] PR creation (opt-in)

---

## Testing

Run builder tests:

```bash
pytest tests/test_builder.py -v
```

### Test Coverage

- URL parsing
- Unified diff generation
- API endpoint authentication
- Request validation
- Job lifecycle (create, status, delete)
- Schema validation

---

## File Structure

```
app/
├── api/
│   └── builder.py      # Builder API endpoints
├── core/
│   └── repo_tools.py   # GitHub repository tools
├── schemas/
│   └── builder.py      # Pydantic schemas
tests/
└── test_builder.py     # Builder tests
docs/
└── PHASE12.md          # This file
```
