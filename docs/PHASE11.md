# Phase 11: CI/CD Deployment

This document describes the automated deployment system for the Agent Service.

## Overview

The deployment system provides:
- **Automated deployments** via GitHub Actions on version tags
- **Database backups** before each deployment
- **Health checks** to verify successful deployment
- **Automatic rollback** if deployment fails
- **Zero-downtime** updates with Docker Compose

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│  GitHub Actions     │     │  Production Server  │
│                     │     │                     │
│  1. Run tests       │────▶│  /opt/agent-service │
│  2. SSH to server   │     │                     │
│  3. Run deploy.sh   │     │  ├── scripts/       │
│  4. Verify health   │     │  ├── data/          │
│                     │     │  ├── backups/       │
└─────────────────────┘     │  └── docker-compose │
                            └─────────────────────┘
```

## Quick Start

### 1. Set Up GitHub Secrets

Go to your repository → Settings → Secrets and variables → Actions

Add these secrets:

| Secret | Description | Example |
|--------|-------------|---------|
| `SSH_HOST` | Server IP or hostname | `192.168.1.100` or `myserver.com` |
| `SSH_USER` | SSH username | `deploy` |
| `SSH_PORT` | SSH port (optional) | `22` |
| `SSH_PRIVATE_KEY` | Private key content | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `DEPLOY_PATH` | Deployment directory | `/opt/agent-service` |
| `HEALTH_CHECK_URL` | Public health URL (optional) | `https://api.example.com/health` |

### 2. Prepare the Server

Run these commands once on your server:

```bash
# Create deployment directory
sudo mkdir -p /opt/agent-service
sudo chown $USER:$USER /opt/agent-service

# Clone the repository
cd /opt/agent-service
git clone https://github.com/YOUR_USERNAME/agent-service.git .

# Create required directories
mkdir -p data backups

# Copy and configure environment
cp .env.example .env
nano .env  # Edit with your actual secrets

# Make scripts executable
chmod +x scripts/*.sh

# Install Docker and Docker Compose if not present
# (Follow Docker's official installation guide)

# Initial deployment
docker compose up -d

# Verify
curl http://127.0.0.1:8000/health
```

### 3. Create SSH Deploy Key

On your **local machine**:

```bash
# Generate a new SSH key for deployments
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy

# Display the public key (add to server)
cat ~/.ssh/github_deploy.pub

# Display the private key (add to GitHub secret SSH_PRIVATE_KEY)
cat ~/.ssh/github_deploy
```

On the **server**:

```bash
# Add the public key to authorized_keys
echo "PUBLIC_KEY_CONTENT" >> ~/.ssh/authorized_keys
```

### 4. Deploy

Create and push a version tag:

```bash
# Create a release tag
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions will automatically:
1. Run tests
2. SSH to your server
3. Execute the deployment script
4. Verify the health check
5. Rollback if anything fails

---

## Deployment Scripts

### scripts/deploy.sh

Main deployment script that orchestrates the entire process:

```bash
./scripts/deploy.sh v1.0.0  # Deploy specific tag
./scripts/deploy.sh         # Deploy current branch
```

**Steps:**
1. Record current commit (for rollback)
2. Fetch latest code from origin
3. Checkout target tag
4. Run backup script
5. Build and start containers
6. Run health check
7. Rollback if health check fails

**Environment variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `DEPLOY_DIR` | Script's parent | Deployment directory |
| `HEALTH_URL` | `http://127.0.0.1:8000/health` | Health check URL |
| `SKIP_BACKUP` | `false` | Skip database backup |
| `COMPOSE_FILE` | `docker-compose.yml` | Compose file path |

### scripts/backup_sqlite.sh

Creates timestamped database backups:

```bash
./scripts/backup_sqlite.sh
```

**Features:**
- Creates backup in `./backups/jobs_YYYYMMDD_HHMMSS.db`
- Uses SQLite's online backup API if available
- Keeps last 20 backups by default
- Fails deployment if backup fails

**Environment variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_BACKUPS` | `20` | Number of backups to keep |

### scripts/healthcheck.sh

Verifies service health with retries:

```bash
./scripts/healthcheck.sh
```

**Environment variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `HEALTH_URL` | `http://127.0.0.1:8000/health` | Health check URL |
| `MAX_RETRIES` | `30` | Number of retry attempts |
| `RETRY_INTERVAL` | `2` | Seconds between retries |

