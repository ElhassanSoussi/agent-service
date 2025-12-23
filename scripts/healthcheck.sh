#!/usr/bin/env bash
# =============================================================================
# Health Check Script
# Verifies the service is healthy with retry logic
# =============================================================================
set -euo pipefail

# Configuration
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
MAX_RETRIES="${MAX_RETRIES:-30}"
RETRY_INTERVAL="${RETRY_INTERVAL:-2}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_info "Checking health at ${HEALTH_URL}"
log_info "Will retry up to ${MAX_RETRIES} times (${RETRY_INTERVAL}s interval)"

for i in $(seq 1 "${MAX_RETRIES}"); do
    if curl -fsS "${HEALTH_URL}" > /dev/null 2>&1; then
        log_info "Health check passed on attempt ${i}"
        
        # Verify response content
        RESPONSE=$(curl -sS "${HEALTH_URL}" 2>/dev/null)
        if echo "${RESPONSE}" | grep -q '"status".*"ok"'; then
            log_info "Service is healthy: ${RESPONSE}"
            exit 0
        else
            log_warn "Unexpected response: ${RESPONSE}"
        fi
    fi
    
    if [[ "${i}" -lt "${MAX_RETRIES}" ]]; then
        log_warn "Attempt ${i}/${MAX_RETRIES} failed, retrying in ${RETRY_INTERVAL}s..."
        sleep "${RETRY_INTERVAL}"
    fi
done

log_error "Health check failed after ${MAX_RETRIES} attempts"
exit 1
