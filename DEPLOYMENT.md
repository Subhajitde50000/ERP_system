# ERP System — Production Deployment & DevOps Guide

This guide covers running the ERP system with **Docker**, configuring **Docker Compose** for local and production environments, setting up **CI/CD with GitHub Actions**, and executing **automated database backups**.

---

## Architecture Overview

```
[ Internet / Browser / Mobile App ]
                │
                ▼ (Ports 80 / 443)
       ┌─────────────────┐
       │   Nginx Proxy   │
       └────────┬────────┘
                │
    ┌───────────┴───────────┐
    ▼                       ▼
┌──────────────┐    ┌──────────────┐
│ Next.js Web  │    │ FastAPI API  │
│ (Port 3000)  │    │ (Port 8000)  │
└──────────────┘    └───────┬──────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
      ┌──────────────┐            ┌──────────────┐
      │  PostgreSQL  │            │    Redis     │
      │ (Port 5432)  │            │ (Port 6379)  │
      └──────────────┘            └──────────────┘
```

---

## 1. Quick Start with Docker (Local Development)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker Engine 20+ & Docker Compose v2)

### Steps
1. **Clone and enter repository**:
   ```bash
   git clone <repo-url>
   cd ERP
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.docker.example .env
   ```

3. **Start all services with Docker Compose**:
   ```bash
   docker compose up --build
   ```

4. **Access the application**:
   - **Frontend**: [http://localhost:3000](http://localhost:3000)
   - **Backend API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **API Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

5. **Stop services**:
   ```bash
   docker compose down
   ```

---

## 2. Production Deployment

### Option A: Automated One-Command Deployment Script
For Linux / Ubuntu / Debian VPS:
```bash
# Make script executable
chmod +x scripts/*.sh

# Run production deploy
./scripts/deploy.sh
```

For Windows PowerShell:
```powershell
.\scripts\deploy.ps1
```

### Option B: Manual Production Docker Compose
1. Configure `.env` with production secrets:
   ```bash
   cp .env.docker.example .env
   # Edit .env: Set secure JWT_SECRET_KEY, POSTGRES_PASSWORD, PUBLIC_ROOT_DOMAIN, etc.
   ```

2. Build and run the production stack:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

3. Run Alembic database migrations:
   ```bash
   docker compose -f docker-compose.prod.yml run --rm migration
   ```

4. Seed initial superadmin (if fresh installation):
   ```bash
   docker compose -f docker-compose.prod.yml exec backend python scripts/create_superadmin.py
   ```

---

## 3. CI/CD Pipelines (GitHub Actions)

Two GitHub Actions workflows are included in `.github/workflows/`:

### 1. `ci.yml` (Continuous Integration)
Triggers on every `push` and `pull_request`:
- **Backend CI**: Boots PostgreSQL 16 & Redis 7 services, sets up Python 3.12, tests imports, and runs all `pytest` suites.
- **Frontend CI**: Sets up Node.js 20, lints with `eslint`, runs `vitest` unit tests, and tests Next.js production compilation (`next build`).
- **Docker Build Check**: Verifies that both `backend/Dockerfile` and `fontend/Dockerfile` build cleanly without layer errors.

### 2. `deploy.yml` (Continuous Delivery)
Triggers on `push` to `main`:
- Builds Docker images with GitHub Action layer caching.
- Publishes container images to GitHub Container Registry (`ghcr.io`).
- Triggers remote SSH deployment on your production server when secrets (`PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`) are set in repository settings.

---

## 4. SSL / HTTPS Setup with Certbot

To enable HTTPS on your production domain:

1. Install Certbot on your host server:
   ```bash
   sudo apt-get install certbot
   ```

2. Issue wildcard SSL certificate:
   ```bash
   sudo certbot certonly --manual --preferred-challenges=dns \
     -d "xyz.com" -d "*.xyz.com"
   ```

3. Mount your certificates into `./certbot/conf` and update `nginx/default.conf` to enable HTTPS listening on port 443.

---

## 5. Database Backup and Disaster Recovery

### Automated Daily Backup (Cron)
Run manual backup anytime:
```bash
chmod +x scripts/backup-db.sh
./scripts/backup-db.sh
```

To schedule daily backups at 02:00 AM, add a crontab entry:
```bash
crontab -e
# Add line:
0 2 * * * /opt/erp/scripts/backup-db.sh >> /var/log/erp_backup.log 2>&1
```

### Database Restore
To restore from a previous backup `.sql.gz`:
```bash
chmod +x scripts/restore-db.sh
./scripts/restore-db.sh backups/erp_backup_YYYYMMDD_HHMMSS.sql.gz
```

---

## 6. Security Hardening & Best Practices

### Security Headers
The ERP reverse proxy (`nginx/default.conf`) and Next.js frontend (`fontend/next.config.mjs`) enforce strict HTTP security headers:
- **Content-Security-Policy (CSP)**: Restricts script, style, and iframe sources to prevent Cross-Site Scripting (XSS) and code injection.
- **Strict-Transport-Security (HSTS)**: `max-age=63072000; includeSubDomains; preload` enforces HTTPS exclusively in production.
- **X-Frame-Options**: `SAMEORIGIN` prevents clickjacking attacks.
- **X-Content-Type-Options**: `nosniff` prevents MIME-type confusion attacks.
- **Referrer-Policy**: `strict-origin-when-cross-origin` protects sensitive URL paths from leaking.
- **Permissions-Policy**: Restricts access to device hardware (camera and microphone allowed only for self during live classrooms; sensitive sensors disabled).

### Token Storage & XSS Mitigation
- **Short-Lived Access Tokens**: Stored **only in memory** (never in `localStorage` or `sessionStorage`).
- **Refresh Tokens**: Issued and delivered in secure **`httpOnly` cookies** (`SameSite=Lax`, `Secure` in production, `path=/`) for web clients. Because JavaScript cannot access `httpOnly` cookies, malicious scripts injected via potential XSS vectors cannot exfiltrate the persistent refresh token.
- **Mobile Compatibility**: Mobile clients receive the token in the API response body and transmit it in headers/body, maintaining seamless full-duplex compatibility.

