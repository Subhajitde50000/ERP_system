# SOFTWARE SPECIFICATION & TECHNICAL ARCHITECTURE DOSSIER
### [Explanatory Technical Manual for Copyright Scrutiny]
## WORK TITLE: Shikshasync — Multi-Tenant Educational ERP & Learning Management System
**Author & Applicant:** Subhajit De  
**Classification:** Literary Work — Computer Software [Section 2(o), Copyright Act, 1957]  
**Status:** Unpublished (2026)  

---

### 1. Executive Summary & Purpose of the Software

**Shikshasync** is an original, production-grade, multi-tenant cloud-native Software-as-a-Service (SaaS) Enterprise Resource Planning (ERP) platform and integrated Learning Management System (LMS) engineered specifically for schools, colleges, coaching institutes, and universities.

The software architecture implements an **AWS/Shopify-style multi-tenant account model**, wherein a single master platform owner account can provision and administer multiple distinct educational institutions. Each institution functions as a logically partitioned tenant on its own unique subdomain (e.g., `tenant.shikshasync.me`) with its own independent staff, students, parents, academic rules, database partition, and subscription lifecycle.

---

### 2. Comprehensive Technology Stack & Runtime Environment

| Tier / Component | Technology & Framework | Key Libraries & Specifications |
|---|---|---|
| **Backend Core** | Python 3.11+ / FastAPI 0.115 | Asynchronous RESTful API framework (ASGI via Uvicorn), Pydantic v2 data validation |
| **Database & ORM** | PostgreSQL 16 / SQLAlchemy 2.0 | Asyncpg non-blocking asynchronous driver, Alembic schema migrations |
| **In-Memory Cache & Pub/Sub** | Redis 7.x | Token revocation, real-time live class signaling, rate limit state |
| **Web Presentation Tier** | Next.js 16 / React 19 / TypeScript 5 | Server-side rendering (SSR) & client-side routing, Tailwind CSS 3.4, 188 page routes |
| **Mobile Client Tier** | React Native 0.86 / Expo SDK 57 | Cross-platform Android & iOS client, Expo Router, 75 native interface screens |
| **Real-time Live Classroom** | WebRTC & WebSocket | Low-latency audio/video streaming, peer-to-peer room state management |
| **Scheduling Engine** | APScheduler (In-process Async) | Automated session reminders, recurring billing, attendance processing |
| **Security & Auth** | python-jose (HS256 JWT) / Passlib | Bcrypt password hashing, hard-separated authentication scopes |

---

### 3. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Client Devices & Surfaces                         │
│   • Web Console (Next.js 16 — 188 Pages)    • Mobile App (Expo RN — 75 Screens) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTPS / WSS (Bearer JWT Tokens)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Reverse Proxy & SSL Termination (Nginx)                 │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Internal Reverse Proxy Routing
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Application Core (Port 8000)                   │
│   • Request ID Correlation Middleware      • SlowAPI Distributed Rate Limiter│
│   • 25 Modular Routing Controllers         • 414 RESTful & WebSocket Endpoints│
└──────────────┬───────────────────────┬──────────────────────────┬───────────┘
               │ Async ORM (SQLAlchemy)│ Pub/Sub & Caching        │ Background
               ▼                       ▼                          ▼
