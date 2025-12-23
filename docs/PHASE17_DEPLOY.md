# Phase 17: Production Deployment & Networking

This document covers the production deployment setup for Agent Service.

## Overview

The Agent Service runs as a systemd service using Uvicorn/FastAPI, listening on all interfaces (`0.0.0.0:8000`) for external access.

## Authentication

### API Key Configuration

**Environment Variable:** `AGENT_API_KEY`

**Header Name:** `X-API-Key` (or `Authorization: Bearer <key>`)

### Generate a New API Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Or for a hex key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Public Routes (No Authentication Required)

| Route | Description |
|-------|-------------|
| `/` | Root homepage |
| `/health` | Health check |
| `/meta` | Service metadata |
| `/docs` | Swagger API documentation |
| `/redoc` | ReDoc API documentation |
| `/openapi.json` | OpenAPI schema |
| `/ui/*` | Web UI (all pages) |

### Protected Routes (API Key Required)

| Route Prefix | Description |
|--------------|-------------|
| `/agent/*` | Agent job endpoints |
| `/builder/*` | Builder endpoints |
| `/metrics/*` | Metrics endpoints |

### Using the API Key

**Via Header:**
```bash
curl -H "X-API-Key: YOUR_API_KEY" http://46.62.208.149:8000/agent/jobs
```

**Via Bearer Token:**
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" http://46.62.208.149:8000/agent/jobs
```

### Web UI Authentication

The Web UI (`/ui/*`) pages are publicly accessible. To make API calls:

1. Open the UI in your browser: `http://46.62.208.149:8000/ui`
2. Enter your API key in the input field in the top navigation bar
3. Click "Save" - the key is stored in `localStorage`
4. All subsequent API calls from the UI will include the key automatically

## Configuration

### Environment Variables

Located in `/etc/agent-service.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_API_KEY` | API key for authentication | (required) |
| `AGENT_ADMIN_KEY` | Admin key for admin endpoints | (optional) |
| `AGENT_KEY_HASH_SECRET` | Secret for key hashing | dev-secret |
| `PUBLIC_BASE_URL` | Public URL for the service | `http://localhost:8000` |
| `LISTEN_HOST` | Host to bind to | `0.0.0.0` |
| `PORT` | Port to listen on | `8000` |

### Systemd Service

Service file: `/etc/systemd/system/agent-service.service`

```ini
[Unit]
Description=Agent Service (FastAPI/Uvicorn)
After=network.target

[Service]
Type=simple
User=elhassan
Group=elhassan
WorkingDirectory=/home/elhassan/agent-service

Environment="PATH=/home/elhassan/agent-service/venv/bin"
ExecStart=/home/elhassan/agent-service/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000

Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Override file: `/etc/systemd/system/agent-service.service.d/override.conf`
```ini
[Service]
EnvironmentFile=/etc/agent-service.env
```

## Service Management Commands

### Start/Stop/Restart

```bash
# Start the service
sudo systemctl start agent-service.service

# Stop the service
sudo systemctl stop agent-service.service

# Restart the service
sudo systemctl restart agent-service.service

# Enable on boot
sudo systemctl enable agent-service.service
```

### Check Status

```bash
# View service status
sudo systemctl status agent-service.service

# View recent logs
sudo journalctl -u agent-service.service -f

# View logs since last boot
sudo journalctl -u agent-service.service -b
```

### Reload After Config Changes

```bash
# After editing /etc/systemd/system/agent-service.service
sudo systemctl daemon-reload
sudo systemctl restart agent-service.service

# After editing /etc/agent-service.env (just restart)
sudo systemctl restart agent-service.service
```

## Verification Commands

### On the Server

```bash
# Check service is running
sudo systemctl status agent-service.service

# Verify listening on 0.0.0.0:8000 (not 127.0.0.1)
sudo ss -ltnp | grep ':8000'
# Expected: LISTEN 0 2048 0.0.0.0:8000 0.0.0.0:*

# Test public endpoints (no auth needed)
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/meta
curl -i http://127.0.0.1:8000/ui/jobs

# Test protected endpoint WITHOUT key (should return 401)
curl -i http://127.0.0.1:8000/agent/jobs
# Expected: {"detail":"Missing API key"}

# Test protected endpoint WITH key (should succeed)
curl -i -H "X-API-Key: YOUR_API_KEY" http://127.0.0.1:8000/agent/jobs
```

### From External Machine (Mac/other)

```bash
# Public endpoints (no key needed)
curl -i http://46.62.208.149:8000/health
curl -s http://46.62.208.149:8000/meta | jq

# Protected endpoints (key required)
curl -H "X-API-Key: YOUR_API_KEY" http://46.62.208.149:8000/agent/jobs

# Open in browser (no key needed for UI)
open http://46.62.208.149:8000/ui
open http://46.62.208.149:8000/docs
```

## URLs

| Endpoint | URL | Auth Required |
|----------|-----|---------------|
| Root | http://46.62.208.149:8000/ | No |
| Health | http://46.62.208.149:8000/health | No |
| Meta | http://46.62.208.149:8000/meta | No |
| API Docs | http://46.62.208.149:8000/docs | No |
| ReDoc | http://46.62.208.149:8000/redoc | No |
| Web UI | http://46.62.208.149:8000/ui | No |
| API Endpoints | http://46.62.208.149:8000/agent/* | **Yes** |
| Builder | http://46.62.208.149:8000/builder/* | **Yes** |

## Firewall Configuration

### UFW (Ubuntu Firewall)

```bash
# Check status
sudo ufw status

# Allow port 8000
sudo ufw allow 8000/tcp
sudo ufw reload

# Verify rule added
sudo ufw status | grep 8000
```

### Cloud Provider Security Groups

Ensure your cloud provider (AWS, GCP, Azure, etc.) security group allows inbound TCP port 8000.

## Troubleshooting

### Service won't start

```bash
# Check for syntax errors
sudo systemctl status agent-service.service -l

# Check full logs
sudo journalctl -u agent-service.service --no-pager -n 50

# Test manually
cd /home/elhassan/agent-service
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Can't connect from external

1. **Check listening interface:**
   ```bash
   sudo ss -ltnp | grep ':8000'
   ```
   Must show `0.0.0.0:8000`, NOT `127.0.0.1:8000`

2. **Check firewall:**
   ```bash
   sudo ufw status | grep 8000
   ```

3. **Check cloud security group** - ensure inbound TCP 8000 is allowed

### Port already in use

```bash
# Find what's using port 8000
sudo ss -ltnp | grep ':8000'
sudo lsof -i :8000

# Kill rogue process if needed
sudo kill <PID>

# Restart service
sudo systemctl restart agent-service.service
```

### Getting "Missing API key" error

1. **For public routes** - This should not happen. Check the route is in the public list.

2. **For protected routes** - This is expected. Provide the API key:
   ```bash
   curl -H "X-API-Key: YOUR_KEY" http://46.62.208.149:8000/agent/jobs
   ```

3. **For Web UI** - Enter your API key in the UI's top navigation bar and click Save.

## Health Monitoring

### Simple monitoring script

```bash
#!/bin/bash
# /home/elhassan/check_agent.sh
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health)
if [ "$RESPONSE" != "200" ]; then
    echo "Agent Service DOWN! Response: $RESPONSE"
    sudo systemctl restart agent-service.service
fi
```

Add to crontab:
```bash
*/5 * * * * /home/elhassan/check_agent.sh >> /var/log/agent-monitor.log 2>&1
```
