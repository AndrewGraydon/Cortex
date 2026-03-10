#!/usr/bin/env bash
# Cortex Backup Script
# Creates a compressed backup of data/ + config/ + .env
# Excludes models/ and data/sandbox/
# Rotates old backups (keeps last 7)
set -euo pipefail

BACKUP_DIR="${CORTEX_BACKUP_DIR:-backups}"
DATA_DIR="${CORTEX_DATA_DIR:-data}"
CONFIG_DIR="${CORTEX_CONFIG_DIR:-config}"
MAX_BACKUPS="${CORTEX_MAX_BACKUPS:-7}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/cortex-${TIMESTAMP}.tar.gz"

# Create backup directory if needed
mkdir -p "${BACKUP_DIR}"

echo "Creating backup: ${BACKUP_FILE}"

# Build tar arguments
TAR_ARGS=()

# Add data directory if it exists
if [ -d "${DATA_DIR}" ]; then
    TAR_ARGS+=("${DATA_DIR}")
fi

# Add config directory if it exists
if [ -d "${CONFIG_DIR}" ]; then
    TAR_ARGS+=("${CONFIG_DIR}")
fi

# Add .env if it exists
if [ -f ".env" ]; then
    TAR_ARGS+=(".env")
fi

if [ ${#TAR_ARGS[@]} -eq 0 ]; then
    echo "Error: No files to back up"
    exit 1
fi

# Create backup, excluding models/ and sandbox/
tar czf "${BACKUP_FILE}" \
    --exclude="${DATA_DIR}/models" \
    --exclude="${DATA_DIR}/sandbox" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    "${TAR_ARGS[@]}"

# Verify the backup
if tar tzf "${BACKUP_FILE}" > /dev/null 2>&1; then
    FILE_COUNT=$(tar tzf "${BACKUP_FILE}" | wc -l)
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "Backup verified: ${FILE_COUNT} files, ${FILE_SIZE}"
else
    echo "Error: Backup verification failed!"
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Rotate old backups (keep last MAX_BACKUPS)
BACKUP_COUNT=$(ls -1 "${BACKUP_DIR}"/cortex-*.tar.gz 2>/dev/null | wc -l)
if [ "${BACKUP_COUNT}" -gt "${MAX_BACKUPS}" ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
    echo "Rotating: removing ${REMOVE_COUNT} old backup(s)"
    ls -1t "${BACKUP_DIR}"/cortex-*.tar.gz | tail -n "${REMOVE_COUNT}" | xargs rm -f
fi

echo "Backup complete: ${BACKUP_FILE}"