---

## GitHub Actions Workflows

### .github/workflows/deploy.yml

**Triggers:**
- Push of tags matching `v*` (e.g., `v1.0.0`)
- Manual workflow dispatch

**Jobs:**
1. **test**: Runs linter and pytest
2. **deploy**: SSHs to server and runs deploy script
3. **notify-failure**: Reports deployment failures

### .github/workflows/ci.yml

Runs on every push/PR:
- Linting with ruff
- Tests with pytest
- Docker build verification

---

## Backup & Recovery

### Backup Location

Backups are stored in `/opt/agent-service/backups/`:

```
backups/
├── jobs_20251219_120000.db
├── jobs_20251219_140000.db
└── jobs_20251219_160000.db
```

### Manual Backup

```bash
cd /opt/agent-service
./scripts/backup_sqlite.sh
```

### Restore from Backup

```bash
# Stop the service
docker compose down

# Restore database
cp backups/jobs_20251219_120000.db data/jobs.db

# Start service
docker compose up -d
```

### Backup Retention

By default, the last 20 backups are kept. Older backups are automatically deleted.

To change retention:
```bash
MAX_BACKUPS=50 ./scripts/backup_sqlite.sh
```

---

## Rollback

### Automatic Rollback

If the health check fails after deployment, the script automatically:
1. Checks out the previous commit
2. Restarts containers with previous version
3. Verifies health again

### Manual Rollback

```bash
cd /opt/agent-service

# List available tags
git tag -l

# Rollback to specific version
./scripts/deploy.sh v1.0.0

# Or checkout and restart manually
git checkout v1.0.0
docker compose up -d --force-recreate
```

---

## Production Configuration

### Using Production Compose File

For servers behind nginx:

```bash
# Use production compose (binds to localhost only)
docker compose -f docker-compose.prod.yml up -d
```

### Environment File

Never commit `.env` with real secrets. Use `.env.example` as template:

```bash
# /opt/agent-service/.env

# REQUIRED
AGENT_ADMIN_KEY=<generate with: openssl rand -hex 32>
AGENT_KEY_HASH_SECRET=<generate with: openssl rand -hex 32>

# Optional
AGENT_API_KEY=<legacy key if needed>
AGENT_PLANNER_MODE=rules
```

### Nginx Configuration

Example nginx config for SSL termination:

```nginx
server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Troubleshooting

### Deployment Fails

1. Check GitHub Actions logs
2. SSH to server and check:
   ```bash
   cd /opt/agent-service
   docker compose logs -f agent
   ```

### Health Check Fails

```bash
# Check if container is running
docker compose ps

# Check container logs
docker compose logs agent

# Test health endpoint manually
curl -v http://127.0.0.1:8000/health
```

### SSH Connection Fails

1. Verify SSH key is correct in GitHub secrets
2. Check server SSH config allows key authentication
3. Verify firewall allows SSH port

### Database Issues

```bash
# Check database file
ls -la data/jobs.db

# Verify database integrity
sqlite3 data/jobs.db "PRAGMA integrity_check;"

# Restore from backup if corrupted
cp backups/jobs_LATEST.db data/jobs.db
docker compose restart
```

---

## Security Notes

1. **Never commit `.env`** - Use `.env.example` as template
2. **Rotate secrets regularly** - Update `AGENT_ADMIN_KEY` periodically
3. **Use SSH keys** - Never password authentication for deployments
4. **Limit SSH access** - Use dedicated deploy user with minimal permissions
5. **Bind to localhost** - Use `docker-compose.prod.yml` behind nginx
6. **No secrets in logs** - Scripts never echo sensitive values

---

## Release Checklist

Before creating a release tag:

- [ ] All tests pass locally: `make test`
- [ ] Linting passes: `make lint`
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (if applicable)
- [ ] Version bumped in code (if tracked)

Create release:

```bash
git tag -a v1.0.0 -m "Release v1.0.0: Description"
git push origin v1.0.0
```

Monitor deployment:
1. Check GitHub Actions workflow
2. Verify health endpoint
3. Test API functionality
