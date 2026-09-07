#!/usr/bin/env bash
# ==============================================================================
# ERP Platform — Production Deployment Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "========================================="
echo " Starting ERP Production Deployment"
echo " Time: $(date)"
echo "========================================="

# 1. Verify Environment File
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found in ${ROOT_DIR}!"
    echo "👉 Please copy .env.docker.example to .env and configure secrets."
    exit 1
fi

# 2. Pull latest git code (if in git repo)
if [ -d .git ]; then
    echo "📥 Pulling latest git changes..."
    git fetch origin
    git pull origin main || echo "⚠️ Warning: git pull returned non-zero, continuing with local files..."
fi

# 3. Build and Start Containers
echo "🐳 Building and starting production containers..."
docker compose -f docker-compose.prod.yml down --remove-orphans || true
docker compose -f docker-compose.prod.yml build --pull
docker compose -f docker-compose.prod.yml up -d

# 4. Run Alembic Database Migrations
echo "📦 Running Alembic database migrations..."
docker compose -f docker-compose.prod.yml run --rm migration || {
    echo "❌ Database migration failed! Inspecting backend logs..."
    docker compose -f docker-compose.prod.yml logs backend
    exit 1
}

# 5. Health Check Verification
echo "🩺 Verifying Backend Health..."
MAX_RETRIES=15
RETRY_COUNT=0
HEALTH_URL="http://localhost/health"

until curl -s -f "${HEALTH_URL}" > /dev/null || [ $RETRY_COUNT -eq $MAX_RETRIES ]; do
    echo "⏳ Waiting for backend to become healthy... ($((RETRY_COUNT+1))/$MAX_RETRIES)"
    sleep 3
    RETRY_COUNT=$((RETRY_COUNT+1))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ Health check timed out after $((MAX_RETRIES * 3)) seconds!"
    docker compose -f docker-compose.prod.yml logs --tail=50
    exit 1
fi

echo "✅ Health check PASSED!"

# 6. Cleanup Dangling Docker Images & Volumes
echo "🧹 Pruning dangling docker images..."
docker image prune -f

echo "========================================="
echo " 🎉 Deployment Completed Successfully!"
echo " Time: $(date)"
echo "========================================="
