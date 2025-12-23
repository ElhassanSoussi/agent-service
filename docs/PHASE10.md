# Phase 10: Production Release Packaging

This document describes the production deployment setup for the Agent Service.

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo-url>
cd agent-service

# Copy environment template
cp .env.example .env

# Edit .env with your values (REQUIRED!)
# Generate secure keys:
#   openssl rand -hex 32
```

### 2. Start with Docker Compose

```bash
# Build and start
docker-compose up -d

# Verify health
curl http://127.0.0.1:8000/health
# {"status":"ok"}

# View logs
docker-compose logs -f agent
```

### 3. Create a Tenant and API Key

```bash
# Create tenant
curl -X POST http://127.0.0.1:8000/admin/tenants \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "MyCompany"}'

# Response: {"tenant_id": "xxx", "name": "MyCompany", ...}

# Create API key for tenant
curl -X POST http://127.0.0.1:8000/admin/tenants/TENANT_ID/keys \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Production Key"}'

# Response: {"api_key": "agk_live_...", ...}
# ⚠️  SAVE THIS KEY - it's only shown once!
```

### 4. Use the API

```bash
# Submit a job
curl -X POST http://127.0.0.1:8000/agent/run \
  -H "X-API-Key: agk_live_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "echo", "input": {"hello": "world"}}'

# Check status
curl http://127.0.0.1:8000/agent/status/JOB_ID \
  -H "X-API-Key: agk_live_YOUR_KEY"
```

---

## Docker Configuration

### Dockerfile

Multi-stage build for minimal production image:

- **Base**: `python:3.10-slim`
- **Non-root user**: `appuser` (UID 1000)
- **Health check**: Built-in curl to `/health`
- **Data volume**: `/app/data` for SQLite persistence

### docker-compose.yml

Services:
- `agent`: Main application on port 8000

Environment variables (set in `.env` or docker-compose):

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_ADMIN_KEY` | Yes | Admin API authentication |
| `AGENT_KEY_HASH_SECRET` | Yes | Secret for key hashing |
| `AGENT_API_KEY` | No | Legacy single key |
| `AGENT_DB_PATH` | No | Database path (default: `/app/data/jobs.db`) |
| `AGENT_PLANNER_MODE` | No | `rules` or `llm` |

### Data Persistence

SQLite database is stored in `./data/jobs.db` (mounted volume).

```yaml
volumes:
  - ./data:/app/data
```

---

## Local Development

### Without Docker

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
make install-dev

# Set environment
export AGENT_API_KEY=dev-key
export AGENT_ADMIN_KEY=dev-admin
export AGENT_KEY_HASH_SECRET=dev-secret

# Run server
make run
# or: uvicorn main:app --reload
```

### Makefile Commands

| Command | Description |
|---------|-------------|
| `make test` | Run pytest |
| `make lint` | Run ruff linter |
| `make format` | Format code with ruff |
| `make run` | Start local dev server |
| `make docker-build` | Build Docker image |
| `make docker-up` | Start docker-compose |
| `make docker-down` | Stop docker-compose |
| `make docker-logs` | View container logs |
| `make clean` | Remove cache files |

---

## CI/CD

### GitHub Actions

The `.github/workflows/ci.yml` runs on push/PR:

1. **Test job**:
   - Python 3.10 setup
   - Install dependencies
   - Syntax check (`compileall`)
   - Lint with ruff
   - Run pytest

2. **Docker job** (after tests pass):
   - Build Docker image
   - Health check test

### Running CI Locally

```bash
# Lint
make lint

# Tests
make test

# Docker build
make docker-build
```

---

## Security Checklist

### Before Deployment

- [ ] Generate strong `AGENT_ADMIN_KEY`: `openssl rand -hex 32`
- [ ] Generate strong `AGENT_KEY_HASH_SECRET`: `openssl rand -hex 32`
- [ ] Remove or randomize `AGENT_API_KEY` (use per-tenant keys)
- [ ] Never commit `.env` file
- [ ] Review `.dockerignore` excludes secrets

### In Production

- [ ] Use HTTPS (terminate SSL at load balancer/nginx)
- [ ] Rotate `AGENT_ADMIN_KEY` periodically
- [ ] Monitor `/metrics` endpoint
- [ ] Set up log aggregation
- [ ] Backup `./data/jobs.db` regularly

### Key Management

- API keys are hashed with HMAC-SHA256 before storage
- Only key prefix (`agk_live_xxx...`) is logged
- Rotate keys via admin API (creates new key, revokes old)
- Changing `AGENT_KEY_HASH_SECRET` invalidates ALL keys

---

## Versioning

### Semantic Versioning

This project uses semantic versioning: `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking API changes
- **MINOR**: New features, backwards compatible
- **PATCH**: Bug fixes

### Release Process

1. Update version in code (if tracked)
2. Update CHANGELOG.md
3. Tag release: `git tag v1.0.0`
4. Push tag: `git push origin v1.0.0`
5. Build and push Docker image

### Current Version

**v1.0.0** - Phase 10 (Production Release)

Features:
- Multi-tenant support with API key management
- Per-tenant quotas and usage tracking
- Tool/Agent execution modes
- Web research tools (search, fetch, summarize)
- LLM-powered planning (optional)
- Docker deployment ready
- CI/CD pipeline

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs agent

# Common issues:
# - Missing required env vars (AGENT_ADMIN_KEY, AGENT_KEY_HASH_SECRET)
# - Port 8000 already in use
# - Permission denied on ./data directory
```

### Database issues

```bash
# Reset database (WARNING: deletes all data!)
rm -rf ./data/jobs.db
docker-compose restart

# Check database location
docker-compose exec agent ls -la /app/data/
```

### Authentication failures

```bash
# Verify admin key is set
docker-compose exec agent env | grep AGENT

# Test admin endpoint
curl -v http://127.0.0.1:8000/admin/tenants \
  -H "X-Admin-Key: YOUR_KEY"
```

---

## File Structure

```
agent-service/
├── .github/
│   └── workflows/
│       └── ci.yml          # GitHub Actions CI
├── app/
│   ├── api/                # API endpoints
│   ├── core/               # Business logic
│   ├── db/                 # Database models
│   └── tools/              # Tool implementations
├── docs/
│   ├── USAGE.md            # API documentation
│   └── PHASE10.md          # This file
├── tests/                  # Test suite
├── data/                   # SQLite database (gitignored)
├── .dockerignore           # Docker build exclusions
├── .env.example            # Environment template
├── docker-compose.yml      # Docker orchestration
├── Dockerfile              # Production image
├── Makefile                # Dev commands
├── main.py                 # Application entry
├── requirements.txt        # Production deps
└── requirements-dev.txt    # Dev deps (ruff, pytest)
```