┌───────────────────────────┐ ┌─────────────────┐   ┌─────────────────────────┐
│  PostgreSQL 16 Database   │ │  Redis 7 Cache  │   │  APScheduler Engine     │
│  132 Relational Tables    │ │  Live Class Sync│   │  Automated Job Worker   │
│  Row-Level Tenant Filter  │ │  Token Registry │   │  Notification Dispatch  │
└───────────────────────────┘ └─────────────────┘   └─────────────────────────┘
```

---

### 4. Tri-Plane Hard-Separated Authentication Architecture

To ensure zero cross-tenant credential contamination, the software implements three completely isolated authentication and session planes:

1. **Platform Plane (`PlatformUser`):** Used exclusively by super administrators, platform finance, and support staff to manage tenants, view server telemetry, and monitor platform health.
2. **Owner Plane (`PlatformOwner`):** Used by educational group owners/trustees to manage institutional subscriptions, billing tiers, domain routing, and multi-school licenses.
3. **Institution Plane (`User`):** Scoped strictly to an individual tenant. Endpoints strictly enforce the `tenant_id` claim parsed from the cryptographic JWT, ensuring complete isolation of student, teacher, and administrative records.

---

### 5. The 16 Proprietary Product Modules

1. **Multi-Tenant Setup & Provisioning:** Automated institution creation wizard, domain validation, and default curriculum seeders.
2. **Role-Based Access Control (RBAC):** Fine-grained permissions across 22 distinct institutional personas.
3. **Student Information System (SIS):** Lifecycle admissions, student profiling, parent linkage, and roll numbering.
4. **Academics & Curriculum Engine:** Academic years, semesters, subjects, syllabus planning, and timetable scheduling.
5. **Attendance Management:** Biometric and teacher-marked daily/period-wise attendance tracking with leave applications.
6. **Examination & Grading System:** Exam scheduling, mark entry, grade book generation, report cards, and GPA algorithms.
7. **Fee Management & Invoicing:** Flexible fee head structuring, installment generation, online payment reconciliation, and receipt generation.
8. **Integrated Learning Management System (LMS):** Course creation, chapter delivery, digital lecture notes, and file attachments.
9. **Interactive Assignment & Homework Engine:** Teacher task creation, file uploads, student submissions, and rubric evaluation.
10. **Live WebRTC Classroom:** Real-time multi-party video conferencing, screen sharing, chat, and room session recording.
11. **Library Automation System:** Book cataloging, ISBN indexing, barcode generation, issue/return tracking, and fine calculation.
12. **Hostel & Dormitory Management:** Building, room, and bed allocation, hostel warden logging, and mess billing.
13. **Transport & Fleet Logistics:** Vehicle routes, bus stop mapping, student boarding lists, and driver management.
14. **Human Resource & Staff Payroll:** Teacher and staff profiles, salary structures, payroll slip generation, and leaves.
15. **Cross-Channel Notification Engine:** Firebase Cloud Messaging (FCM) push notifications, automated email templating, and SMS triggers.
16. **Audit & Compliance Logging:** Immutable request-ID-correlated audit trails recording IP addresses, actions, and timestamps.

---

### 6. The 22 Role-Based Access Personas

The program structures business logic across 22 distinct hierarchical roles:
1. `SUPER_ADMIN` (Platform root)
2. `PLATFORM_SUPPORT` (Customer support)
3. `PLATFORM_FINANCE` (Platform billing)
4. `INSTITUTION_OWNER` (School/College founder)
5. `PRINCIPAL` (Institutional head)
6. `VICE_PRINCIPAL` (Academic head)
7. `DEAN` (University faculty head)
8. `HOD` (Head of Department)
9. `ACADEMIC_COORDINATOR` (Curriculum coordinator)
10. `EXAM_CONTROLLER` (Examination officer)
11. `TEACHER` (Faculty member)
12. `TEACHING_ASSISTANT` (TA / Lab instructor)
13. `STUDENT` (Learner)
14. `PARENT` (Guardian)
15. `LIBRARIAN` (Library manager)
16. `ACCOUNTANT` (Finance officer)
17. `HOSTEL_WARDEN` (Dormitory supervisor)
18. `TRANSPORT_MANAGER` (Logistics supervisor)
19. `RECEPTIONIST` (Front desk officer)
20. `ADMISSIONS_OFFICER` (Enrollment manager)
21. `COUNSELOR` (Student welfare)
22. `ALUMNI` (Graduated student)

---

### 7. Database Model & Schema Scale

* **Total Database Tables:** 132 structured relational tables.
* **Integrity Features:** Foreign key cascades, foreign-key multi-column indexing, PostgreSQL `UUID` primary keys, enum-validated states, timestamped audit triggers, and soft-delete capabilities (`is_deleted` flags).
* **Isolation Guarantee:** Every tenant-scoped entity carries a foreign key reference to `tenant_id` indexed with compound uniqueness constraints.

---

### 8. Intellectual Property & Originality Statement

The software has been entirely authored by **Subhajit De**. The organization of modules, the relational data structures, the multi-tier authentication isolation algorithms, and the integration mechanics represent original literary expressions under Section 2(o) and Section 13(1)(a) of the Copyright Act, 1957.
