# Phase 6: Production Hardening & Observability

This phase adds structured logging, metrics, automated tests, and CI/CD pipeline.

## Features Added

### 1. Structured JSON Logging

All logs are output as JSON for easy parsing by log aggregators (ELK, Loki, etc.).

**Location:** `app/core/logging.py`

**Features:**
- JSON formatted output to stdout
- Request ID tracking across logs
- Automatic redaction of sensitive headers (X-API-Key, Authorization, Cookie)
- Request/response logging with timing
- Never logs payloads or secrets

**Log Fields:**
```json
{
  "timestamp": "2024-12-18T10:30:00.000Z",
  "level": "INFO",
  "logger": "app.core.jobs",
  "message": "job_created job_id=abc123 mode=agent status=queued",
  "request_id": "req-uuid",
  "method": "POST",
  "path": "/agent/run",
  "status_code": 200,
  "duration_ms": 45,
  "client_ip": "10.0.0.1"
}
```

### 2. Prometheus Metrics

**Endpoint:** `GET /metrics` (requires authentication)

**Available Metrics:**
| Metric | Type | Description |
|--------|------|-------------|
| `agent_requests_total` | counter | Total HTTP requests |
| `agent_requests_by_status{status="2xx\|4xx\|5xx"}` | counter | Requests by status class |
| `agent_job_created_total` | counter | Total jobs created |
| `agent_job_completed_total` | counter | Jobs completed successfully |
| `agent_job_error_total` | counter | Jobs that failed |
| `agent_steps_total` | counter | Total agent steps executed |

**Example Response:**
```
# HELP agent_requests_total Total HTTP requests
# TYPE agent_requests_total counter
agent_requests_total 150

# HELP agent_job_created_total Total jobs created
# TYPE agent_job_created_total counter
agent_job_created_total 42
```

### 3. Request Context Tracking

Each request gets a unique `X-Request-ID` header for tracing.

**Location:** `app/core/request_context.py`

- Auto-generated UUID if not provided
- Propagated through all logs
- Returned in response headers

### 4. Automated Tests

**Location:** `tests/`

**Test Coverage:**
- Health endpoint
- Authentication (missing key, invalid key, valid key)
- Metrics endpoint
- Tool mode (echo, job status, list jobs)
- Agent mode (run, steps, result)
- Job management (delete, cancel)

**Running Tests:**
```bash
cd /home/elhassan/agent-service
source venv/bin/activate
pytest tests/ -v
```

### 5. CI Pipeline

**Location:** `.github/workflows/ci.yml`

**Pipeline Steps:**
1. **Test Job:**
   - Checkout code
   - Setup Python 3.10
   - Install dependencies
   - Run linting (ruff)
   - Run pytest

2. **Type Check Job:**
   - Run mypy type checking

## File Structure

```
app/
├── core/
│   ├── logging.py          # JSON logging setup
│   ├── metrics.py          # Prometheus metrics
│   ├── request_context.py  # Request ID tracking
│   └── request_logging.py  # Request logging middleware
├── api/
│   └── metrics.py          # /metrics endpoint
tests/
├── __init__.py
├── conftest.py             # Pytest fixtures
└── test_api.py             # API tests
.github/
└── workflows/
    └── ci.yml              # GitHub Actions CI
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `AGENT_API_KEY` | API authentication key | Required |

### Viewing Logs

```bash
# Follow service logs (JSON format)
sudo journalctl -u agent-service -f

# Parse with jq
sudo journalctl -u agent-service -f -o cat | jq .

# Filter by level
sudo journalctl -u agent-service -f -o cat | jq 'select(.level == "ERROR")'

# Filter by request ID
sudo journalctl -u agent-service -o cat | jq 'select(.request_id == "your-request-id")'
```

### Prometheus Integration

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'agent-service'
    static_configs:
      - targets: ['your-server:443']
    scheme: https
    metrics_path: /metrics
    authorization:
      credentials: your-api-key
```

## Verification

```bash
# Check metrics endpoint
curl -s -H "X-API-Key: $API_KEY" https://your-domain/metrics

# Check JSON logs
sudo journalctl -u agent-service -n 5 -o cat | jq .

# Run tests
cd /home/elhassan/agent-service
source venv/bin/activate
pytest tests/ -v
```

## Security Notes

1. **Logs never contain:**
   - API keys or secrets
   - Request/response payloads
   - User data

2. **Metrics endpoint:**
   - Requires authentication
   - Only exposes aggregate counts

3. **Request IDs:**
   - Safe for external sharing
   - Useful for debugging without exposing sensitive data
