#!/usr/bin/env bash
# ==============================================================================
# ERP Platform — Automated PostgreSQL Backup Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKUP_DIR="${ROOT_DIR}/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/erp_backup_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=7

mkdir -p "${BACKUP_DIR}"

echo "📦 Starting PostgreSQL backup at $(date)..."

# Source environment variables if available
if [ -f "${ROOT_DIR}/.env" ]; then
    export $(grep -v '^#' "${ROOT_DIR}/.env" | xargs)
fi

DB_CONTAINER=$(docker ps --filter "name=postgres" --format "{{.Names}}" | head -n 1)
DB_USER="${POSTGRES_USER:-erp_user}"
DB_NAME="${POSTGRES_DB:-erp_db}"

if [ -z "${DB_CONTAINER}" ]; then
    echo "❌ Error: PostgreSQL container is not running!"
    exit 1
fi

# Run pg_dump inside container and compress output
docker exec -t "${DB_CONTAINER}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${BACKUP_FILE}"

FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "✅ Backup completed successfully: ${BACKUP_FILE} (${FILE_SIZE})"

# Delete backups older than RETENTION_DAYS
echo "🧹 Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "erp_backup_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete

echo "🎉 Backup routine finished."
