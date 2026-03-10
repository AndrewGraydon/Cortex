#!/usr/bin/env bash
# Cortex Restore Script
# Restores from a backup tarball with integrity verification
# Usage: scripts/restore.sh <backup-file.tar.gz>
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-file.tar.gz>"
    echo "Available backups:"
    ls -1t backups/cortex-*.tar.gz 2>/dev/null || echo "  (none found)"
    exit 1
fi

BACKUP_FILE="$1"
STAGING_DIR=$(mktemp -d)

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "Error: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

echo "Restoring from: ${BACKUP_FILE}"
echo "Staging directory: ${STAGING_DIR}"

# Verify backup is readable
if ! tar tzf "${BACKUP_FILE}" > /dev/null 2>&1; then
    echo "Error: Backup file is corrupted or not a valid tar.gz"
    rm -rf "${STAGING_DIR}"
    exit 1
fi

# Extract to staging
echo "Extracting to staging..."
tar xzf "${BACKUP_FILE}" -C "${STAGING_DIR}"

# Check SQLite database integrity
echo "Checking database integrity..."
INTEGRITY_OK=true
for db in "${STAGING_DIR}"/data/*.db; do
    if [ -f "${db}" ]; then
        RESULT=$(sqlite3 "${db}" "PRAGMA integrity_check;" 2>&1 || echo "FAILED")
        if [ "${RESULT}" = "ok" ]; then
            echo "  ✓ $(basename "${db}")"
        else
            echo "  ✗ $(basename "${db}"): ${RESULT}"
            INTEGRITY_OK=false
        fi
    fi
done

if [ "${INTEGRITY_OK}" = false ]; then
    echo "Error: Database integrity check failed!"
    echo "Staging directory preserved at: ${STAGING_DIR}"
    exit 1
fi

# Copy to live directories
echo "Restoring files..."
if [ -d "${STAGING_DIR}/data" ]; then
    cp -r "${STAGING_DIR}/data/"* data/ 2>/dev/null || true
fi
if [ -d "${STAGING_DIR}/config" ]; then
    cp -r "${STAGING_DIR}/config/"* config/ 2>/dev/null || true
fi
if [ -f "${STAGING_DIR}/.env" ]; then
    cp "${STAGING_DIR}/.env" .env
fi

# Clean up staging
rm -rf "${STAGING_DIR}"

echo "Restore complete from: ${BACKUP_FILE}"
echo "Note: Restart Cortex services to pick up restored data."
