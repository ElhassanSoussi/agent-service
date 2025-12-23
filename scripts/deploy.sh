#!/usr/bin/env bash
# =============================================================================
# Deployment Script
# Deploys the agent-service with backup, update, healthcheck, and rollback
# 
# Usage: ./scripts/deploy.sh [TAG]
#   TAG: Git tag to deploy (e.g., v1.0.0). If omitted, uses current branch.
#
# Environment variables:
#   DEPLOY_DIR: Override deployment directory (default: script's parent dir)
#   HEALTH_URL: Override health check URL (default: http://127.0.0.1:8000/health)
#   SKIP_BACKUP: Set to "true" to skip backup (not recommended)
#   COMPOSE_FILE: Override compose file path
# =============================================================================
set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="${DEPLOY_DIR:-$(dirname "$SCRIPT_DIR")}"
COMPOSE_FILE="${COMPOSE_FILE:-${DEPLOY_DIR}/docker-compose.yml}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
TARGET_TAG="${1:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

# Store the previous commit for potential rollback
PREVIOUS_COMMIT=""
ROLLBACK_NEEDED=false

cleanup() {
    if [[ "${ROLLBACK_NEEDED}" == "true" ]]; then
        log_error "Deployment failed - initiating rollback"
        perform_rollback
    fi
}

trap cleanup EXIT

perform_rollback() {
    if [[ -z "${PREVIOUS_COMMIT}" ]]; then
        log_error "No previous commit recorded - cannot rollback"
        return 1
    fi
    
    log_step "Rolling back to previous commit: ${PREVIOUS_COMMIT}"
    
    cd "${DEPLOY_DIR}"
    git checkout "${PREVIOUS_COMMIT}" --quiet
    
    log_step "Restarting containers with previous version..."
    docker compose -f "${COMPOSE_FILE}" up -d --force-recreate
    
    log_step "Verifying rollback health..."
    if "${SCRIPT_DIR}/healthcheck.sh"; then
        log_info "Rollback successful - service is healthy"
        ROLLBACK_NEEDED=false
        return 0
    else
        log_error "Rollback failed - service is still unhealthy"
        return 1
    fi
}

# =============================================================================
# Main Deployment Process
# =============================================================================

log_info "=========================================="
log_info "Agent Service Deployment"
log_info "=========================================="
log_info "Deploy directory: ${DEPLOY_DIR}"
log_info "Target tag: ${TARGET_TAG:-'(current branch)'}"
log_info "Health URL: ${HEALTH_URL}"

# Step 1: Change to deploy directory
log_step "1/7 Changing to deploy directory"
cd "${DEPLOY_DIR}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    log_error "docker-compose.yml not found at ${COMPOSE_FILE}"
    exit 1
fi

# Step 2: Record current commit for rollback
log_step "2/7 Recording current state for rollback"
PREVIOUS_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")
if [[ -n "${PREVIOUS_COMMIT}" ]]; then
    log_info "Previous commit: ${PREVIOUS_COMMIT:0:12}"
else
    log_warn "Could not determine previous commit"
fi

# Step 3: Fetch latest code
log_step "3/7 Fetching latest code from origin"
git fetch --tags --prune origin

# Step 4: Checkout target tag/branch
if [[ -n "${TARGET_TAG}" ]]; then
    log_step "4/7 Checking out tag: ${TARGET_TAG}"
    
    # Verify tag exists
    if ! git rev-parse "${TARGET_TAG}" >/dev/null 2>&1; then
        log_error "Tag '${TARGET_TAG}' not found"
        exit 1
    fi
    
    git checkout "${TARGET_TAG}" --quiet
    CURRENT_VERSION="${TARGET_TAG}"
else
    log_step "4/7 Pulling latest changes"
    git pull --quiet origin "$(git rev-parse --abbrev-ref HEAD)"
    CURRENT_VERSION="$(git rev-parse --short HEAD)"
fi

log_info "Deploying version: ${CURRENT_VERSION}"

# Step 5: Backup database
log_step "5/7 Creating database backup"
if [[ "${SKIP_BACKUP:-false}" == "true" ]]; then
    log_warn "Skipping backup (SKIP_BACKUP=true)"
else
    if ! "${SCRIPT_DIR}/backup_sqlite.sh"; then
        log_error "Backup failed - aborting deployment"
        exit 1
    fi
fi

# Enable rollback from this point
ROLLBACK_NEEDED=true

# Step 6: Update containers
log_step "6/7 Updating containers"

# Pull latest images (if using pre-built images)
# docker compose -f "${COMPOSE_FILE}" pull --quiet 2>/dev/null || true

# Build and start containers
log_info "Building and starting containers..."
docker compose -f "${COMPOSE_FILE}" build --quiet
docker compose -f "${COMPOSE_FILE}" up -d --force-recreate

# Wait a moment for container to initialize
log_info "Waiting for container initialization..."
sleep 3

# Step 7: Health check
log_step "7/7 Verifying deployment health"
export HEALTH_URL
if ! "${SCRIPT_DIR}/healthcheck.sh"; then
    log_error "Health check failed - triggering rollback"
    exit 1
fi

# Success - disable rollback
ROLLBACK_NEEDED=false

log_info "=========================================="
log_info "Deployment completed successfully!"
log_info "Version: ${CURRENT_VERSION}"
log_info "=========================================="

# Show running containers
docker compose -f "${COMPOSE_FILE}" ps

exit 0
