#!/usr/bin/env bash
# ==============================================================================
# ERP Platform — PostgreSQL Database Restore Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKUP_FILE="${1:-}"

if [ -z "${BACKUP_FILE}" ]; then
    echo "Usage: ./scripts/restore-db.sh <path-to-backup.sql.gz>"
    echo ""
    echo "Available backups in backups/:"
    ls -lh "${ROOT_DIR}/backups" 2>/dev/null || echo "No backups found."
    exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "❌ Error: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

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

echo "⚠️  WARNING: Restoring will overwrite existing database '${DB_NAME}'!"
read -p "Are you sure you want to proceed? (yes/no): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo "🔄 Restoring ${BACKUP_FILE} into ${DB_NAME}..."
gunzip -c "${BACKUP_FILE}" | docker exec -i "${DB_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}"

echo "✅ Database restore completed successfully!"
