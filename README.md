# ERP_system — xyz.com Multi-Tenant ERP + LMS

A multi-tenant SaaS ERP + learning platform for schools, colleges and
universities. One platform account owns many institutions (AWS/Shopify/Zoho
model), each an isolated tenant on its own subdomain, with 16 modules.

**Read [`MANUAL.md`](./MANUAL.md)** for the full setup, the three login systems,
the live admin features, the API reference and the production checklist.

## Quick start

### Option A: Docker (Recommended)

```bash
# 1. Copy Docker environment variables
cp .env.docker.example .env

# 2. Start PostgreSQL, Redis, Backend & Frontend
docker compose up --build

# Web: http://localhost:3000 | API Docs: http://localhost:8000/docs
```

For complete production deployment, CI/CD, and backup instructions, see **[`DEPLOYMENT.md`](./DEPLOYMENT.md)**.

### Option B: Local Manual Setup

```bash
# 1. Database (PostgreSQL)
psql -U erp_user -d erp_db -f database/database.sql


# 2. Backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env   # edit secrets
python scripts/seed_data.py && python run.py              # :8000

# 3. Frontend
cd ../fontend && npm ci && cp .env.example .env.local     # NEXT_PUBLIC_API_URL
npm run dev                                               # :3000
```

See `doc/` for architecture, system flow and the owner-account model.

