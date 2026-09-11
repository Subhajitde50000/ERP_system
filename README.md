# 🎓 shikshasync.me — Multi-Tenant ERP + LMS for Schools & Universities

<div align="center">

![Platform](https://img.shields.io/badge/Platform-SaaS%20Multi--Tenant-blue)
![Backend](https://img.shields.io/badge/Backend-FastAPI%200.115%20%7C%20Python%203.11+-green)
![Frontend](https://img.shields.io/badge/Frontend-Next.js%2016%20%7C%20React%2019-black)
![Mobile](https://img.shields.io/badge/Mobile-Expo%20SDK%2057%20%7C%20React%20Native%200.86-purple)
![Database](https://img.shields.io/badge/Database-PostgreSQL%2016%20%7C%20132%20tables-336791)
![License](https://img.shields.io/badge/License-Proprietary-red)

**A production-grade, cloud-native SaaS ERP + Learning Management System for schools, colleges, and universities.**

[Quick Start](#-quick-start) · [Architecture](#-architecture) · [Modules](#-16-product-modules) · [Roles](#-22-roles--rbac) · [Deployment](#-deployment) · [API Docs](#-api-reference) · [Contributing](#-contributing)

</div>

---

## 📖 Overview

**shikshasync.me** is a fully featured, multi-tenant SaaS ERP platform built for educational institutions — schools, colleges, and universities. Inspired by the **AWS / Shopify / Zoho account model**, a single *platform owner* account can create and manage **many institutions**, each provisioned as an isolated tenant on its own subdomain (e.g. `greenwood.shikshasync.me`).

Every tenant receives the complete **16-module product** with its own staff, students, parents, data partition, and subscription state — from **14-day free trial → paid plan**.

### 🏆 What Makes It Unique

| Capability | Detail |
|---|---|
| **True multi-tenant self-serve SaaS** | Owner signs up → provisions school in minutes via a setup wizard |
| **Integrated LMS + Live Classes** | Built-in LMS with assignments, discussions, content & WebRTC live classrooms |
| **Three hard-separated auth planes** | Platform staff · Owner accounts · Institution users — tokens cannot cross |
| **22 roles covering all edu workflows** | From Super Admin to HOD, Exam Controller, Librarian, Hostel Warden |
| **First-class mobile experience** | 75-screen Expo/React Native app for Students, Teachers & Parents |
| **Production-grade engineering** | 414 API endpoints, 132 DB tables, 289 automated tests, async end-to-end |

---

## 📐 Architecture

### System Overview

```
                     ┌────────────────────────────────────────────┐
                     │         Browser / Mobile Users             │
                     │  Next.js 16 (188 pages)  ·  Expo RN app   │
                     └──────────────┬─────────────────────────────┘
                                    │  HTTPS (Bearer JWT)
                         ┌──────────▼──────────┐
                         │   Nginx Reverse      │  Ports 80 / 443
                         │     Proxy            │
                         └────────┬────────────┘
                    ┌─────────────┴───────────────┐
                    ▼                             ▼
          ┌─────────────────┐           ┌──────────────────┐
          │  Next.js Web    │           │  FastAPI Backend  │
          │  (Port 3000)    │           │  (Port 8000)      │
          └─────────────────┘           │  25 routers       │
                                        │  414 endpoints    │
                                        │  WebSocket /live  │
                                        └────┬───────┬──────┘
                         ┌──────────────────┘       └──────────────────┐
                         ▼                                              ▼
               ┌──────────────────┐                        ┌──────────────────┐
               │  PostgreSQL 16   │                        │    Redis 7        │
               │  132 tables      │                        │  Cache · Pub/Sub  │
               │  Row-per-tenant  │                        │  (live classes)   │
               └──────────────────┘                        └──────────────────┘
                         ▼
               ┌──────────────────┐      ┌───────────────────────────┐
               │  APScheduler     │      │  Mailer Registry           │
               │  (in-process)    │      │  Google SMTP · ZeptoMail ·   │
               │  auto-start      │      │  Console (dev)             │
               │  classes/reminders│     └───────────────────────────┘
               └──────────────────┘
```

### Three Client Surfaces — One Backend API

| Surface | Folder | Stack | Purpose |
|---|---|---|---|
| **Web Console + Marketing** | `fontend/` | Next.js 16, React 19, TypeScript 5, Tailwind CSS 3.4 | Marketing pages, pricing/signup, and the full admin console for all 22 roles — 188 pages |
| **Mobile App** | `app/` | Expo SDK 57, React Native 0.86, React 19, expo-router | Student / Teacher / Parent on-the-go app — 75 screens |
| **Backend API** | `backend/` | FastAPI 0.115, Python 3.11+, SQLAlchemy 2, asyncpg, PostgreSQL, Redis | All business logic, auth, multi-tenancy, live classes, email, billing |

---

## 🛠️ Technology Stack

### Backend (`backend/`)

| Layer | Technology | Version |
|---|---|---|
| Web framework | **FastAPI** | 0.115.5 |
| ASGI server | **Uvicorn**[standard] | 0.32.1 |
| ORM | **SQLAlchemy**[asyncio] 2.x | 2.0.36 |
| DB driver | **asyncpg** | 0.30.0 |
| Migrations | **Alembic** | 1.14.0 |
| Validation & settings | **Pydantic 2** + pydantic-settings | 2.10.3 / 2.6.1 |
| Auth tokens | **python-jose** (JWT, HS256) | 3.3.0 |
| Password hashing | **passlib**[bcrypt] (cost factor 12) | 1.7.4 / 4.2.1 |
| Rate limiting | **slowapi** (IP-keyed) | 0.1.9 |
| Cache / Pub-Sub | **redis**[hiredis] | 5.2.1 |
| Email (SMTP) | **aiosmtplib** | 3.0.2 |
| Email (HTTP) | **httpx** (ZeptoMail HTTPS API) | 0.28.1 |
| Background jobs | **APScheduler** (AsyncIOScheduler) | 3.11.0 |
| Forms / multipart | python-multipart | 0.0.12 |
| Object storage | boto3 (S3, optional) | 1.35.90 |
| Tests | pytest, pytest-asyncio, pgserver | 8.3.4 / 0.24.0 / 0.1.4 |

### Web Frontend (`fontend/`)

| Layer | Technology | Version |
|---|---|---|
| Framework | **Next.js** (App Router) | ^16.2.12 |
| UI library | **React** | ^19.2.8 |
| Language | **TypeScript** | ~6.0.3 |
| Styling | **Tailwind CSS** | ^3.4.1 |
| Icons | lucide-react | ^1.27.0 |
| Excel I/O | xlsx | ^0.18.5 |
| Grade card export | html2canvas | ^1.4.1 |
| Push notifications | firebase (FCM JS SDK) | ^10.14.1 |
| E2E / link check | Playwright | ^1.62.1 |
| Unit testing | vitest + @testing-library/react | ^3.2.7 |

### Mobile App (`app/`)

| Layer | Technology |
|---|---|
| SDK | **Expo SDK 57** |
| Framework | **React Native 0.86**, React 19 |
| Routing | **expo-router** (file-based, route groups) |
| Secure storage | expo-secure-store |
| Animations | react-native-reanimated 4 + gesture-handler |
| Graphics | react-native-svg |
| Push notifications | Firebase FCM (Android & iOS) |

### Infrastructure

| Component | Choice |
|---|---|
| Database | **PostgreSQL 16** — UUID PKs, shared schema, row-level tenant isolation |
| Cache / messaging | **Redis 7** — sessions, cache, pub/sub for live classes |
| File storage | Local disk `backend/uploads/` → **AWS S3** (production) |
| Reverse proxy | **Nginx** (wildcard subdomain routing `*.shikshasync.me`) |
| Container | **Docker** + Docker Compose (dev & prod configs) |
| CI/CD | **GitHub Actions** (ci.yml + deploy.yml) |

---

## 🧩 16 Product Modules

### 8 Core Modules (included in every plan — always on)

| Module | Description |
|---|---|
| 📅 **Attendance** | Session-based attendance marking, leave requests, leave policies, auto-attendance from live classes |
| 📝 **Examination** | Question bank (6 types), exam sections, timed attempts, auto-grading, manual grading, result publication, grade cards, hall allocation, malpractice logs |
| 📚 **Assignments** | Milestone-based assignments, file submissions, `CHANGES_REQUESTED` → resubmission review flow |
| 📢 **Notice Board** | Rich notices with attachments, read-receipts per role |
| 💬 **Discussion** | Threaded discussion forums with replies and voting |
| 🎬 **Content (LMS)** | Content items (PDF, VIDEO, SLIDE, IMAGE, AUDIO, LINK), content tags, access logs |
| 📊 **Results** | Student results, grade cards, result publications, exam controller grade-card exports |
| 🗓️ **Timetable** | Weekly timetable slots, substitutions, academic events |

### 8 Paid Add-On Modules (à-la-carte, billed monthly in ₹)

| Module | ₹/month | Description |
|---|---|---|
| 📖 **Library** | ₹1,500 | Books catalogue, copies, issues, e-resources |
| 🏠 **Hostel** | ₹2,000 | Blocks, rooms, allotments, night attendance, leave requests, complaints |
| 🚌 **Transport** | ₹1,500 | Routes, stops, vehicles, drivers, student transport assignments |
| 🎓 **Placement** | ₹1,500 | Drives, company profiles, applications, offers, merit lists, eligibility |
| 👔 **HR** | ₹2,000 | Staff profiles, documents, appraisal cycles, salary structures, payroll runs, payslips |
| 🏫 **Admission** | ₹1,500 | Admission cycles, applications, documents, interview rounds |
| 📦 **Inventory** | ₹1,500 | Categories, items, stock transactions, vendors, purchase orders |
| 💰 **Finance** | ₹2,000 | Fee heads, fee structures, installments, student accounts, payments, scholarships |

### Plans & Pricing

| Plan | Monthly Price | Includes |
|---|---|---|
| **Starter** | — | 8 core modules, up to N users |
| **Professional** | ₹7,999/mo | Core + selected add-ons |
| **Enterprise** | Custom | Full suite + dedicated support |

> 14-day free trial · Coupon codes supported (WELCOME10, LAUNCH500)

---

## 👥 22 Roles & RBAC

### Platform Roles (4) — manage the SaaS platform itself

| Role | Access |
|---|---|
| `SUPER_ADMIN` | Full platform control, all tenants, all settings |
| `SUPPORT_STAFF` | Read across tenants for ticket resolution (audit-logged) |
| `SALES_EXECUTIVE` | Trials, conversions, sales pipeline |
| `FINANCE_MANAGER` | Invoices, payments, billing |

### Owner Account — manage institutions (multi-campus)

| Role | Access |
|---|---|
| `OWNER` | Create/manage institutions, billing, subscriptions, invoices |

### Institution Roles (18) — operate within a single tenant

| Role | Scope |
|---|---|
| `INSTITUTION_ADMIN` | Full institution setup: staff, students, structure, settings |
| `PRINCIPAL` | School-wide visibility, approvals, reports |
| `VICE_PRINCIPAL` | Delegated departments/classes |
| `HOD` | Department-scoped management |
| `ACADEMIC_COORDINATOR` | Academic events, timetable coordination |
| `EXAM_CONTROLLER` | Exam scheduling, monitoring, publication, result management |
| `TEACHER` | Classes, attendance, assignments, exams, content, live sessions |
| `STUDENT` | Enrolled classes, exams, assignments, discussions, library |
| `PARENT / GUARDIAN` | Multi-child view: attendance, fees, results, notices, leave |
| `LIBRARIAN` | Book catalogue, issues, returns |
| `HOSTEL_WARDEN` | Block/room allocation, attendance, complaints |
| + Supporting staff roles | HR, Finance, Coordinator sub-roles |

**Permissions** are materialized as `module_key.ACTION.SCOPE` strings (e.g. `attendance.MARK.DEPARTMENT`) loaded from the DB, embedded in JWT, and **re-validated live per request** — instant revocation, no stale permissions.

---

## 🔐 Security Architecture

### Three Independent Login Systems

All tokens are **HS256 JWTs** signed with one secret but distinguished by a `type` claim. Each auth dependency rejects tokens of other types:

| Token `type` | Identity table | Login URL | Roles served |
|---|---|---|---|
| `platform` | `platform_users` | `/platform/login` | Super Admin, Support, Sales, Finance |
| `owner` | `platform_owners` | `/account/login` | Institution owners |
| `tenant` | `users` (tenant-scoped) | `{slug}.shikshasync.me/login` | 18 institution roles |

### Token Lifecycle

- **Access token:** 15-minute expiry, stored in memory only (never `localStorage`)
- **Refresh token:** 7-day expiry, `httpOnly` cookie (web) / `expo-secure-store` (mobile), stored as **SHA-256 hash** in DB
- **Single-flight refresh guard** (`createRefreshGuard`) prevents thundering-herd on token expiry
- Login is **constant-time** (dummy bcrypt verify when user does not exist) and **rate-limited**

### Security Headers (via Nginx + Next.js)

- **CSP** — restricts script/style/iframe sources
- **HSTS** — `max-age=63072000; includeSubDomains; preload`
- **X-Frame-Options** — `SAMEORIGIN` (clickjacking prevention)
- **X-Content-Type-Options** — `nosniff`
- **Permissions-Policy** — camera/mic allowed only for live classrooms

---

## 🚀 Quick Start

### Option A: Docker (Recommended)

> **Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Docker Engine 20+ & Compose v2)

```bash
# 1. Clone the repository
git clone <repo-url>
cd ERP

# 2. Copy environment variables
cp .env.docker.example .env
# Edit .env to set your secrets (JWT_SECRET_KEY, POSTGRES_PASSWORD, etc.)

# 3. Start all services (PostgreSQL + Redis + Coturn TURN/STUN + MinIO + Backend + Frontend)
docker compose up --build

# 4. Access the application
#    Web console:    http://localhost:3000
#    API Docs:       http://localhost:8000/docs
#    Health check:   http://localhost:8000/health
#    MinIO Console:  http://localhost:9001  (object store)
```

To stop services:
```bash
docker compose down
```

---

### Option B: Local Manual Setup

#### Prerequisites

- **Python 3.11+**
- **Node.js 20+**
- **PostgreSQL 16**
- **Redis 7**

#### Step 1 — Database

```bash
# Create DB and user
psql -U postgres -c "CREATE USER erp_user WITH PASSWORD 'yourpassword';"
psql -U postgres -c "CREATE DATABASE erp_db OWNER erp_user;"

# Load the full schema (132 tables)
psql -U erp_user -d erp_db -f database/database.sql
```

#### Step 2 — Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate
# Activate (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: DATABASE_URL, JWT_SECRET_KEY, REDIS_URL, EMAIL_PROVIDER, etc.

# Seed roles, permissions, modules, plans and superadmin
python scripts/seed_data.py

# Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API available at:  http://localhost:8000
# Swagger Docs:      http://localhost:8000/docs
```

#### Step 3 — Web Frontend

```bash
cd fontend

# Install dependencies
npm ci

# Configure environment
cp .env.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8000

# Start the dev server
npm run dev
# Web available at: http://localhost:3000
```

#### Step 4 — Mobile App (optional)

```bash
cd app

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Set EXPO_PUBLIC_API_URL=http://localhost:8000

# Start Expo dev server
npx expo start
```

---

## 📁 Project Structure

```
ERP/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── main.py             # App factory, CORS, middleware, router mounts
│   │   ├── config.py           # pydantic-settings, env-validated singleton
│   │   ├── database.py         # Async engine, session factory, DeclarativeBase
│   │   ├── dependencies/       # Auth guards: platform / owner / tenant / per-role
│   │   ├── middleware/         # RequestID correlation middleware
│   │   ├── routers/            # HTTP/WebSocket routes (thin) — 25 routers
│   │   │   ├── platform/       #   Platform admin, auth, support tickets
│   │   │   ├── owner/          #   Owner auth, billing, dashboard
│   │   │   ├── tenant/         #   Tenant login, institution setup
│   │   │   └── institution/    #   Principal, VP, HOD, Teacher, Student, Parent…
│   │   ├── services/           # Business logic (fat service layer) — 30+ services
│   │   │   ├── auth_service.py         # Login/refresh/lockout/reset
│   │   │   ├── signup_service.py       # 12-step order → payment → provision pipeline
│   │   │   ├── online_class_service.py # Live rooms, WS lifecycle, auto-attendance
│   │   │   ├── scheduler_service.py    # APScheduler jobs
│   │   │   ├── push_service.py         # In-app inbox + FCM push
│   │   │   ├── audit_service.py        # Audit log writer
│   │   │   └── mailer/                 # Base, registry, providers (SMTP/ZeptoMail)
│   │   ├── models/             # SQLAlchemy ORM — 27 model modules
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── utils/security.py   # bcrypt(12), secure tokens, SHA-256 hashing
│   │   └── alembic/            # 7 DB migration revisions
│   ├── requirements.txt
│   └── Dockerfile
│
├── fontend/                    # Next.js 16 web console + marketing site
│   ├── app/                    # App Router pages (188 pages)
│   │   ├── (auth)/             #   Login, platform login, password reset
│   │   ├── (platform)/         #   Platform & owner admin consoles
│   │   ├── admin/              #   Institution admin console
│   │   ├── principal/          #   Principal dashboard
│   │   ├── teacher/            #   Teacher portal
│   │   ├── student/            #   Student portal
│   │   ├── parent/             #   Parent portal
│   │   └── (marketing)/        #   /, /features, /pricing, /signup…
│   ├── components/             # Per-role + shared UI components
│   ├── lib/                    # ~50 API client modules + auth helpers
│   ├── hooks/                  # React hooks (live room, auth, etc.)
│   ├── types/                  # TypeScript type definitions
│   └── Dockerfile
│
├── app/                        # Expo / React Native mobile app (75 screens)
│   └── src/
│       ├── (student)/          # Student route group
│       ├── (teacher)/          # Teacher route group
│       └── (parent)/           # Parent route group
│
├── database/
│   └── database.sql            # Canonical schema — 132 tables
│
├── nginx/                      # Nginx reverse proxy config
├── scripts/                    # Deployment, backup, restore, seed scripts
├── docker-compose.yml          # Local development stack
├── docker-compose.prod.yml     # Production stack
├── .env.docker.example         # Environment variable template
├── DEPLOYMENT.md               # Full DevOps & CI/CD guide
├── TECHNICAL-DETAILS-AND-SYSTEM-DESIGN.md
├── NOTIFICATION-SYSTEM.md
├── MARKET-AND-BUSINESS-ANALYSIS.md
└── PRE-LAUNCH-ISSUES-AND-FIXES.md
```

---

## 🗄️ Data Model

The database contains **132 tables** organized into domains:

| Domain | Key Tables |
|---|---|
| **Platform / Tenancy** | `platform_owners`, `platform_users`, `tenants`, `users`, `roles`, `permissions`, `role_assignments`, `audit_logs` |
| **Billing / Catalog** | `modules`, `plans`, `orders`, `subscriptions`, `coupons`, `platform_invoices`, `platform_payments` |
| **Academic Structure** | `academic_years`, `departments`, `classes`, `subjects`, `teacher_subjects`, `student_enrollments`, `timetable_slots` |
| **LMS** | `assignments`, `submissions`, `content_items`, `discussion_threads`, `notices`, `notifications` |
| **Examinations** | `exams`, `questions`, `question_bank_items`, `exam_attempts`, `answers`, `student_results`, `grade_cards` |
| **Attendance / Leave** | `attendance_sessions`, `attendance_records`, `leave_requests`, `leave_policies` |
| **Fees / Finance** | `fee_heads`, `fee_structures`, `student_fee_accounts`, `fee_payments`, `scholarships`, `payroll_runs` |
| **Library** | `books`, `book_copies`, `book_issues`, `e_resources` |
| **Hostel** | `hostel_blocks`, `hostel_rooms`, `hostel_allotments`, `hostel_attendance`, `hostel_complaints` |
| **Transport** | `transport_routes`, `vehicles`, `drivers`, `student_transport` |
| **Live Classes** | `online_classes`, `online_class_participants`, `online_class_messages`, `online_class_files` |
| **Placement / HR / Admission** | `placement_drives`, `staff_profiles`, `appraisals`, `admission_applications` |
| **Inventory** | `inventory_items`, `stock_transactions`, `vendors`, `purchase_orders` |

**Multi-tenancy:** Shared database, shared schema, **row-level tenant discrimination** — every business table carries `tenant_id`. The same email address can exist across multiple institutions.

---

## 🎥 Live Classes (WebSocket + WebRTC)

The live classroom subsystem is one of the most technically sophisticated parts of the platform:

- **WebSocket endpoint:** `GET /api/v1/.../online-classes/{class_id}/live?token=...`
  - Token passed as query param (browsers cannot set WebSocket headers)
  - Handshake verifies JWT type, tenant, enrolment, and class state before `accept()`
- **In-memory `LiveRoomManager`:** tracks rooms → users → sockets per worker
  - Features: waiting room, mute controls, chat, whiteboard (capped 500 strokes), hand-raise, file sharing, presence
  - Room cap: 500 participants per worker · Frame size cap: 128 KB
- **Audio/Video (Web):** peer-to-peer **WebRTC mesh** — one `RTCPeerConnection` per peer, SDP/ICE signalling over WebSocket, screen share via `getDisplayMedia`, browser-side recording via `MediaRecorder`
- **Mobile app:** carries chat, whiteboard, presence, materials — no WebRTC A/V in this build
- **Auto-attendance policy:**
  - ≥ 75% of live duration → `PRESENT`
  - 30–74% → `LATE`
  - < 30% → `ABSENT`
  - On class end, attendance syncs to canonical `attendance_sessions` / `attendance_records` tables

---

## 🔔 Notification & Push System

A durable, multi-channel notification system:

```
Services  →  notifications (in-app DB rows)
                  └→  notification_deliveries (outbox)
                              └→  deliver_pending() worker (every 10s)
                                        ├→  FCM v1 HTTP (Android / iOS)
                                        └→  Firebase JS SDK (Web push)
```

- **In-app inbox:** unified bell icon + inbox page for every role
- **FCM push:** Android, iOS, and web browser push via Firebase Cloud Messaging v1
- **Durable delivery:** rows are written first; failed FCM calls are retried — no lost notifications
- **Device token registry:** `device_tokens` table (per platform + user)

---

## 📧 Email System

**Outbox pattern** — transactional emails are written to `outbox_emails` inside the same DB transaction as the business change, then drained by the APScheduler:

| Provider | When to use |
|---|---|
| `google` | Gmail / Google Workspace SMTP (app password) |
| `zeptomail` | Zoho ZeptoMail HTTPS API — production (India DC available) |
| `console` | Dev / test — logs to stdout only, no real email sent |

Set `EMAIL_PROVIDER` in `.env` to switch providers. Tests always force `console`.

---

## 🚢 Deployment

See **[`DEPLOYMENT.md`](./DEPLOYMENT.md)** for the full guide. Summary below:

### Production Docker Compose

```bash
# 1. Configure secrets
cp .env.docker.example .env
# Edit: JWT_SECRET_KEY, POSTGRES_PASSWORD, PUBLIC_ROOT_DOMAIN, EMAIL_PROVIDER, etc.

# 2. Build & start the production stack
docker compose -f docker-compose.prod.yml up -d --build

# 3. Run Alembic migrations
docker compose -f docker-compose.prod.yml run --rm migration

# 4. Seed superadmin (fresh install only)
docker compose -f docker-compose.prod.yml exec backend python scripts/create_superadmin.py
```

### One-Command Deployment Script

```bash
# Linux / Ubuntu / Debian VPS
chmod +x scripts/*.sh
./scripts/deploy.sh

# Windows PowerShell
.\scripts\deploy.ps1
```

### SSL / HTTPS (Wildcard Certificate)

```bash
# Issue wildcard certificate for *.shikshasync.me
sudo certbot certonly --manual --preferred-challenges=dns \
  -d "shikshasync.me" -d "*.shikshasync.me"
```

### CI/CD — GitHub Actions

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | Every push / PR | Backend pytest (PostgreSQL + Redis services), Frontend ESLint + vitest + `next build`, Docker build check |
| `deploy.yml` | Push to `main` | Build images → push to `ghcr.io` → SSH deploy to production server |

### Database Backup & Restore

```bash
# Manual backup
chmod +x scripts/backup-db.sh
./scripts/backup-db.sh

# Restore from backup
./scripts/restore-db.sh backups/erp_backup_YYYYMMDD_HHMMSS.sql.gz

# Scheduled daily backup at 02:00 AM (add to crontab)
0 2 * * * /opt/erp/scripts/backup-db.sh >> /var/log/erp_backup.log 2>&1
```

---

## 🧪 Testing

### Backend Tests

```bash
cd backend
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# Run all 289 pytest functions (27 test files)
pytest

# Run with verbose output
pytest -v

# Run a specific test module
pytest tests/test_auth.py -v
```

- Uses **pgserver** (embedded PostgreSQL) for real integration suites — no DB mocking
- Mailer is forced to `console` — tests never send real email
- Rate limiters are reset per test

### Frontend Tests

```bash
cd fontend

# Unit tests (vitest + @testing-library/react)
npm test

# Lint
npm run lint

# Check for broken internal links
npm run link-check
```

### Mobile Tests

```bash
cd app
npm test
```

---

## 🔑 Key Environment Variables

### Backend (`.env`)

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async URL: `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | Default: `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | Strong random secret for signing JWTs |
| `APP_ENV` | `development` / `production` |
| `APP_DEBUG` | `true` exposes `/docs`, `/redoc`, full stack traces |
| `PUBLIC_ROOT_DOMAIN` | Default: `shikshasync.me` (for subdomain tenant routing) |
| `TRIAL_DAYS` | Default: `14` |
| `EMAIL_PROVIDER` | `console` / `google` / `zeptomail` |
| `EMAIL_FROM` | Envelope sender address |
| `GOOGLE_SMTP_USER` | Gmail address (if `EMAIL_PROVIDER=google`) |
| `GOOGLE_SMTP_PASSWORD` | Gmail App Password (NOT account password) |
| `ZEPTO_MAIL_SEND_TOKEN` | ZeptoMail API token (if `EMAIL_PROVIDER=zeptomail`) |
| `ZEPTO_MAIL_API_URL` | Default: `https://api.zeptomail.com/v1.1/email` (use `.in` for India DC) |
| `STORAGE_BACKEND` | `auto` / `local` / `r2` (Cloudflare R2) / `s3` (AWS S3/MinIO) |
| `R2_BUCKET` | Cloudflare R2 bucket name |
| `R2_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | R2 access key ID |
| `R2_SECRET_ACCESS_KEY` | R2 secret access key |
| `S3_BUCKET` | AWS S3 / MinIO bucket name |
| `S3_REGION` | e.g. `ap-south-1` |
| `S3_ENDPOINT_URL` | MinIO or custom S3-compatible endpoint URL |
| `S3_FORCE_PATH_STYLE` | `true` for MinIO; `false` for AWS S3 / R2 |
| `FCM_SERVICE_ACCOUNT_JSON` | Path to Firebase service account JSON file |
| `FCM_SERVICE_ACCOUNT_B64` | Base64-encoded Firebase service account JSON (for env-based secrets) |
| `FCM_PROJECT_ID` | Firebase project ID (usually auto-read from JSON) |
| `TURN_URL` | e.g. `turn:turn.example.com:3478` or `turns:...:5349` (TLS) |
| `TURN_USERNAME` | TURN server username |
| `TURN_CREDENTIAL` | TURN server password |
| `SFU_ENABLED` | `false` — SFU (LiveKit/mediasoup/Janus) config slot |
| `SCHEDULER_ENABLED` | `true` — set `false` on API-only workers |
| `ALLOWED_ORIGINS` | Comma-separated CORS-allowed origins |

### Frontend (`.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend API base URL (e.g. `http://localhost:8000`) |
| `NEXT_PUBLIC_FIREBASE_*` | Firebase config for web push notifications |

---

## 📊 Codebase at a Glance

| Metric | Count |
|---|---|
| Backend Python (app code) | ~48,900 LOC |
| Web frontend (TS/TSX) | ~80,600 LOC, **188 pages** |
| Mobile app (TS/TSX) | ~28,600 LOC, **75 screens** |
| REST / WebSocket endpoints | **414** |
| Database tables | **132** |
| Pytest test functions | **289** across 27 test files |
| Roles | **22** (4 platform + 18 institution) |
| Product modules | **16** (8 core + 8 paid add-ons) |

---

## 📚 Documentation

| Document | Description |
|---|---|
| [`DEPLOYMENT.md`](./DEPLOYMENT.md) | Full DevOps guide: Docker, CI/CD, SSL, backups, security hardening |
| [`TECHNICAL-DETAILS-AND-SYSTEM-DESIGN.md`](./TECHNICAL-DETAILS-AND-SYSTEM-DESIGN.md) | End-to-end engineering reference for developers and architects |
| [`NOTIFICATION-SYSTEM.md`](./NOTIFICATION-SYSTEM.md) | In-app, FCM push, and web push notification system design |
| [`MARKET-AND-BUSINESS-ANALYSIS.md`](./MARKET-AND-BUSINESS-ANALYSIS.md) | Market size, competition, pricing strategy, go-to-market analysis |
| [`PRE-LAUNCH-ISSUES-AND-FIXES.md`](./PRE-LAUNCH-ISSUES-AND-FIXES.md) | Known issues, blockers, and proposed fixes before go-live |
| [`backend/EMAIL-SETUP.md`](./backend/EMAIL-SETUP.md) | Google SMTP and ZeptoMail (Zoho) email provider setup guide |
| `doc/` | Architecture diagrams, system flow, the owner-account model |

---

## 🤝 Contributing

1. **Fork** the repository and create a feature branch:
   ```bash
   git checkout -b feat/my-feature
   ```

2. **Follow the architecture patterns:**
   - **Thin routers, fat services** — routers validate input, services own business logic
   - **Fail-closed authorization** — every privileged route must have a role guard
   - **Outbox email pattern** — write to `outbox_emails` table, never send email inline
   - **Audit by default** — call `AuditService.record()` for privileged actions

3. **Write tests** for new functionality (backend: pytest, frontend: vitest)

4. **Run the test suite** before submitting:
   ```bash
   # Backend
   cd backend && pytest

   # Frontend
   cd fontend && npm test && npm run lint
   ```

5. **Open a Pull Request** — CI will run automatically

---

## 📜 License

Proprietary — All rights reserved. See [`app/LICENSE`](./app/LICENSE) for the mobile app license terms.

---

<div align="center">
  <b>Built with love for educational institutions across India and beyond.</b><br/>
  <sub>Market: USD 84B+ School ERP · India beachhead: ~420K private institutions · Target SOM: 150-350 institutions in 3 years</sub>
</div>
