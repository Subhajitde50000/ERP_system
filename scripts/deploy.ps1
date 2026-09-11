# ==============================================================================
# ERP Platform — Production/Staging Deployment Script for Windows (PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " Starting ERP Deployment (PowerShell)" -ForegroundColor Cyan
Write-Host " Root: $RootDir" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 1. Check for .env file
if (-not (Test-Path ".env")) {
    Write-Host "❌ Error: .env file not found!" -ForegroundColor Red
    Write-Host "👉 Copy .env.docker.example to .env and configure secrets." -ForegroundColor Yellow
    exit 1
}

# 2. Rebuild and Launch Containers
Write-Host "🐳 Building and starting containers..." -ForegroundColor Green
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# 3. Run Alembic Database Migrations
Write-Host "📦 Executing Database Migrations..." -ForegroundColor Green
docker compose -f docker-compose.prod.yml run --rm migration

# 4. Health Check
Write-Host "🩺 Verifying Backend Health..." -ForegroundColor Green
$MaxRetries = 15
$Retry = 0
$Healthy = $false

while ($Retry -lt $MaxRetries) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($response.status -eq "healthy") {
            $Healthy = $true
            break
        }
    } catch {
        # Retry
    }
    Write-Host "⏳ Waiting for API health... ($($Retry + 1)/$MaxRetries)"
    Start-Sleep -Seconds 3
    $Retry++
}

if (-not $Healthy) {
    Write-Host "❌ Backend Health Check Failed!" -ForegroundColor Red
    docker compose -f docker-compose.prod.yml logs --tail=50
    exit 1
}

Write-Host "✅ Health Check PASSED!" -ForegroundColor Green
Write-Host "🎉 ERP System deployed and running successfully!" -ForegroundColor Green
