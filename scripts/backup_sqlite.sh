#!/usr/bin/env bash
# =============================================================================
# SQLite Backup Script
# Creates timestamped backups before deployment
# Keeps only the last N backups to save disk space
# =============================================================================
set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="${PROJECT_DIR}/data"
BACKUP_DIR="${PROJECT_DIR}/backups"
DB_FILE="${DATA_DIR}/jobs.db"
MAX_BACKUPS=${MAX_BACKUPS:-20}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Check if database exists
if [[ ! -f "${DB_FILE}" ]]; then
    log_warn "Database file not found at ${DB_FILE}"
    log_info "This might be a fresh install - skipping backup"
    exit 0
fi

# Create timestamped backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/jobs_${TIMESTAMP}.db"

log_info "Creating backup: ${BACKUP_FILE}"

# Use sqlite3 .backup command if available for consistency
# Otherwise fall back to cp
if command -v sqlite3 &> /dev/null; then
    # Use SQLite's online backup API for consistency
    sqlite3 "${DB_FILE}" ".backup '${BACKUP_FILE}'"
else
    # Fall back to file copy (safe if no writes during copy)
    cp "${DB_FILE}" "${BACKUP_FILE}"
fi

# Verify backup was created
if [[ ! -f "${BACKUP_FILE}" ]]; then
    log_error "Backup failed - file not created"
    exit 1
fi

# Verify backup is not empty
BACKUP_SIZE=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}" 2>/dev/null)
if [[ "${BACKUP_SIZE}" -eq 0 ]]; then
    log_error "Backup failed - file is empty"
    rm -f "${BACKUP_FILE}"
    exit 1
fi

log_info "Backup created successfully (${BACKUP_SIZE} bytes)"

# Clean up old backups (keep only MAX_BACKUPS)
BACKUP_COUNT=$(find "${BACKUP_DIR}" -name "jobs_*.db" -type f | wc -l)
if [[ "${BACKUP_COUNT}" -gt "${MAX_BACKUPS}" ]]; then
    DELETE_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
    log_info "Cleaning up ${DELETE_COUNT} old backup(s)..."
    
    # Delete oldest backups
    find "${BACKUP_DIR}" -name "jobs_*.db" -type f -printf '%T+ %p\n' | \
        sort | head -n "${DELETE_COUNT}" | cut -d' ' -f2- | \
        xargs -r rm -f
    
    log_info "Kept ${MAX_BACKUPS} most recent backups"
fi

# List current backups
log_info "Current backups:"
ls -lh "${BACKUP_DIR}"/jobs_*.db 2>/dev/null | tail -5 || true

exit 0
