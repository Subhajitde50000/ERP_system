# ERP + LMS Platform — Complete Database Design

> Platform: shikshasync.me Multi-Tenant ERP + LMS  
> Database: PostgreSQL 15  
> ORM: Prisma  
> Version: 1.0  
> Scope: All 15 modules · All 22 roles · Platform + Institution layers

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Naming Conventions](#2-naming-conventions)
3. [Schema Overview — All Tables](#3-schema-overview--all-tables)
4. [Layer 1 — Platform Tables](#4-layer-1--platform-tables)
5. [Layer 2 — RBAC Tables](#5-layer-2--rbac-tables)
6. [Layer 3 — Institution Structure Tables](#6-layer-3--institution-structure-tables)
7. [Layer 4 — Core Module Tables](#7-layer-4--core-module-tables)
   - 7.1 Attendance
   - 7.2 Examination
   - 7.3 Assignment & Milestone
   - 7.4 Notice Board
   - 7.5 Discussion Forum
   - 7.6 Content Upload
   - 7.7 Results & Grade Cards
   - 7.8 Timetable
8. [Layer 5 — Optional Module Tables](#8-layer-5--optional-module-tables)
   - 8.1 Library
   - 8.2 Hostel
   - 8.3 Transport
   - 8.4 Placement
   - 8.5 HR
   - 8.6 Admission
   - 8.7 Inventory
9. [Layer 6 — Platform ERP Tables](#9-layer-6--platform-erp-tables)
10. [Layer 7 — Notification & Audit Tables](#10-layer-7--notification--audit-tables)
11. [Full Index Strategy](#11-full-index-strategy)
12. [Foreign Key Map](#12-foreign-key-map)
13. [Enum Reference](#13-enum-reference)
14. [Complete Prisma Schema](#14-complete-prisma-schema)

---

## 1. Design Principles

| Principle | Implementation |
|---|---|
| Multi-tenancy | Every institution-scoped table has `tenant_id UUID NOT NULL`. All queries filter by it. |
| Data isolation | No cross-tenant joins ever. Tenant ID injected at middleware, not trusted from client. |
| Soft delete | No hard deletes on academic records. Use `deleted_at TIMESTAMPTZ` or `is_active BOOLEAN`. |
| UUID primary keys | All tables use `UUID` PKs generated server-side. No auto-increment integers exposed to clients. |
| Audit trail | Every write-capable table logs to `audit_logs`. Sensitive tables have `created_by` + `updated_by`. |
| Referential integrity | All foreign keys enforced at DB level. Cascade rules defined explicitly. |
| Indexes | Every FK column, every frequently filtered column, and every unique constraint is indexed. |
| Enum types | PostgreSQL native enums for all status / type columns. No magic strings in DB. |
| JSON columns | Used only for flexible config (module settings, notification data). Never for queryable data. |
| Academic year scoping | All academic records link to `academic_year_id` for year-wise isolation and archival. |

---

## 2. Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Tables | `snake_case`, plural | `attendance_records` |
| Columns | `snake_case` | `created_at`, `tenant_id` |
| Primary key | `id` (UUID) | `id UUID PRIMARY KEY` |
| Foreign keys | `{table_singular}_id` | `tenant_id`, `class_id` |
| Boolean flags | `is_{state}` | `is_active`, `is_core` |
| Timestamps | `{action}_at` | `created_at`, `deleted_at` |
| Enums | `UPPER_SNAKE_CASE` values | `PRESENT`, `ABSENT` |
| Indexes | `idx_{table}_{column(s)}` | `idx_users_tenant_email` |
| Unique constraints | `uq_{table}_{column(s)}` | `uq_tenants_slug` |

---

## 3. Schema Overview — All Tables

| # | Table Name | Layer | Module | Rows (est. per 1k students/yr) |
|---|---|---|---|---|
| 1 | `plans` | Platform | — | ~10 |
| 2 | `tenants` | Platform | — | ~500 |
| 3 | `tenant_settings` | Platform | — | ~500 |
| 4 | `subscriptions` | Platform | — | ~500 |
| 5 | `platform_users` | Platform | — | ~50 |
| 6 | `support_tickets` | Platform | — | ~5k |
| 7 | `modules` | RBAC | — | 15 |
| 8 | `tenant_modules` | RBAC | — | ~30/tenant |
| 9 | `roles` | RBAC | — | 22 |
| 10 | `permissions` | RBAC | — | ~200 |
| 11 | `users` | RBAC | — | ~1.5k |
| 12 | `role_assignments` | RBAC | — | ~2k |
| 13 | `user_sessions` | RBAC | — | ~5k |
| 14 | `departments` | Structure | — | ~20 |
| 15 | `academic_years` | Structure | — | ~5 |
| 16 | `classes` | Structure | — | ~30 |
| 17 | `subjects` | Structure | — | ~100 |
| 18 | `teacher_subjects` | Structure | — | ~150 |
| 19 | `student_enrollments` | Structure | — | ~1k |
| 20 | `parent_student_links` | Structure | — | ~1k |
| 21 | `attendance_sessions` | Core | Attendance | ~50k |
| 22 | `attendance_records` | Core | Attendance | ~500k |
| 23 | `attendance_leaves` | Core | Attendance | ~2k |
| 24 | `exams` | Core | Examination | ~200 |
| 25 | `exam_sections` | Core | Examination | ~400 |
| 26 | `questions` | Core | Examination | ~5k |
| 27 | `question_options` | Core | Examination | ~20k |
| 28 | `exam_hall_allocations` | Core | Examination | ~500 |
| 29 | `exam_attempts` | Core | Examination | ~200k |
| 30 | `answers` | Core | Examination | ~1M |
| 31 | `malpractice_logs` | Core | Examination | ~100 |
| 32 | `assignments` | Core | Assignment | ~500 |
| 33 | `milestones` | Core | Assignment | ~1.5k |
| 34 | `submissions` | Core | Assignment | ~10k |
| 35 | `submission_files` | Core | Assignment | ~30k |
| 36 | `submission_reviews` | Core | Assignment | ~10k |
| 37 | `notices` | Core | Notice | ~2k |
| 38 | `notice_attachments` | Core | Notice | ~3k |
| 39 | `notice_reads` | Core | Notice | ~50k |
| 40 | `discussion_threads` | Core | Discussion | ~1k |
| 41 | `discussion_replies` | Core | Discussion | ~10k |
| 42 | `discussion_votes` | Core | Discussion | ~20k |
| 43 | `content_items` | Core | Content | ~2k |
| 44 | `content_tags` | Core | Content | ~5k |
| 45 | `content_access_logs` | Core | Content | ~50k |
| 46 | `result_publications` | Core | Results | ~50 |
| 47 | `student_results` | Core | Results | ~50k |
| 48 | `grade_cards` | Core | Results | ~5k |
| 49 | `timetable_slots` | Core | Timetable | ~500 |
| 50 | `timetable_substitutions` | Core | Timetable | ~200 |
| 51 | `books` | Optional | Library | ~5k |
| 52 | `book_copies` | Optional | Library | ~10k |
| 53 | `book_issues` | Optional | Library | ~20k |
| 54 | `e_resources` | Optional | Library | ~500 |
| 55 | `hostel_blocks` | Optional | Hostel | ~10 |
| 56 | `hostel_rooms` | Optional | Hostel | ~200 |
| 57 | `hostel_allotments` | Optional | Hostel | ~500 |
| 58 | `hostel_attendance` | Optional | Hostel | ~100k |
| 59 | `hostel_complaints` | Optional | Hostel | ~200 |
| 60 | `hostel_leave_requests` | Optional | Hostel | ~1k |
| 61 | `transport_routes` | Optional | Transport | ~20 |
| 62 | `transport_stops` | Optional | Transport | ~100 |
| 63 | `vehicles` | Optional | Transport | ~20 |
| 64 | `drivers` | Optional | Transport | ~20 |
| 65 | `student_transport` | Optional | Transport | ~500 |
| 66 | `companies` | Optional | Placement | ~200 |
| 67 | `placement_drives` | Optional | Placement | ~50 |
| 68 | `drive_eligibility` | Optional | Placement | ~200 |
| 69 | `placement_applications` | Optional | Placement | ~2k |
| 70 | `interview_rounds` | Optional | Placement | ~500 |
| 71 | `placement_offers` | Optional | Placement | ~200 |
| 72 | `staff_profiles` | Optional | HR | ~100 |
| 73 | `leave_policies` | Optional | HR | ~10 |
| 74 | `leave_requests` | Optional | HR | ~1k |
| 75 | `salary_structures` | Optional | HR | ~50 |
| 76 | `payroll_runs` | Optional | HR | ~1k |
| 77 | `payslips` | Optional | HR | ~10k |
| 78 | `appraisal_cycles` | Optional | HR | ~10 |
| 79 | `appraisals` | Optional | HR | ~500 |
| 80 | `staff_documents` | Optional | HR | ~500 |
| 81 | `admission_cycles` | Optional | Admission | ~5 |
| 82 | `admission_applications` | Optional | Admission | ~2k |
| 83 | `application_documents` | Optional | Admission | ~5k |
| 84 | `merit_lists` | Optional | Admission | ~20 |
| 85 | `fee_structures` | ERP | Finance | ~20 |
| 86 | `fee_heads` | ERP | Finance | ~50 |
| 87 | `student_fee_accounts` | ERP | Finance | ~1k |
| 88 | `fee_installments` | ERP | Finance | ~3k |
| 89 | `fee_payments` | ERP | Finance | ~10k |
| 90 | `scholarships` | ERP | Finance | ~100 |
| 91 | `scholarship_grants` | ERP | Finance | ~200 |
| 92 | `inventory_categories` | Optional | Inventory | ~20 |
| 93 | `inventory_items` | Optional | Inventory | ~200 |
| 94 | `stock_transactions` | Optional | Inventory | ~2k |
| 95 | `vendors` | Optional | Inventory | ~50 |
| 96 | `purchase_orders` | Optional | Inventory | ~100 |
| 97 | `purchase_order_items` | Optional | Inventory | ~500 |
| 98 | `notifications` | System | — | ~200k |
| 99 | `device_tokens` | System | — | ~2k |
| 100 | `audit_logs` | System | — | ~1M |

---

## 4. Layer 1 — Platform Tables

### 4.1 `plans`

Subscription plans available for institutions.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | |
| `name` | VARCHAR(100) | NOT NULL | Basic / Standard / Premium |
| `slug` | VARCHAR(50) | NOT NULL, UNIQUE | basic / standard / premium |
| `max_students` | INTEGER | NOT NULL | -1 = unlimited |
| `max_teachers` | INTEGER | NOT NULL | -1 = unlimited |
| `max_storage_gb` | INTEGER | NOT NULL DEFAULT 10 | |
| `price_monthly` | NUMERIC(10,2) | NOT NULL | |
| `price_yearly` | NUMERIC(10,2) | NOT NULL | |
| `currency` | VARCHAR(3) | NOT NULL DEFAULT 'INR' | |
| `allowed_modules` | TEXT[] | NOT NULL DEFAULT '{}' | module keys allowed |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 4.2 `tenants`

One row per institution (school or college).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | VARCHAR(255) | NOT NULL | "ABC College of Engineering" |
| `slug` | VARCHAR(100) | NOT NULL, UNIQUE | subdomain: `abc-college` |
| `type` | tenant_type ENUM | NOT NULL | SCHOOL / COLLEGE |
| `plan_id` | UUID | FK → plans.id | |
| `logo_url` | TEXT | | |
| `address` | TEXT | | |
| `city` | VARCHAR(100) | | |
| `state` | VARCHAR(100) | | |
| `country` | VARCHAR(100) | NOT NULL DEFAULT 'India' | |
| `pincode` | VARCHAR(20) | | |
| `phone` | VARCHAR(20) | | |
| `email` | VARCHAR(255) | | |
| `website` | VARCHAR(255) | | |
| `timezone` | VARCHAR(50) | NOT NULL DEFAULT 'Asia/Kolkata' | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `trial_ends_at` | TIMESTAMPTZ | | NULL = not on trial |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Indexes:** `uq_tenants_slug`, `idx_tenants_plan_id`, `idx_tenants_is_active`

---

### 4.3 `tenant_settings`

Key-value settings per institution (branding, thresholds, policies).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `key` | VARCHAR(100) | NOT NULL | attendance_threshold / academic_year_start_month |
| `value` | TEXT | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, key)`

---

### 4.4 `subscriptions`

Billing history per tenant.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `plan_id` | UUID | NOT NULL, FK → plans.id | |
| `status` | subscription_status ENUM | NOT NULL | TRIAL / ACTIVE / PAST_DUE / CANCELLED |
| `starts_at` | TIMESTAMPTZ | NOT NULL | |
| `ends_at` | TIMESTAMPTZ | | |
| `amount` | NUMERIC(10,2) | NOT NULL | |
| `currency` | VARCHAR(3) | NOT NULL DEFAULT 'INR' | |
| `payment_reference` | VARCHAR(255) | | gateway transaction ID |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 4.5 `platform_users`

Super Admin, Support, Sales, Finance — not tied to any tenant.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | VARCHAR(255) | NOT NULL | |
| `email` | VARCHAR(255) | NOT NULL, UNIQUE | |
| `password_hash` | TEXT | NOT NULL | bcrypt |
| `platform_role` | platform_role ENUM | NOT NULL | SUPER_ADMIN / SUPPORT / SALES / FINANCE |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `last_login_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 4.6 `support_tickets`

Tickets raised by institution admins.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `raised_by` | UUID | NOT NULL, FK → users.id | |
| `assigned_to` | UUID | FK → platform_users.id | support staff |
| `subject` | VARCHAR(255) | NOT NULL | |
| `description` | TEXT | NOT NULL | |
| `priority` | ticket_priority ENUM | NOT NULL DEFAULT 'MEDIUM' | LOW / MEDIUM / HIGH / CRITICAL |
| `status` | ticket_status ENUM | NOT NULL DEFAULT 'OPEN' | OPEN / IN_PROGRESS / RESOLVED / CLOSED |
| `resolved_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

## 5. Layer 2 — RBAC Tables

### 5.1 `modules`

Master list of all 15 modules in the platform.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `key` | VARCHAR(50) | NOT NULL, UNIQUE | attendance / hostel / placement |
| `name` | VARCHAR(100) | NOT NULL | Display name |
| `description` | TEXT | | |
| `is_core` | BOOLEAN | NOT NULL DEFAULT FALSE | Core = always on |
| `icon` | VARCHAR(50) | | UI icon name |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | UI display order |

---

### 5.2 `tenant_modules`

Which optional modules each institution has enabled.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id ON DELETE CASCADE | |
| `module_key` | VARCHAR(50) | NOT NULL, FK → modules.key | |
| `is_enabled` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `enabled_at` | TIMESTAMPTZ | | |
| `enabled_by` | UUID | FK → users.id | institution admin who toggled |
| `disabled_at` | TIMESTAMPTZ | | |
| `disabled_by` | UUID | FK → users.id | |

**Unique:** `(tenant_id, module_key)`  
**Indexes:** `idx_tenant_modules_tenant_id`, `idx_tenant_modules_enabled`

---

### 5.3 `roles`

All 22 roles in the system (platform + institution).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | VARCHAR(100) | NOT NULL, UNIQUE | TEACHER / STUDENT / HOD |
| `label` | VARCHAR(100) | NOT NULL | Human-readable: "Head of Department" |
| `scope_level` | scope_level ENUM | NOT NULL | PLATFORM / INSTITUTION / DEPARTMENT / CLASS / SUBJECT / SELF / CHILD |
| `is_platform` | BOOLEAN | NOT NULL DEFAULT FALSE | TRUE = Super Admin etc. |
| `is_optional` | BOOLEAN | NOT NULL DEFAULT FALSE | TRUE = only visible when module enabled |
| `module_key` | VARCHAR(50) | FK → modules.key | which module activates this role |
| `description` | TEXT | | |

---

### 5.4 `permissions`

Explicit permission matrix: which role can do what action on which module.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `role_id` | UUID | NOT NULL, FK → roles.id ON DELETE CASCADE | |
| `module_key` | VARCHAR(50) | NOT NULL | attendance / examination |
| `action` | permission_action ENUM | NOT NULL | CREATE / READ / UPDATE / DELETE |
| `scope` | permission_scope ENUM | NOT NULL | ALL / DEPARTMENT / CLASS / SUBJECT / OWN / CHILD |

**Unique:** `(role_id, module_key, action)`  
**Index:** `idx_permissions_role_id`

---

### 5.5 `users`

All institution-level users (teachers, students, parents, admins, etc.).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id ON DELETE CASCADE | |
| `name` | VARCHAR(255) | NOT NULL | |
| `email` | VARCHAR(255) | | nullable: some students may have no email |
| `phone` | VARCHAR(20) | | |
| `password_hash` | TEXT | | null for SSO-only users |
| `avatar_url` | TEXT | | S3 key |
| `gender` | gender ENUM | | MALE / FEMALE / OTHER |
| `date_of_birth` | DATE | | |
| `address` | TEXT | | |
| `employee_code` | VARCHAR(50) | | for staff |
| `student_roll_no` | VARCHAR(50) | | for students |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `email_verified_at` | TIMESTAMPTZ | | |
| `phone_verified_at` | TIMESTAMPTZ | | |
| `last_login_at` | TIMESTAMPTZ | | |
| `password_reset_token` | VARCHAR(255) | | |
| `password_reset_expires` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `deleted_at` | TIMESTAMPTZ | | soft delete |

**Unique:** `(tenant_id, email)` where email IS NOT NULL  
**Unique:** `(tenant_id, student_roll_no)` where student_roll_no IS NOT NULL  
**Indexes:** `idx_users_tenant_id`, `idx_users_email`, `idx_users_is_active`, `idx_users_deleted_at`

---

### 5.6 `role_assignments`

Which user holds which role, scoped to what resource.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | NOT NULL, FK → users.id ON DELETE CASCADE | |
| `role_id` | UUID | NOT NULL, FK → roles.id | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `scope_id` | UUID | | dept_id / class_id / subject_id per role scope |
| `scope_type` | VARCHAR(50) | | DEPARTMENT / CLASS / SUBJECT / NULL |
| `assigned_by` | UUID | FK → users.id | who made the assignment |
| `assigned_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `expires_at` | TIMESTAMPTZ | | for temporary role grants |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

**Unique:** `(user_id, role_id, tenant_id, scope_id)`  
**Indexes:** `idx_role_assignments_user_id`, `idx_role_assignments_tenant_role`, `idx_role_assignments_scope_id`

---

### 5.7 `user_sessions`

Refresh token store (complements Redis cache).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | NOT NULL, FK → users.id ON DELETE CASCADE | |
| `refresh_token_hash` | VARCHAR(255) | NOT NULL, UNIQUE | hashed refresh token |
| `device_info` | TEXT | | user-agent |
| `ip_address` | INET | | |
| `expires_at` | TIMESTAMPTZ | NOT NULL | |
| `revoked_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Index:** `idx_user_sessions_user_id`, `idx_user_sessions_expires_at`

---

## 6. Layer 3 — Institution Structure Tables

### 6.1 `academic_years`

Each institution manages their own academic years.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(50) | NOT NULL | "2024-25" |
| `start_date` | DATE | NOT NULL | |
| `end_date` | DATE | NOT NULL | |
| `is_current` | BOOLEAN | NOT NULL DEFAULT FALSE | only one TRUE per tenant |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, name)`  
**Rule:** Enforce single `is_current = TRUE` per tenant via partial unique index:  
`CREATE UNIQUE INDEX uq_one_current_year ON academic_years (tenant_id) WHERE is_current = TRUE;`

---

### 6.2 `departments`

Academic departments within an institution.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(255) | NOT NULL | "Computer Science" |
| `code` | VARCHAR(20) | NOT NULL | "CS" |
| `hod_id` | UUID | FK → users.id | nullable — may not be assigned yet |
| `description` | TEXT | | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, code)`  
**Indexes:** `idx_departments_tenant_id`, `idx_departments_hod_id`

---

### 6.3 `classes`

A class/batch/section within a department for an academic year.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `department_id` | UUID | NOT NULL, FK → departments.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `name` | VARCHAR(100) | NOT NULL | "FY-B.Sc-A" / "Grade 10-B" |
| `code` | VARCHAR(20) | NOT NULL | "FY-A" |
| `max_strength` | INTEGER | NOT NULL DEFAULT 60 | |
| `class_teacher_id` | UUID | FK → users.id | |
| `room_no` | VARCHAR(20) | | default classroom |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, department_id, academic_year_id, code)`  
**Indexes:** `idx_classes_tenant_id`, `idx_classes_department_id`, `idx_classes_academic_year_id`

---

### 6.4 `subjects`

Subjects/courses taught in a class.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `name` | VARCHAR(255) | NOT NULL | "Data Structures" |
| `code` | VARCHAR(30) | NOT NULL | "CS301" |
| `subject_type` | subject_type ENUM | NOT NULL | THEORY / PRACTICAL / ELECTIVE / PROJECT |
| `credits` | INTEGER | | for college systems |
| `max_marks` | INTEGER | NOT NULL DEFAULT 100 | |
| `passing_marks` | INTEGER | NOT NULL DEFAULT 35 | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, class_id, code)`  
**Index:** `idx_subjects_class_id`

---

### 6.5 `teacher_subjects`

Which teacher teaches which subject (a subject can have multiple teachers: theory + practical).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `teacher_id` | UUID | NOT NULL, FK → users.id | |
| `subject_id` | UUID | NOT NULL, FK → subjects.id | |
| `role_in_subject` | VARCHAR(50) | NOT NULL DEFAULT 'TEACHER' | TEACHER / CO_TEACHER / LAB_ASSISTANT |
| `assigned_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `assigned_by` | UUID | FK → users.id | |

**Unique:** `(teacher_id, subject_id, role_in_subject)`  
**Indexes:** `idx_teacher_subjects_teacher_id`, `idx_teacher_subjects_subject_id`

---

### 6.6 `student_enrollments`

Which students are enrolled in which class for an academic year.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `roll_number` | VARCHAR(50) | | class roll number |
| `enrollment_date` | DATE | NOT NULL DEFAULT CURRENT_DATE | |
| `status` | enrollment_status ENUM | NOT NULL DEFAULT 'ACTIVE' | ACTIVE / TRANSFERRED / DROPPED / COMPLETED |
| `transferred_to` | UUID | FK → classes.id | if transferred |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(student_id, class_id, academic_year_id)`  
**Indexes:** `idx_enrollments_student_id`, `idx_enrollments_class_id`, `idx_enrollments_academic_year_id`

---

### 6.7 `parent_student_links`

Links parent users to their child student users (school type only).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `parent_id` | UUID | NOT NULL, FK → users.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `relation` | VARCHAR(50) | NOT NULL | Father / Mother / Guardian |
| `is_primary` | BOOLEAN | NOT NULL DEFAULT FALSE | primary contact |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(parent_id, student_id)`  
**Indexes:** `idx_parent_student_parent_id`, `idx_parent_student_student_id`

---

## 7. Layer 4 — Core Module Tables

### 7.1 Attendance Module

#### `attendance_sessions`

One session = one class period marked by a teacher on a date.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `subject_id` | UUID | NOT NULL, FK → subjects.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `teacher_id` | UUID | NOT NULL, FK → users.id | who marked |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `date` | DATE | NOT NULL | |
| `period_label` | VARCHAR(30) | NOT NULL | "Period 1" / "Lecture" / "Lab-1" |
| `start_time` | TIME | | |
| `end_time` | TIME | | |
| `total_present` | INTEGER | NOT NULL DEFAULT 0 | computed on submit |
| `total_absent` | INTEGER | NOT NULL DEFAULT 0 | |
| `notes` | TEXT | | session-level notes |
| `is_locked` | BOOLEAN | NOT NULL DEFAULT FALSE | locked after teacher submits |
| `locked_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, subject_id, class_id, date, period_label)`  
**Indexes:** `idx_att_sessions_class_date`, `idx_att_sessions_teacher_id`, `idx_att_sessions_academic_year`

---

#### `attendance_records`

One record per student per session.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `session_id` | UUID | NOT NULL, FK → attendance_sessions.id ON DELETE CASCADE | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `status` | attendance_status ENUM | NOT NULL | PRESENT / ABSENT / LATE / EXCUSED |
| `late_by_minutes` | INTEGER | | only if LATE |
| `remarks` | VARCHAR(255) | | |
| `marked_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_by` | UUID | FK → users.id | if corrected |

**Unique:** `(session_id, student_id)`  
**Indexes:** `idx_att_records_session_id`, `idx_att_records_student_id`, `idx_att_records_status`

---

#### `attendance_leaves`

Medical/planned leave that auto-marks as EXCUSED.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `from_date` | DATE | NOT NULL | |
| `to_date` | DATE | NOT NULL | |
| `reason` | TEXT | NOT NULL | |
| `document_url` | TEXT | | medical certificate S3 key |
| `status` | leave_status ENUM | NOT NULL DEFAULT 'PENDING' | PENDING / APPROVED / REJECTED |
| `reviewed_by` | UUID | FK → users.id | teacher/HOD |
| `reviewed_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 7.2 Examination Module

#### `exams`

An exam or quiz created by a teacher or exam controller.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `title` | VARCHAR(255) | NOT NULL | "Mid-Term Exam - CS301" |
| `subject_id` | UUID | NOT NULL, FK → subjects.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `exam_type` | exam_type ENUM | NOT NULL | MCQ / DESCRIPTIVE / MIXED / QUIZ |
| `mode` | exam_mode ENUM | NOT NULL DEFAULT 'ONLINE' | ONLINE / OFFLINE |
| `total_marks` | INTEGER | NOT NULL | |
| `passing_marks` | INTEGER | NOT NULL | |
| `duration_minutes` | INTEGER | NOT NULL | |
| `instructions` | TEXT | | |
| `scheduled_at` | TIMESTAMPTZ | NOT NULL | when exam starts |
| `window_end_at` | TIMESTAMPTZ | | latest time a student can start |
| `results_release_at` | TIMESTAMPTZ | | scheduled auto-release |
| `status` | exam_status ENUM | NOT NULL DEFAULT 'DRAFT' | DRAFT / PUBLISHED / ONGOING / COMPLETED / RESULTS_RELEASED / CANCELLED |
| `allow_review` | BOOLEAN | NOT NULL DEFAULT FALSE | student can review after submit |
| `shuffle_questions` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `show_score_immediately` | BOOLEAN | NOT NULL DEFAULT FALSE | for quizzes |
| `created_by` | UUID | NOT NULL, FK → users.id | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Indexes:** `idx_exams_class_id`, `idx_exams_subject_id`, `idx_exams_status`, `idx_exams_scheduled_at`

---

#### `exam_sections`

Optional grouping of questions (Paper 1, Section A, etc.).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `exam_id` | UUID | NOT NULL, FK → exams.id ON DELETE CASCADE | |
| `title` | VARCHAR(100) | NOT NULL | "Section A — MCQ" |
| `description` | TEXT | | |
| `max_marks` | INTEGER | NOT NULL | |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | |

---

#### `questions`

Questions belonging to an exam.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `exam_id` | UUID | NOT NULL, FK → exams.id ON DELETE CASCADE | |
| `section_id` | UUID | FK → exam_sections.id | |
| `text` | TEXT | NOT NULL | question body |
| `rich_text` | JSONB | | for formatted/image questions |
| `question_type` | question_type ENUM | NOT NULL | MCQ / SHORT_ANSWER / LONG_ANSWER / TRUE_FALSE / FILL_BLANK / MATCH |
| `marks` | NUMERIC(5,2) | NOT NULL | |
| `negative_marks` | NUMERIC(5,2) | NOT NULL DEFAULT 0 | |
| `image_url` | TEXT | | |
| `explanation` | TEXT | | shown after exam if allow_review |
| `difficulty` | difficulty_level ENUM | | EASY / MEDIUM / HARD |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | |

**Index:** `idx_questions_exam_id`

---

#### `question_options`

Answer choices for MCQ / True-False / Match questions.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `question_id` | UUID | NOT NULL, FK → questions.id ON DELETE CASCADE | |
| `text` | TEXT | NOT NULL | |
| `image_url` | TEXT | | |
| `is_correct` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | |

**Index:** `idx_question_options_question_id`

---

#### `exam_hall_allocations`

For offline exams: room + invigilator assignment.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `exam_id` | UUID | NOT NULL, FK → exams.id | |
| `room_no` | VARCHAR(50) | NOT NULL | |
| `invigilator_id` | UUID | FK → users.id | teacher assigned |
| `student_ids` | UUID[] | NOT NULL | students seated in this room |
| `capacity` | INTEGER | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `exam_attempts`

One row per student per exam (their attempt).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `exam_id` | UUID | NOT NULL, FK → exams.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `started_at` | TIMESTAMPTZ | NOT NULL | |
| `submitted_at` | TIMESTAMPTZ | | NULL = not yet submitted |
| `auto_submitted` | BOOLEAN | NOT NULL DEFAULT FALSE | TRUE if timer expired |
| `total_score` | NUMERIC(8,2) | | computed after grading |
| `percentage` | NUMERIC(5,2) | | |
| `grade` | VARCHAR(5) | | A+ / B / Pass / Fail |
| `status` | attempt_status ENUM | NOT NULL DEFAULT 'IN_PROGRESS' | IN_PROGRESS / SUBMITTED / GRADED / MALPRACTICE |
| `tab_switch_count` | INTEGER | NOT NULL DEFAULT 0 | anti-cheat |
| `ip_address` | INET | | |
| `device_info` | TEXT | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(exam_id, student_id)`  
**Indexes:** `idx_attempts_exam_id`, `idx_attempts_student_id`, `idx_attempts_status`

---

#### `answers`

Each student's answer to each question in their attempt.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `attempt_id` | UUID | NOT NULL, FK → exam_attempts.id ON DELETE CASCADE | |
| `question_id` | UUID | NOT NULL, FK → questions.id | |
| `selected_option_id` | UUID | FK → question_options.id | for MCQ |
| `text_answer` | TEXT | | for SHORT / LONG / FILL |
| `matched_pairs` | JSONB | | for MATCH type |
| `score` | NUMERIC(5,2) | | NULL until graded |
| `is_auto_graded` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `feedback` | TEXT | | teacher feedback on descriptive |
| `graded_by` | UUID | FK → users.id | |
| `graded_at` | TIMESTAMPTZ | | |
| `answered_at` | TIMESTAMPTZ | | |

**Unique:** `(attempt_id, question_id)`  
**Index:** `idx_answers_attempt_id`

---

#### `malpractice_logs`

Records suspected malpractice events.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `attempt_id` | UUID | NOT NULL, FK → exam_attempts.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `type` | VARCHAR(50) | NOT NULL | TAB_SWITCH / COPY_PASTE / MULTIPLE_IP / REPORTED |
| `description` | TEXT | | |
| `evidence_url` | TEXT | | screenshot/log S3 key |
| `action_taken` | VARCHAR(255) | | WARNED / DISQUALIFIED / IGNORED |
| `logged_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `handled_by` | UUID | FK → users.id | exam controller |

---

### 7.3 Assignment & Milestone Module

#### `assignments`

An assignment created by a teacher.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `title` | VARCHAR(255) | NOT NULL | |
| `description` | TEXT | NOT NULL | |
| `subject_id` | UUID | NOT NULL, FK → subjects.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `teacher_id` | UUID | NOT NULL, FK → users.id | |
| `type` | assignment_type ENUM | NOT NULL | REGULAR / MILESTONE / GROUP |
| `total_marks` | INTEGER | NOT NULL | |
| `passing_marks` | INTEGER | NOT NULL | |
| `due_date` | TIMESTAMPTZ | NOT NULL | |
| `allow_late_submission` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `late_penalty_percent` | INTEGER | NOT NULL DEFAULT 0 | |
| `max_file_size_mb` | INTEGER | NOT NULL DEFAULT 10 | |
| `allowed_file_types` | TEXT[] | NOT NULL DEFAULT '{pdf,doc,docx,zip}' | |
| `status` | assignment_status ENUM | NOT NULL DEFAULT 'DRAFT' | DRAFT / PUBLISHED / CLOSED |
| `instructions_url` | TEXT | | S3 key for attached instructions |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Indexes:** `idx_assignments_class_id`, `idx_assignments_teacher_id`, `idx_assignments_due_date`

---

#### `milestones`

Stages within a milestone-type assignment.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `assignment_id` | UUID | NOT NULL, FK → assignments.id ON DELETE CASCADE | |
| `title` | VARCHAR(255) | NOT NULL | "Phase 1 — Proposal" |
| `description` | TEXT | | |
| `sort_order` | INTEGER | NOT NULL | sequence number |
| `marks` | INTEGER | NOT NULL | marks for this milestone |
| `due_date` | TIMESTAMPTZ | | |
| `unlock_after_milestone_id` | UUID | FK → milestones.id | NULL = always visible |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Index:** `idx_milestones_assignment_id`

---

#### `submissions`

A student's submission for an assignment (or a specific milestone).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `assignment_id` | UUID | NOT NULL, FK → assignments.id | |
| `milestone_id` | UUID | FK → milestones.id | NULL for non-milestone assignments |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `text_response` | TEXT | | optional text answer |
| `submitted_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `is_late` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `late_by_minutes` | INTEGER | | |
| `score` | NUMERIC(5,2) | | |
| `grade` | VARCHAR(5) | | |
| `feedback` | TEXT | | |
| `status` | submission_status ENUM | NOT NULL DEFAULT 'SUBMITTED' | SUBMITTED / UNDER_REVIEW / APPROVED / REJECTED / RESUBMIT_REQUESTED |
| `reviewed_by` | UUID | FK → users.id | |
| `reviewed_at` | TIMESTAMPTZ | | |
| `version` | INTEGER | NOT NULL DEFAULT 1 | increments on resubmission |

**Unique:** `(assignment_id, milestone_id, student_id, version)` — allows resubmissions  
**Indexes:** `idx_submissions_assignment_id`, `idx_submissions_student_id`, `idx_submissions_status`

---

#### `submission_files`

Files attached to a submission.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `submission_id` | UUID | NOT NULL, FK → submissions.id ON DELETE CASCADE | |
| `file_name` | VARCHAR(255) | NOT NULL | original filename |
| `file_key` | TEXT | NOT NULL | S3 key |
| `file_size_bytes` | BIGINT | NOT NULL | |
| `mime_type` | VARCHAR(100) | NOT NULL | |
| `uploaded_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 7.4 Notice Board Module

#### `notices`

A notice posted by any authorized role.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `title` | VARCHAR(255) | NOT NULL | |
| `body` | TEXT | NOT NULL | |
| `author_id` | UUID | NOT NULL, FK → users.id | |
| `target_scope` | notice_scope ENUM | NOT NULL | INSTITUTION / DEPARTMENT / CLASS / HOSTEL / TRANSPORT |
| `target_id` | UUID | | dept_id / class_id / null for INSTITUTION |
| `priority` | notice_priority ENUM | NOT NULL DEFAULT 'NORMAL' | NORMAL / IMPORTANT / URGENT |
| `is_pinned` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `published_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `expires_at` | TIMESTAMPTZ | | NULL = never expires |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `deleted_at` | TIMESTAMPTZ | | soft delete |

**Indexes:** `idx_notices_tenant_scope`, `idx_notices_published_at`, `idx_notices_expires_at`

---

#### `notice_attachments`

Files attached to a notice.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `notice_id` | UUID | NOT NULL, FK → notices.id ON DELETE CASCADE | |
| `file_name` | VARCHAR(255) | NOT NULL | |
| `file_key` | TEXT | NOT NULL | S3 key |
| `file_size_bytes` | BIGINT | NOT NULL | |
| `mime_type` | VARCHAR(100) | NOT NULL | |

---

#### `notice_reads`

Tracks which users have read which notices (for read receipts).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `notice_id` | UUID | NOT NULL, FK → notices.id ON DELETE CASCADE | |
| `user_id` | UUID | NOT NULL, FK → users.id ON DELETE CASCADE | |
| `read_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(notice_id, user_id)`  
**Index:** `idx_notice_reads_notice_id`, `idx_notice_reads_user_id`

---

### 7.5 Discussion Forum Module

#### `discussion_threads`

A question or discussion thread posted by student or teacher.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `title` | VARCHAR(255) | NOT NULL | |
| `body` | TEXT | NOT NULL | |
| `author_id` | UUID | NOT NULL, FK → users.id | |
| `scope_type` | VARCHAR(20) | NOT NULL | CLASS / SUBJECT / DEPARTMENT |
| `scope_id` | UUID | NOT NULL | class_id / subject_id / dept_id |
| `tags` | TEXT[] | | topic tags |
| `is_pinned` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `is_locked` | BOOLEAN | NOT NULL DEFAULT FALSE | no more replies |
| `is_resolved` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `resolved_by` | UUID | FK → users.id | |
| `reply_count` | INTEGER | NOT NULL DEFAULT 0 | denormalized count |
| `upvote_count` | INTEGER | NOT NULL DEFAULT 0 | |
| `view_count` | INTEGER | NOT NULL DEFAULT 0 | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `deleted_at` | TIMESTAMPTZ | | soft delete |

**Indexes:** `idx_threads_scope`, `idx_threads_author_id`, `idx_threads_created_at`

---

#### `discussion_replies`

Replies to a thread (flat, not nested).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `thread_id` | UUID | NOT NULL, FK → discussion_threads.id ON DELETE CASCADE | |
| `author_id` | UUID | NOT NULL, FK → users.id | |
| `body` | TEXT | NOT NULL | |
| `is_accepted_answer` | BOOLEAN | NOT NULL DEFAULT FALSE | teacher marks as solution |
| `upvote_count` | INTEGER | NOT NULL DEFAULT 0 | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `deleted_at` | TIMESTAMPTZ | | soft delete |

**Index:** `idx_replies_thread_id`, `idx_replies_author_id`

---

#### `discussion_votes`

Upvotes on threads and replies (one per user per target).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | NOT NULL, FK → users.id ON DELETE CASCADE | |
| `target_type` | VARCHAR(10) | NOT NULL | THREAD / REPLY |
| `target_id` | UUID | NOT NULL | thread_id or reply_id |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(user_id, target_type, target_id)`

---

### 7.6 Content Upload Module

#### `content_items`

Notes, videos, slides, links uploaded by teachers.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `title` | VARCHAR(255) | NOT NULL | |
| `description` | TEXT | | |
| `subject_id` | UUID | NOT NULL, FK → subjects.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `uploaded_by` | UUID | NOT NULL, FK → users.id | |
| `content_type` | content_type ENUM | NOT NULL | PDF / VIDEO / SLIDE / LINK / IMAGE / AUDIO / ZIP |
| `file_key` | TEXT | | S3 key (null for LINK type) |
| `external_url` | TEXT | | for LINK type |
| `file_size_bytes` | BIGINT | | |
| `duration_seconds` | INTEGER | | for VIDEO / AUDIO |
| `chapter` | VARCHAR(100) | | chapter / unit label |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | |
| `is_visible` | BOOLEAN | NOT NULL DEFAULT TRUE | teacher can hide |
| `download_count` | INTEGER | NOT NULL DEFAULT 0 | |
| `view_count` | INTEGER | NOT NULL DEFAULT 0 | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `deleted_at` | TIMESTAMPTZ | | soft delete |

**Indexes:** `idx_content_subject_id`, `idx_content_class_id`, `idx_content_chapter`

---

#### `content_tags`

User-defined tags on content items for easy filtering.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `content_id` | UUID | NOT NULL, FK → content_items.id ON DELETE CASCADE | |
| `tag` | VARCHAR(50) | NOT NULL | |

**Unique:** `(content_id, tag)`

---

#### `content_access_logs`

Tracks who downloaded/viewed what (for analytics).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `content_id` | UUID | NOT NULL, FK → content_items.id | |
| `user_id` | UUID | NOT NULL, FK → users.id | |
| `action` | VARCHAR(10) | NOT NULL | VIEW / DOWNLOAD |
| `accessed_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Index:** `idx_content_access_content_id`, `idx_content_access_user_id`

---

### 7.7 Results & Grade Cards Module

#### `result_publications`

A publication event that releases results for an exam/term.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `title` | VARCHAR(255) | NOT NULL | "Mid-Term Results 2024-25" |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `class_id` | UUID | FK → classes.id | NULL = all classes |
| `exam_ids` | UUID[] | NOT NULL | which exams are included |
| `published_by` | UUID | NOT NULL, FK → users.id | |
| `published_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `is_visible_to_students` | BOOLEAN | NOT NULL DEFAULT FALSE | |

---

#### `student_results`

Compiled result row per student per publication.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `publication_id` | UUID | NOT NULL, FK → result_publications.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `total_marks_obtained` | NUMERIC(8,2) | NOT NULL | |
| `total_marks_possible` | NUMERIC(8,2) | NOT NULL | |
| `percentage` | NUMERIC(5,2) | NOT NULL | |
| `grade` | VARCHAR(5) | NOT NULL | A+ / B / Pass / Fail |
| `rank` | INTEGER | | within class |
| `result` | result_outcome ENUM | NOT NULL | PASS / FAIL / WITHHELD / ABSENT |
| `subject_scores` | JSONB | NOT NULL | [{subject_id, marks, grade}, ...] |
| `remarks` | TEXT | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(publication_id, student_id)`  
**Index:** `idx_results_student_id`, `idx_results_class_id`

---

#### `grade_cards`

Generated PDF grade cards.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `student_result_id` | UUID | NOT NULL, FK → student_results.id | |
| `file_key` | TEXT | NOT NULL | S3 key for the PDF |
| `generated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `template_version` | VARCHAR(20) | NOT NULL DEFAULT '1.0' | |

---

### 7.8 Timetable Module

#### `timetable_slots`

Each slot = one class period on a day of week.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `class_id` | UUID | NOT NULL, FK → classes.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `day_of_week` | SMALLINT | NOT NULL | 1=Mon to 6=Sat |
| `period_number` | SMALLINT | NOT NULL | 1-8 |
| `start_time` | TIME | NOT NULL | |
| `end_time` | TIME | NOT NULL | |
| `subject_id` | UUID | FK → subjects.id | NULL = break/free |
| `teacher_id` | UUID | FK → users.id | |
| `room_no` | VARCHAR(20) | | |
| `slot_type` | slot_type ENUM | NOT NULL DEFAULT 'CLASS' | CLASS / BREAK / LAB / ACTIVITY |
| `effective_from` | DATE | NOT NULL | |
| `effective_to` | DATE | | NULL = current |

**Unique:** `(class_id, day_of_week, period_number, effective_from)`  
**Index:** `idx_timetable_class_id`, `idx_timetable_teacher_id`

---

#### `timetable_substitutions`

One-off teacher substitution for a specific date.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `slot_id` | UUID | NOT NULL, FK → timetable_slots.id | |
| `date` | DATE | NOT NULL | |
| `substitute_teacher_id` | UUID | NOT NULL, FK → users.id | |
| `original_teacher_id` | UUID | NOT NULL, FK → users.id | |
| `reason` | TEXT | | |
| `arranged_by` | UUID | FK → users.id | academic coordinator |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(slot_id, date)`

---

## 8. Layer 5 — Optional Module Tables

### 8.1 Library Module

#### `books`

Book titles in the library catalogue.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `title` | VARCHAR(500) | NOT NULL | |
| `authors` | TEXT[] | NOT NULL | |
| `isbn` | VARCHAR(20) | | |
| `publisher` | VARCHAR(255) | | |
| `edition` | VARCHAR(50) | | |
| `publication_year` | SMALLINT | | |
| `subject_area` | VARCHAR(255) | | |
| `language` | VARCHAR(50) | NOT NULL DEFAULT 'English' | |
| `total_copies` | INTEGER | NOT NULL DEFAULT 1 | |
| `available_copies` | INTEGER | NOT NULL DEFAULT 1 | updated on issue/return |
| `cover_image_url` | TEXT | | |
| `location_code` | VARCHAR(50) | | shelf code |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Indexes:** `idx_books_tenant_id`, `idx_books_isbn`

---

#### `book_copies`

Physical copies of a book title.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `book_id` | UUID | NOT NULL, FK → books.id | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `accession_number` | VARCHAR(50) | NOT NULL | physical tag on book |
| `condition` | book_condition ENUM | NOT NULL DEFAULT 'GOOD' | GOOD / FAIR / DAMAGED / LOST |
| `is_available` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `added_at` | DATE | NOT NULL DEFAULT CURRENT_DATE | |

**Unique:** `(tenant_id, accession_number)`

---

#### `book_issues`

Issue and return records.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `copy_id` | UUID | NOT NULL, FK → book_copies.id | |
| `book_id` | UUID | NOT NULL, FK → books.id | |
| `borrower_id` | UUID | NOT NULL, FK → users.id | student or staff |
| `issued_by` | UUID | NOT NULL, FK → users.id | librarian |
| `issued_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `due_date` | DATE | NOT NULL | |
| `returned_at` | TIMESTAMPTZ | | NULL = not yet returned |
| `returned_to` | UUID | FK → users.id | librarian who accepted return |
| `fine_amount` | NUMERIC(8,2) | NOT NULL DEFAULT 0 | overdue fine |
| `fine_paid` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `fine_paid_at` | TIMESTAMPTZ | | |
| `notes` | TEXT | | |

**Indexes:** `idx_book_issues_borrower_id`, `idx_book_issues_copy_id`, `idx_book_issues_due_date`

---

#### `e_resources`

Digital resources in the library.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `title` | VARCHAR(500) | NOT NULL | |
| `resource_type` | VARCHAR(50) | NOT NULL | EBOOK / JOURNAL / PAPER / LINK |
| `url` | TEXT | | external link |
| `file_key` | TEXT | | S3 key if uploaded |
| `subject_area` | VARCHAR(255) | | |
| `uploaded_by` | UUID | NOT NULL, FK → users.id | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 8.2 Hostel Module

#### `hostel_blocks`

Physical blocks/buildings in the hostel.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(100) | NOT NULL | "Block A — Boys" |
| `gender` | gender ENUM | NOT NULL | MALE / FEMALE |
| `warden_id` | UUID | FK → users.id | |
| `total_rooms` | INTEGER | NOT NULL DEFAULT 0 | |
| `total_capacity` | INTEGER | NOT NULL DEFAULT 0 | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

---

#### `hostel_rooms`

Individual rooms in a hostel block.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `block_id` | UUID | NOT NULL, FK → hostel_blocks.id | |
| `room_number` | VARCHAR(20) | NOT NULL | "A-101" |
| `floor` | SMALLINT | NOT NULL DEFAULT 0 | |
| `capacity` | SMALLINT | NOT NULL DEFAULT 2 | beds per room |
| `room_type` | VARCHAR(30) | NOT NULL DEFAULT 'SHARED' | SINGLE / SHARED / DORMITORY |
| `monthly_fee` | NUMERIC(10,2) | NOT NULL | |
| `amenities` | TEXT[] | | AC / ATTACHED_BATH / WIFI |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

**Unique:** `(block_id, room_number)`

---

#### `hostel_allotments`

Student-to-room assignments.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `room_id` | UUID | NOT NULL, FK → hostel_rooms.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `bed_number` | SMALLINT | | |
| `allotted_from` | DATE | NOT NULL | |
| `allotted_to` | DATE | | NULL = active |
| `allotted_by` | UUID | FK → users.id | warden |
| `status` | allotment_status ENUM | NOT NULL DEFAULT 'ACTIVE' | ACTIVE / VACATED / TRANSFERRED |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique (partial):** `(student_id, academic_year_id)` WHERE status = 'ACTIVE'

---

#### `hostel_attendance`

Daily hostel night attendance.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `room_id` | UUID | NOT NULL, FK → hostel_rooms.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `date` | DATE | NOT NULL | |
| `status` | attendance_status ENUM | NOT NULL | PRESENT / ABSENT / ON_LEAVE |
| `marked_by` | UUID | FK → users.id | warden |
| `marked_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(student_id, date)`

---

#### `hostel_leave_requests`

Students requesting leave from hostel.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `from_date` | DATE | NOT NULL | |
| `to_date` | DATE | NOT NULL | |
| `reason` | TEXT | NOT NULL | |
| `destination` | TEXT | | |
| `contact_during_leave` | VARCHAR(20) | | |
| `status` | leave_status ENUM | NOT NULL DEFAULT 'PENDING' | PENDING / APPROVED / REJECTED |
| `reviewed_by` | UUID | FK → users.id | warden |
| `reviewed_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `hostel_complaints`

Maintenance and other complaints.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `room_id` | UUID | FK → hostel_rooms.id | |
| `category` | VARCHAR(50) | NOT NULL | MAINTENANCE / FOOD / SECURITY / OTHER |
| `description` | TEXT | NOT NULL | |
| `status` | complaint_status ENUM | NOT NULL DEFAULT 'OPEN' | OPEN / IN_PROGRESS / RESOLVED |
| `resolved_by` | UUID | FK → users.id | |
| `resolved_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 8.3 Transport Module

#### `transport_routes`

Bus/van routes operated by the institution.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(100) | NOT NULL | "Route 3 — North Campus" |
| `code` | VARCHAR(20) | NOT NULL | "RT-03" |
| `vehicle_id` | UUID | FK → vehicles.id | |
| `driver_id` | UUID | FK → drivers.id | |
| `monthly_fee` | NUMERIC(10,2) | NOT NULL | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

---

#### `transport_stops`

Stops on a route (ordered).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `route_id` | UUID | NOT NULL, FK → transport_routes.id ON DELETE CASCADE | |
| `name` | VARCHAR(255) | NOT NULL | "City Mall Stop" |
| `stop_order` | SMALLINT | NOT NULL | sequence |
| `latitude` | NUMERIC(10,7) | | GPS |
| `longitude` | NUMERIC(10,7) | | GPS |
| `pickup_time` | TIME | | morning pickup |
| `drop_time` | TIME | | evening drop |

---

#### `vehicles`

Fleet of vehicles.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `registration_no` | VARCHAR(30) | NOT NULL | |
| `vehicle_type` | VARCHAR(30) | NOT NULL | BUS / VAN / AUTO |
| `capacity` | INTEGER | NOT NULL | |
| `make_model` | VARCHAR(100) | | |
| `insurance_expiry` | DATE | | |
| `fitness_expiry` | DATE | | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

---

#### `drivers`

Driver records.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(255) | NOT NULL | |
| `phone` | VARCHAR(20) | NOT NULL | |
| `license_no` | VARCHAR(50) | NOT NULL | |
| `license_expiry` | DATE | | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

---

#### `student_transport`

Assigns a student to a route and stop.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `route_id` | UUID | NOT NULL, FK → transport_routes.id | |
| `stop_id` | UUID | NOT NULL, FK → transport_stops.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `from_date` | DATE | NOT NULL | |
| `to_date` | DATE | | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

**Unique (partial):** `(student_id, academic_year_id)` WHERE is_active = TRUE

---

### 8.4 Placement Module

#### `companies`

Companies that visit for placement drives.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(255) | NOT NULL | |
| `industry` | VARCHAR(100) | | |
| `website` | VARCHAR(255) | | |
| `hr_contact_name` | VARCHAR(255) | | |
| `hr_contact_email` | VARCHAR(255) | | |
| `hr_contact_phone` | VARCHAR(20) | | |
| `logo_url` | TEXT | | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `placement_drives`

A placement drive event.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `company_id` | UUID | NOT NULL, FK → companies.id | |
| `title` | VARCHAR(255) | NOT NULL | "TCS Campus Hiring 2025" |
| `job_role` | VARCHAR(255) | NOT NULL | |
| `job_type` | VARCHAR(30) | NOT NULL | FULL_TIME / INTERNSHIP / CONTRACT |
| `package_lpa` | NUMERIC(8,2) | | CTC in LPA |
| `location` | VARCHAR(255) | | |
| `description` | TEXT | | |
| `application_deadline` | DATE | NOT NULL | |
| `drive_date` | DATE | | |
| `status` | drive_status ENUM | NOT NULL DEFAULT 'UPCOMING' | UPCOMING / OPEN / ONGOING / COMPLETED / CANCELLED |
| `created_by` | UUID | NOT NULL, FK → users.id | placement officer |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `drive_eligibility`

Criteria for who can apply to a drive.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `drive_id` | UUID | NOT NULL, FK → placement_drives.id ON DELETE CASCADE | |
| `department_ids` | UUID[] | NOT NULL | eligible departments |
| `min_percentage` | NUMERIC(5,2) | | |
| `max_backlogs` | INTEGER | NOT NULL DEFAULT 0 | |
| `min_academic_year` | VARCHAR(20) | | "FY" / "SY" / "Final" |
| `custom_criteria` | TEXT | | |

---

#### `placement_applications`

Student applications for a drive.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `drive_id` | UUID | NOT NULL, FK → placement_drives.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `resume_key` | TEXT | | S3 key |
| `status` | application_status ENUM | NOT NULL DEFAULT 'APPLIED' | APPLIED / SHORTLISTED / REJECTED / PLACED / WITHDRAWN |
| `applied_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(drive_id, student_id)`

---

#### `interview_rounds`

Rounds of interview for a specific application.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `application_id` | UUID | NOT NULL, FK → placement_applications.id | |
| `round_number` | SMALLINT | NOT NULL | 1, 2, 3 |
| `round_type` | VARCHAR(30) | NOT NULL | APTITUDE / TECHNICAL / HR / GD / CODING |
| `scheduled_at` | TIMESTAMPTZ | | |
| `venue` | TEXT | | physical or online link |
| `result` | interview_result ENUM | | PASS / FAIL / ON_HOLD / ABSENT |
| `feedback` | TEXT | | |
| `conducted_at` | TIMESTAMPTZ | | |

---

#### `placement_offers`

Final job offers issued to students.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `application_id` | UUID | NOT NULL, FK → placement_applications.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `drive_id` | UUID | NOT NULL, FK → placement_drives.id | |
| `offer_letter_key` | TEXT | | S3 key |
| `package_lpa` | NUMERIC(8,2) | NOT NULL | |
| `joining_date` | DATE | | |
| `status` | offer_status ENUM | NOT NULL DEFAULT 'ISSUED' | ISSUED / ACCEPTED / DECLINED / REVOKED |
| `issued_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 8.5 HR Module

#### `staff_profiles`

Extended HR profile for each staff member.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | NOT NULL, UNIQUE, FK → users.id | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `employee_code` | VARCHAR(50) | NOT NULL | |
| `designation` | VARCHAR(100) | NOT NULL | |
| `department_id` | UUID | FK → departments.id | |
| `employment_type` | employment_type ENUM | NOT NULL | FULL_TIME / PART_TIME / CONTRACT / VISITING |
| `date_of_joining` | DATE | NOT NULL | |
| `date_of_leaving` | DATE | | |
| `qualification` | TEXT | | |
| `experience_years` | SMALLINT | NOT NULL DEFAULT 0 | |
| `pan_number` | VARCHAR(20) | | |
| `bank_account_no` | VARCHAR(30) | | |
| `bank_ifsc` | VARCHAR(15) | | |
| `bank_name` | VARCHAR(100) | | |
| `pf_number` | VARCHAR(30) | | |
| `emergency_contact_name` | VARCHAR(255) | | |
| `emergency_contact_phone` | VARCHAR(20) | | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `leave_policies`

Leave policies defined by HR for the institution.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(100) | NOT NULL | "Casual Leave" / "Sick Leave" |
| `code` | VARCHAR(10) | NOT NULL | CL / SL / EL |
| `days_per_year` | INTEGER | NOT NULL | |
| `is_carry_forward` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `max_carry_forward_days` | INTEGER | NOT NULL DEFAULT 0 | |
| `applies_to` | employment_type ENUM[] | NOT NULL | which employment types |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

**Unique:** `(tenant_id, code)`

---

#### `leave_requests`

Staff leave applications.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `staff_id` | UUID | NOT NULL, FK → users.id | |
| `policy_id` | UUID | NOT NULL, FK → leave_policies.id | |
| `from_date` | DATE | NOT NULL | |
| `to_date` | DATE | NOT NULL | |
| `total_days` | NUMERIC(4,1) | NOT NULL | supports half-day |
| `reason` | TEXT | NOT NULL | |
| `document_key` | TEXT | | S3 key for supporting doc |
| `status` | leave_status ENUM | NOT NULL DEFAULT 'PENDING' | PENDING / APPROVED / REJECTED / CANCELLED |
| `reviewed_by` | UUID | FK → users.id | HR Manager / HOD |
| `reviewed_at` | TIMESTAMPTZ | | |
| `review_note` | TEXT | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `salary_structures`

Salary component definition per staff.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `staff_id` | UUID | NOT NULL, FK → users.id | |
| `effective_from` | DATE | NOT NULL | |
| `basic_salary` | NUMERIC(12,2) | NOT NULL | |
| `hra` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | |
| `da` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | |
| `ta` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | |
| `other_allowances` | JSONB | | [{name, amount}] |
| `pf_deduction` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | |
| `tax_deduction` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | |
| `other_deductions` | JSONB | | [{name, amount}] |
| `gross_salary` | NUMERIC(12,2) | NOT NULL | computed |
| `net_salary` | NUMERIC(12,2) | NOT NULL | computed |
| `created_by` | UUID | FK → users.id | HR Manager |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `payroll_runs`

A monthly payroll processing event.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `month` | SMALLINT | NOT NULL | 1-12 |
| `year` | SMALLINT | NOT NULL | |
| `status` | payroll_status ENUM | NOT NULL DEFAULT 'DRAFT' | DRAFT / PROCESSED / PAID / LOCKED |
| `processed_by` | UUID | FK → users.id | |
| `processed_at` | TIMESTAMPTZ | | |
| `paid_at` | TIMESTAMPTZ | | |

**Unique:** `(tenant_id, month, year)`

---

#### `payslips`

Individual payslip per staff per payroll run.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `payroll_run_id` | UUID | NOT NULL, FK → payroll_runs.id | |
| `staff_id` | UUID | NOT NULL, FK → users.id | |
| `working_days` | SMALLINT | NOT NULL | |
| `present_days` | SMALLINT | NOT NULL | |
| `leave_days` | SMALLINT | NOT NULL DEFAULT 0 | |
| `lop_days` | NUMERIC(4,1) | NOT NULL DEFAULT 0 | loss of pay |
| `gross_salary` | NUMERIC(12,2) | NOT NULL | |
| `total_deductions` | NUMERIC(12,2) | NOT NULL | |
| `net_salary` | NUMERIC(12,2) | NOT NULL | |
| `components` | JSONB | NOT NULL | earnings + deductions snapshot |
| `file_key` | TEXT | | generated PDF payslip S3 key |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(payroll_run_id, staff_id)`

---

#### `appraisal_cycles`

Annual performance appraisal cycle.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(100) | NOT NULL | "Appraisal 2024-25" |
| `academic_year_id` | UUID | FK → academic_years.id | |
| `start_date` | DATE | NOT NULL | |
| `end_date` | DATE | NOT NULL | |
| `status` | appraisal_status ENUM | NOT NULL DEFAULT 'PLANNED' | PLANNED / OPEN / CLOSED |

---

#### `appraisals`

Individual staff appraisal within a cycle.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `cycle_id` | UUID | NOT NULL, FK → appraisal_cycles.id | |
| `staff_id` | UUID | NOT NULL, FK → users.id | |
| `reviewer_id` | UUID | NOT NULL, FK → users.id | HOD or HR |
| `self_score` | NUMERIC(4,2) | | out of 10 |
| `reviewer_score` | NUMERIC(4,2) | | |
| `final_score` | NUMERIC(4,2) | | |
| `rating` | VARCHAR(20) | | Excellent / Good / Average |
| `comments` | TEXT | | |
| `status` | appraisal_status ENUM | NOT NULL DEFAULT 'PENDING' | |
| `submitted_at` | TIMESTAMPTZ | | |

**Unique:** `(cycle_id, staff_id)`

---

#### `staff_documents`

Contracts, certificates, offer letters stored for staff.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `staff_id` | UUID | NOT NULL, FK → users.id | |
| `document_type` | VARCHAR(50) | NOT NULL | OFFER_LETTER / CONTRACT / CERTIFICATE / ID_PROOF / OTHER |
| `file_name` | VARCHAR(255) | NOT NULL | |
| `file_key` | TEXT | NOT NULL | S3 key |
| `uploaded_by` | UUID | FK → users.id | |
| `uploaded_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 8.6 Admission Module

#### `admission_cycles`

An admission intake cycle (e.g., "Admissions 2025-26").

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(100) | NOT NULL | "Admissions 2025-26" |
| `academic_year_id` | UUID | FK → academic_years.id | |
| `application_open` | DATE | NOT NULL | |
| `application_close` | DATE | NOT NULL | |
| `status` | admission_cycle_status ENUM | NOT NULL DEFAULT 'UPCOMING' | UPCOMING / OPEN / CLOSED / COMPLETED |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `admission_applications`

A prospective student's application.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `cycle_id` | UUID | NOT NULL, FK → admission_cycles.id | |
| `applicant_name` | VARCHAR(255) | NOT NULL | |
| `applicant_email` | VARCHAR(255) | NOT NULL | |
| `applicant_phone` | VARCHAR(20) | NOT NULL | |
| `date_of_birth` | DATE | | |
| `gender` | gender ENUM | | |
| `category` | VARCHAR(30) | | GENERAL / OBC / SC / ST / EWS |
| `applied_for_dept` | UUID | FK → departments.id | |
| `previous_marks_percent` | NUMERIC(5,2) | | |
| `previous_institution` | VARCHAR(255) | | |
| `status` | admission_status ENUM | NOT NULL DEFAULT 'SUBMITTED' | SUBMITTED / UNDER_REVIEW / SHORTLISTED / WAITLISTED / ADMITTED / REJECTED |
| `assigned_to` | UUID | FK → users.id | admission officer |
| `enrolled_user_id` | UUID | FK → users.id | set when admitted + enrolled |
| `notes` | TEXT | | internal notes |
| `submitted_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `application_documents`

Documents submitted with an admission application.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `application_id` | UUID | NOT NULL, FK → admission_applications.id ON DELETE CASCADE | |
| `document_type` | VARCHAR(50) | NOT NULL | MARKSHEET / PHOTO / ID_PROOF / CASTE_CERT / OTHER |
| `file_key` | TEXT | NOT NULL | S3 key |
| `is_verified` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `verified_by` | UUID | FK → users.id | |
| `uploaded_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `merit_lists`

Generated merit/selection lists for a cycle.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `cycle_id` | UUID | NOT NULL, FK → admission_cycles.id | |
| `list_number` | SMALLINT | NOT NULL DEFAULT 1 | First merit list / Second merit list |
| `department_id` | UUID | FK → departments.id | |
| `category` | VARCHAR(30) | | GENERAL / OBC etc. |
| `application_ids` | UUID[] | NOT NULL | ordered by merit |
| `published_at` | TIMESTAMPTZ | | |
| `created_by` | UUID | NOT NULL, FK → users.id | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 8.7 Inventory Module

#### `inventory_categories`

Categories for stock items.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(100) | NOT NULL | "Lab Equipment" / "Stationery" |
| `parent_id` | UUID | FK → inventory_categories.id | sub-categories |

---

#### `inventory_items`

Master list of inventory items.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `category_id` | UUID | FK → inventory_categories.id | |
| `name` | VARCHAR(255) | NOT NULL | |
| `code` | VARCHAR(50) | NOT NULL | |
| `unit` | VARCHAR(20) | NOT NULL | pcs / kg / litre / box |
| `current_stock` | NUMERIC(10,2) | NOT NULL DEFAULT 0 | |
| `reorder_level` | NUMERIC(10,2) | NOT NULL DEFAULT 0 | triggers low-stock alert |
| `unit_cost` | NUMERIC(10,2) | NOT NULL DEFAULT 0 | |
| `location` | VARCHAR(100) | | storage location |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, code)`

---

#### `stock_transactions`

Every stock in/out event.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `item_id` | UUID | NOT NULL, FK → inventory_items.id | |
| `transaction_type` | stock_txn_type ENUM | NOT NULL | STOCK_IN / STOCK_OUT / ADJUSTMENT / RETURN |
| `quantity` | NUMERIC(10,2) | NOT NULL | |
| `balance_after` | NUMERIC(10,2) | NOT NULL | snapshot |
| `department_id` | UUID | FK → departments.id | issued to which dept |
| `reference_no` | VARCHAR(100) | | PO number or reason |
| `notes` | TEXT | | |
| `transacted_by` | UUID | NOT NULL, FK → users.id | store manager |
| `transacted_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

#### `vendors`

Suppliers for inventory.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(255) | NOT NULL | |
| `contact_person` | VARCHAR(255) | | |
| `phone` | VARCHAR(20) | | |
| `email` | VARCHAR(255) | | |
| `address` | TEXT | | |
| `gst_number` | VARCHAR(20) | | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

---

#### `purchase_orders`

Purchase orders raised by store manager.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `vendor_id` | UUID | NOT NULL, FK → vendors.id | |
| `po_number` | VARCHAR(50) | NOT NULL | |
| `total_amount` | NUMERIC(12,2) | NOT NULL | |
| `status` | po_status ENUM | NOT NULL DEFAULT 'DRAFT' | DRAFT / SENT / ACKNOWLEDGED / DELIVERED / CANCELLED |
| `created_by` | UUID | NOT NULL, FK → users.id | |
| `approved_by` | UUID | FK → users.id | institution admin |
| `ordered_at` | DATE | | |
| `expected_delivery` | DATE | | |
| `delivered_at` | DATE | | |
| `notes` | TEXT | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, po_number)`

---

#### `purchase_order_items`

Line items in a purchase order.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `po_id` | UUID | NOT NULL, FK → purchase_orders.id ON DELETE CASCADE | |
| `item_id` | UUID | NOT NULL, FK → inventory_items.id | |
| `quantity` | NUMERIC(10,2) | NOT NULL | |
| `unit_price` | NUMERIC(10,2) | NOT NULL | |
| `total_price` | NUMERIC(12,2) | NOT NULL | |
| `received_quantity` | NUMERIC(10,2) | NOT NULL DEFAULT 0 | |

---

## 9. Layer 6 — Platform ERP Tables (Finance Module)

### 9.1 `fee_structures`

Fee structure template defined per academic year / class type.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `name` | VARCHAR(100) | NOT NULL | "General Fee — FY 2025-26" |
| `applicable_to` | UUID[] | | class_ids this structure applies to |
| `total_amount` | NUMERIC(12,2) | NOT NULL | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

---

### 9.2 `fee_heads`

Individual fee components within a fee structure.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `structure_id` | UUID | NOT NULL, FK → fee_structures.id ON DELETE CASCADE | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(100) | NOT NULL | "Tuition Fee" / "Lab Fee" / "Library Fee" |
| `amount` | NUMERIC(12,2) | NOT NULL | |
| `is_refundable` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | |

---

### 9.3 `student_fee_accounts`

One account per student per academic year.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `structure_id` | UUID | NOT NULL, FK → fee_structures.id | |
| `total_fee` | NUMERIC(12,2) | NOT NULL | |
| `concession_amount` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | |
| `scholarship_amount` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | |
| `net_payable` | NUMERIC(12,2) | NOT NULL | total - concession - scholarship |
| `total_paid` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | updated on payment |
| `balance_due` | NUMERIC(12,2) | NOT NULL | net_payable - total_paid |
| `status` | fee_status ENUM | NOT NULL DEFAULT 'UNPAID' | UNPAID / PARTIAL / PAID / WAIVED |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(student_id, academic_year_id)`

---

### 9.4 `fee_installments`

Installment schedule for a student's fee account.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `fee_account_id` | UUID | NOT NULL, FK → student_fee_accounts.id | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `installment_number` | SMALLINT | NOT NULL | 1, 2, 3... |
| `label` | VARCHAR(50) | NOT NULL | "Term 1" / "Q1" |
| `amount` | NUMERIC(12,2) | NOT NULL | |
| `due_date` | DATE | NOT NULL | |
| `paid_amount` | NUMERIC(12,2) | NOT NULL DEFAULT 0 | |
| `status` | installment_status ENUM | NOT NULL DEFAULT 'PENDING' | PENDING / PAID / OVERDUE / WAIVED |
| `late_fine` | NUMERIC(8,2) | NOT NULL DEFAULT 0 | |

---

### 9.5 `fee_payments`

Each payment transaction.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `fee_account_id` | UUID | NOT NULL, FK → student_fee_accounts.id | |
| `installment_id` | UUID | FK → fee_installments.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `amount` | NUMERIC(12,2) | NOT NULL | |
| `payment_mode` | payment_mode ENUM | NOT NULL | CASH / ONLINE / CHEQUE / DD / UPI |
| `transaction_reference` | VARCHAR(255) | | bank ref / UTR / cheque no |
| `payment_date` | DATE | NOT NULL | |
| `receipt_number` | VARCHAR(50) | NOT NULL | |
| `collected_by` | UUID | NOT NULL, FK → users.id | accountant |
| `notes` | TEXT | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Unique:** `(tenant_id, receipt_number)`

---

### 9.6 `scholarships`

Scholarship schemes defined by the institution.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `name` | VARCHAR(255) | NOT NULL | "Merit Scholarship" |
| `type` | scholarship_type ENUM | NOT NULL | PERCENTAGE / FIXED_AMOUNT / FULL_WAIVER |
| `value` | NUMERIC(10,2) | NOT NULL | % or fixed amount |
| `criteria` | TEXT | | eligibility description |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

---

### 9.7 `scholarship_grants`

Scholarship awarded to a specific student.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `scholarship_id` | UUID | NOT NULL, FK → scholarships.id | |
| `student_id` | UUID | NOT NULL, FK → users.id | |
| `fee_account_id` | UUID | NOT NULL, FK → student_fee_accounts.id | |
| `amount_granted` | NUMERIC(12,2) | NOT NULL | computed at time of grant |
| `academic_year_id` | UUID | NOT NULL, FK → academic_years.id | |
| `granted_by` | UUID | FK → users.id | accountant / admin |
| `granted_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `remarks` | TEXT | | |

---

## 10. Layer 7 — Notification & Audit Tables

### 10.1 `notifications`

In-app notification inbox for every user.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | FK → tenants.id | NULL for platform notifications |
| `user_id` | UUID | NOT NULL, FK → users.id ON DELETE CASCADE | |
| `title` | VARCHAR(255) | NOT NULL | |
| `body` | TEXT | NOT NULL | |
| `type` | VARCHAR(50) | NOT NULL | ATTENDANCE / EXAM / ASSIGNMENT / NOTICE / FEE / MILESTONE / SYSTEM |
| `data` | JSONB | NOT NULL DEFAULT '{}' | deep-link data e.g. {exam_id} |
| `is_read` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `read_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Indexes:** `idx_notifications_user_id`, `idx_notifications_is_read`, `idx_notifications_created_at`

---

### 10.2 `device_tokens`

FCM device tokens for push notifications.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | NOT NULL, FK → users.id ON DELETE CASCADE | |
| `token` | TEXT | NOT NULL | FCM token |
| `platform` | VARCHAR(10) | NOT NULL | ANDROID / IOS / WEB |
| `registered_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `last_used_at` | TIMESTAMPTZ | | |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |

**Unique:** `(user_id, token)`

---

### 10.3 `audit_logs`

Immutable log of every write action across the platform.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant_id` | UUID | FK → tenants.id | NULL for platform actions |
| `user_id` | UUID | NOT NULL | actor (no FK — logs survive user deletion) |
| `user_role` | VARCHAR(100) | NOT NULL | role at time of action |
| `action` | VARCHAR(100) | NOT NULL | CREATE_EXAM / TOGGLE_MODULE / DELETE_USER |
| `entity` | VARCHAR(100) | NOT NULL | Exam / User / TenantModule |
| `entity_id` | UUID | | |
| `old_value` | JSONB | | before state (for UPDATE) |
| `new_value` | JSONB | | after state |
| `ip_address` | INET | | |
| `user_agent` | TEXT | | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

**Indexes:** `idx_audit_tenant_id`, `idx_audit_user_id`, `idx_audit_entity`, `idx_audit_created_at`  
**Note:** Audit logs are **append-only**. No UPDATE or DELETE ever runs on this table. Partition by month for performance at scale.

---

## 11. Full Index Strategy

```sql
-- Users
CREATE INDEX idx_users_tenant_id        ON users (tenant_id);
CREATE INDEX idx_users_email            ON users (email) WHERE email IS NOT NULL;
CREATE INDEX idx_users_is_active        ON users (tenant_id, is_active);
CREATE INDEX idx_users_deleted_at       ON users (deleted_at) WHERE deleted_at IS NULL;

-- Role Assignments
CREATE INDEX idx_ra_user_id             ON role_assignments (user_id);
CREATE INDEX idx_ra_tenant_role         ON role_assignments (tenant_id, role_id);
CREATE INDEX idx_ra_scope_id            ON role_assignments (scope_id) WHERE scope_id IS NOT NULL;

-- Tenant Modules
CREATE INDEX idx_tm_tenant_enabled      ON tenant_modules (tenant_id, is_enabled);

-- Attendance
CREATE INDEX idx_att_sessions_class_date       ON attendance_sessions (class_id, date);
CREATE INDEX idx_att_sessions_teacher          ON attendance_sessions (teacher_id);
CREATE INDEX idx_att_records_session           ON attendance_records (session_id);
CREATE INDEX idx_att_records_student           ON attendance_records (student_id);
CREATE INDEX idx_att_records_student_status    ON attendance_records (student_id, status);

-- Exams
CREATE INDEX idx_exams_class_subject    ON exams (class_id, subject_id);
CREATE INDEX idx_exams_status_date      ON exams (status, scheduled_at);
CREATE INDEX idx_questions_exam         ON questions (exam_id, sort_order);
CREATE INDEX idx_attempts_exam_student  ON exam_attempts (exam_id, student_id);
CREATE INDEX idx_attempts_status        ON exam_attempts (status);
CREATE INDEX idx_answers_attempt        ON answers (attempt_id);

-- Assignments
CREATE INDEX idx_assignments_class      ON assignments (class_id, due_date);
CREATE INDEX idx_submissions_assignment ON submissions (assignment_id, student_id);
CREATE INDEX idx_submissions_status     ON submissions (status);

-- Notices
CREATE INDEX idx_notices_scope_target   ON notices (tenant_id, target_scope, target_id);
CREATE INDEX idx_notices_expiry         ON notices (expires_at) WHERE expires_at IS NOT NULL;

-- Discussion
CREATE INDEX idx_threads_scope          ON discussion_threads (scope_type, scope_id, created_at DESC);
CREATE INDEX idx_replies_thread         ON discussion_replies (thread_id, created_at);

-- Content
CREATE INDEX idx_content_subject_class  ON content_items (subject_id, class_id, is_visible);
CREATE INDEX idx_content_chapter        ON content_items (subject_id, chapter);

-- Results
CREATE INDEX idx_results_publication    ON student_results (publication_id);
CREATE INDEX idx_results_student        ON student_results (student_id);

-- Timetable
CREATE INDEX idx_timetable_class_day    ON timetable_slots (class_id, day_of_week, period_number);
CREATE INDEX idx_timetable_teacher      ON timetable_slots (teacher_id);

-- Fee
CREATE INDEX idx_fee_payments_student   ON fee_payments (student_id);
CREATE INDEX idx_fee_payments_date      ON fee_payments (payment_date);
CREATE INDEX idx_installments_due       ON fee_installments (due_date, status);

-- Notifications
CREATE INDEX idx_notif_user_unread      ON notifications (user_id, is_read, created_at DESC);

-- Audit
CREATE INDEX idx_audit_tenant_time      ON audit_logs (tenant_id, created_at DESC);
CREATE INDEX idx_audit_entity_id        ON audit_logs (entity, entity_id);
```

---

## 12. Foreign Key Map

```
plans                ←── tenants.plan_id
tenants              ←── subscriptions.tenant_id
tenants              ←── tenant_modules.tenant_id
tenants              ←── users.tenant_id
tenants              ←── departments.tenant_id
tenants              ←── academic_years.tenant_id
tenants              ←── audit_logs.tenant_id

users                ←── role_assignments.user_id
users                ←── role_assignments.assigned_by
roles                ←── role_assignments.role_id
roles                ←── permissions.role_id

users                ←── student_enrollments.student_id
classes              ←── student_enrollments.class_id
academic_years       ←── student_enrollments.academic_year_id

departments          ←── classes.department_id
academic_years       ←── classes.academic_year_id
classes              ←── subjects.class_id
subjects             ←── teacher_subjects.subject_id
users                ←── teacher_subjects.teacher_id

classes              ←── attendance_sessions.class_id
subjects             ←── attendance_sessions.subject_id
users                ←── attendance_sessions.teacher_id
attendance_sessions  ←── attendance_records.session_id
users                ←── attendance_records.student_id

subjects             ←── exams.subject_id
classes              ←── exams.class_id
exams                ←── questions.exam_id
questions            ←── question_options.question_id
exams                ←── exam_attempts.exam_id
users                ←── exam_attempts.student_id
exam_attempts        ←── answers.attempt_id
questions            ←── answers.question_id

subjects             ←── assignments.subject_id
classes              ←── assignments.class_id
assignments          ←── milestones.assignment_id
assignments          ←── submissions.assignment_id
milestones           ←── submissions.milestone_id
users                ←── submissions.student_id
submissions          ←── submission_files.submission_id

subjects             ←── content_items.subject_id
classes              ←── content_items.class_id

academic_years       ←── fee_structures.academic_year_id
fee_structures       ←── fee_heads.structure_id
fee_structures       ←── student_fee_accounts.structure_id
users                ←── student_fee_accounts.student_id
student_fee_accounts ←── fee_installments.fee_account_id
student_fee_accounts ←── fee_payments.fee_account_id

users                ←── staff_profiles.user_id
leave_policies       ←── leave_requests.policy_id
users                ←── leave_requests.staff_id
staff_profiles       ←── salary_structures.staff_id
payroll_runs         ←── payslips.payroll_run_id
users                ←── payslips.staff_id

hostel_blocks        ←── hostel_rooms.block_id
hostel_rooms         ←── hostel_allotments.room_id
users                ←── hostel_allotments.student_id

transport_routes     ←── transport_stops.route_id
transport_routes     ←── student_transport.route_id
transport_stops      ←── student_transport.stop_id

companies            ←── placement_drives.company_id
placement_drives     ←── placement_applications.drive_id
users                ←── placement_applications.student_id
placement_applications ←── interview_rounds.application_id
placement_applications ←── placement_offers.application_id

admission_cycles     ←── admission_applications.cycle_id
admission_applications ←── application_documents.application_id

inventory_items      ←── stock_transactions.item_id
vendors              ←── purchase_orders.vendor_id
purchase_orders      ←── purchase_order_items.po_id
inventory_items      ←── purchase_order_items.item_id
```

---

## 13. Enum Reference

```sql
-- Tenant
CREATE TYPE tenant_type         AS ENUM ('SCHOOL', 'COLLEGE');
CREATE TYPE subscription_status AS ENUM ('TRIAL', 'ACTIVE', 'PAST_DUE', 'CANCELLED');
CREATE TYPE platform_role       AS ENUM ('SUPER_ADMIN', 'SUPPORT', 'SALES', 'FINANCE');

-- RBAC
CREATE TYPE scope_level         AS ENUM ('PLATFORM', 'INSTITUTION', 'DEPARTMENT', 'CLASS', 'SUBJECT', 'SELF', 'CHILD');
CREATE TYPE permission_action   AS ENUM ('CREATE', 'READ', 'UPDATE', 'DELETE');
CREATE TYPE permission_scope    AS ENUM ('ALL', 'DEPARTMENT', 'CLASS', 'SUBJECT', 'OWN', 'CHILD');

-- Users
CREATE TYPE gender              AS ENUM ('MALE', 'FEMALE', 'OTHER');
CREATE TYPE enrollment_status   AS ENUM ('ACTIVE', 'TRANSFERRED', 'DROPPED', 'COMPLETED');

-- Subjects
CREATE TYPE subject_type        AS ENUM ('THEORY', 'PRACTICAL', 'ELECTIVE', 'PROJECT');

-- Attendance
CREATE TYPE attendance_status   AS ENUM ('PRESENT', 'ABSENT', 'LATE', 'EXCUSED');
CREATE TYPE leave_status        AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED');

-- Examination
CREATE TYPE exam_type           AS ENUM ('MCQ', 'DESCRIPTIVE', 'MIXED', 'QUIZ');
CREATE TYPE exam_mode           AS ENUM ('ONLINE', 'OFFLINE');
CREATE TYPE exam_status         AS ENUM ('DRAFT', 'PUBLISHED', 'ONGOING', 'COMPLETED', 'RESULTS_RELEASED', 'CANCELLED');
CREATE TYPE question_type       AS ENUM ('MCQ', 'SHORT_ANSWER', 'LONG_ANSWER', 'TRUE_FALSE', 'FILL_BLANK', 'MATCH');
CREATE TYPE difficulty_level    AS ENUM ('EASY', 'MEDIUM', 'HARD');
CREATE TYPE attempt_status      AS ENUM ('IN_PROGRESS', 'SUBMITTED', 'GRADED', 'MALPRACTICE');

-- Assignment
CREATE TYPE assignment_type     AS ENUM ('REGULAR', 'MILESTONE', 'GROUP');
CREATE TYPE assignment_status   AS ENUM ('DRAFT', 'PUBLISHED', 'CLOSED');
CREATE TYPE submission_status   AS ENUM ('SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'RESUBMIT_REQUESTED');

-- Notices
CREATE TYPE notice_scope        AS ENUM ('INSTITUTION', 'DEPARTMENT', 'CLASS', 'HOSTEL', 'TRANSPORT');
CREATE TYPE notice_priority     AS ENUM ('NORMAL', 'IMPORTANT', 'URGENT');

-- Content
CREATE TYPE content_type        AS ENUM ('PDF', 'VIDEO', 'SLIDE', 'LINK', 'IMAGE', 'AUDIO', 'ZIP');

-- Results
CREATE TYPE result_outcome      AS ENUM ('PASS', 'FAIL', 'WITHHELD', 'ABSENT');

-- Timetable
CREATE TYPE slot_type           AS ENUM ('CLASS', 'BREAK', 'LAB', 'ACTIVITY');

-- Library
CREATE TYPE book_condition      AS ENUM ('GOOD', 'FAIR', 'DAMAGED', 'LOST');

-- Hostel
CREATE TYPE allotment_status    AS ENUM ('ACTIVE', 'VACATED', 'TRANSFERRED');
CREATE TYPE complaint_status    AS ENUM ('OPEN', 'IN_PROGRESS', 'RESOLVED');

-- Placement
CREATE TYPE drive_status        AS ENUM ('UPCOMING', 'OPEN', 'ONGOING', 'COMPLETED', 'CANCELLED');
CREATE TYPE application_status  AS ENUM ('APPLIED', 'SHORTLISTED', 'REJECTED', 'PLACED', 'WITHDRAWN');
CREATE TYPE interview_result    AS ENUM ('PASS', 'FAIL', 'ON_HOLD', 'ABSENT');
CREATE TYPE offer_status        AS ENUM ('ISSUED', 'ACCEPTED', 'DECLINED', 'REVOKED');

-- HR
CREATE TYPE employment_type     AS ENUM ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'VISITING');
CREATE TYPE payroll_status      AS ENUM ('DRAFT', 'PROCESSED', 'PAID', 'LOCKED');
CREATE TYPE appraisal_status    AS ENUM ('PLANNED', 'OPEN', 'CLOSED', 'PENDING');

-- Admission
CREATE TYPE admission_status         AS ENUM ('SUBMITTED', 'UNDER_REVIEW', 'SHORTLISTED', 'WAITLISTED', 'ADMITTED', 'REJECTED');
CREATE TYPE admission_cycle_status   AS ENUM ('UPCOMING', 'OPEN', 'CLOSED', 'COMPLETED');

-- Finance
CREATE TYPE fee_status           AS ENUM ('UNPAID', 'PARTIAL', 'PAID', 'WAIVED');
CREATE TYPE installment_status   AS ENUM ('PENDING', 'PAID', 'OVERDUE', 'WAIVED');
CREATE TYPE payment_mode         AS ENUM ('CASH', 'ONLINE', 'CHEQUE', 'DD', 'UPI');
CREATE TYPE scholarship_type     AS ENUM ('PERCENTAGE', 'FIXED_AMOUNT', 'FULL_WAIVER');

-- Inventory
CREATE TYPE stock_txn_type       AS ENUM ('STOCK_IN', 'STOCK_OUT', 'ADJUSTMENT', 'RETURN');
CREATE TYPE po_status             AS ENUM ('DRAFT', 'SENT', 'ACKNOWLEDGED', 'DELIVERED', 'CANCELLED');

-- Support
CREATE TYPE ticket_priority      AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
CREATE TYPE ticket_status        AS ENUM ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED');
```

---

## 14. Complete Prisma Schema

> The full `schema.prisma` covering all 100 tables above is available in the repository at:
> `apps/api/prisma/schema.prisma`
>
> Key Prisma config:

```prisma
generator client {
  provider        = "prisma-client-js"
  previewFeatures = ["postgresqlExtensions"]
}

datasource db {
  provider   = "postgresql"
  url        = env("DATABASE_URL")
  extensions = [pgcrypto]   // for gen_random_uuid()
}
```

> Run migrations:
> ```bash
> npx prisma migrate dev --name add_all_modules
> npx prisma db seed
> npx prisma studio        # visual DB browser
> ```

---

*Document version: 1.0 | 100 tables · 15 modules · 22 roles · PostgreSQL 15*  
*Companion documents: Role-Based System Design v1.0 · Developer Deployment Guide v1.0*

---

## 15. Full Prisma Schema (All 100 Tables)

```prisma
// ================================================================
// apps/api/prisma/schema.prisma
// ERP + LMS Platform — Complete Schema
// ================================================================

generator client {
  provider        = "prisma-client-js"
  previewFeatures = ["postgresqlExtensions"]
}

datasource db {
  provider   = "postgresql"
  url        = env("DATABASE_URL")
  extensions = [pgcrypto]
}

// ─────────────────────────────────────────────
// ENUMS
// ─────────────────────────────────────────────

enum TenantType          { SCHOOL COLLEGE }
enum SubscriptionStatus  { TRIAL ACTIVE PAST_DUE CANCELLED }
enum PlatformRole        { SUPER_ADMIN SUPPORT SALES FINANCE }
enum ScopeLevel          { PLATFORM INSTITUTION DEPARTMENT CLASS SUBJECT SELF CHILD }
enum PermissionAction    { CREATE READ UPDATE DELETE }
enum PermissionScope     { ALL DEPARTMENT CLASS SUBJECT OWN CHILD }
enum Gender              { MALE FEMALE OTHER }
enum EnrollmentStatus    { ACTIVE TRANSFERRED DROPPED COMPLETED }
enum SubjectType         { THEORY PRACTICAL ELECTIVE PROJECT }
enum AttendanceStatus    { PRESENT ABSENT LATE EXCUSED }
enum LeaveStatus         { PENDING APPROVED REJECTED CANCELLED }
enum ExamType            { MCQ DESCRIPTIVE MIXED QUIZ }
enum ExamMode            { ONLINE OFFLINE }
enum ExamStatus          { DRAFT PUBLISHED ONGOING COMPLETED RESULTS_RELEASED CANCELLED }
enum QuestionType        { MCQ SHORT_ANSWER LONG_ANSWER TRUE_FALSE FILL_BLANK MATCH }
enum DifficultyLevel     { EASY MEDIUM HARD }
enum AttemptStatus       { IN_PROGRESS SUBMITTED GRADED MALPRACTICE }
enum AssignmentType      { REGULAR MILESTONE GROUP }
enum AssignmentStatus    { DRAFT PUBLISHED CLOSED }
enum SubmissionStatus    { SUBMITTED UNDER_REVIEW APPROVED REJECTED RESUBMIT_REQUESTED }
enum NoticeScope         { INSTITUTION DEPARTMENT CLASS HOSTEL TRANSPORT }
enum NoticePriority      { NORMAL IMPORTANT URGENT }
enum ContentType         { PDF VIDEO SLIDE LINK IMAGE AUDIO ZIP }
enum ResultOutcome       { PASS FAIL WITHHELD ABSENT }
enum SlotType            { CLASS BREAK LAB ACTIVITY }
enum BookCondition       { GOOD FAIR DAMAGED LOST }
enum AllotmentStatus     { ACTIVE VACATED TRANSFERRED }
enum ComplaintStatus     { OPEN IN_PROGRESS RESOLVED }
enum DriveStatus         { UPCOMING OPEN ONGOING COMPLETED CANCELLED }
enum ApplicationStatus   { APPLIED SHORTLISTED REJECTED PLACED WITHDRAWN }
enum InterviewResult     { PASS FAIL ON_HOLD ABSENT }
enum OfferStatus         { ISSUED ACCEPTED DECLINED REVOKED }
enum EmploymentType      { FULL_TIME PART_TIME CONTRACT VISITING }
enum PayrollStatus       { DRAFT PROCESSED PAID LOCKED }
enum AppraisalStatus     { PLANNED OPEN CLOSED PENDING SUBMITTED }
enum AdmissionStatus     { SUBMITTED UNDER_REVIEW SHORTLISTED WAITLISTED ADMITTED REJECTED }
enum AdmissionCycleStatus { UPCOMING OPEN CLOSED COMPLETED }
enum FeeStatus           { UNPAID PARTIAL PAID WAIVED }
enum InstallmentStatus   { PENDING PAID OVERDUE WAIVED }
enum PaymentMode         { CASH ONLINE CHEQUE DD UPI }
enum ScholarshipType     { PERCENTAGE FIXED_AMOUNT FULL_WAIVER }
enum StockTxnType        { STOCK_IN STOCK_OUT ADJUSTMENT RETURN }
enum PoStatus            { DRAFT SENT ACKNOWLEDGED DELIVERED CANCELLED }
enum TicketPriority      { LOW MEDIUM HIGH CRITICAL }
enum TicketStatus        { OPEN IN_PROGRESS RESOLVED CLOSED }


// ─────────────────────────────────────────────
// LAYER 1: PLATFORM
// ─────────────────────────────────────────────

model Plan {
  id              String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  name            String   @db.VarChar(100)
  slug            String   @unique @db.VarChar(50)
  maxStudents     Int      @map("max_students")
  maxTeachers     Int      @map("max_teachers")
  maxStorageGb    Int      @default(10) @map("max_storage_gb")
  priceMonthly    Decimal  @db.Decimal(10, 2) @map("price_monthly")
  priceYearly     Decimal  @db.Decimal(10, 2) @map("price_yearly")
  currency        String   @default("INR") @db.VarChar(3)
  allowedModules  String[] @map("allowed_modules")
  isActive        Boolean  @default(true) @map("is_active")
  createdAt       DateTime @default(now()) @map("created_at") @db.Timestamptz
  updatedAt       DateTime @updatedAt @map("updated_at") @db.Timestamptz

  tenants         Tenant[]
  subscriptions   Subscription[]

  @@map("plans")
}

model Tenant {
  id            String     @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  name          String     @db.VarChar(255)
  slug          String     @unique @db.VarChar(100)
  type          TenantType
  planId        String     @map("plan_id") @db.Uuid
  logoUrl       String?    @map("logo_url")
  address       String?
  city          String?    @db.VarChar(100)
  state         String?    @db.VarChar(100)
  country       String     @default("India") @db.VarChar(100)
  pincode       String?    @db.VarChar(20)
  phone         String?    @db.VarChar(20)
  email         String?    @db.VarChar(255)
  website       String?    @db.VarChar(255)
  timezone      String     @default("Asia/Kolkata") @db.VarChar(50)
  isActive      Boolean    @default(true) @map("is_active")
  trialEndsAt   DateTime?  @map("trial_ends_at") @db.Timestamptz
  createdAt     DateTime   @default(now()) @map("created_at") @db.Timestamptz
  updatedAt     DateTime   @updatedAt @map("updated_at") @db.Timestamptz

  plan              Plan               @relation(fields: [planId], references: [id])
  subscriptions     Subscription[]
  settings          TenantSetting[]
  tenantModules     TenantModule[]
  users             User[]
  departments       Department[]
  academicYears     AcademicYear[]
  auditLogs         AuditLog[]
  supportTickets    SupportTicket[]
  feeStructures     FeeStructure[]
  scholarships      Scholarship[]

  @@index([planId], name: "idx_tenants_plan_id")
  @@index([isActive], name: "idx_tenants_is_active")
  @@map("tenants")
}

model TenantSetting {
  id        String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId  String   @map("tenant_id") @db.Uuid
  key       String   @db.VarChar(100)
  value     String
  createdAt DateTime @default(now()) @map("created_at") @db.Timestamptz

  tenant    Tenant   @relation(fields: [tenantId], references: [id], onDelete: Cascade)

  @@unique([tenantId, key], name: "uq_tenant_settings")
  @@map("tenant_settings")
}

model Subscription {
  id                 String             @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId           String             @map("tenant_id") @db.Uuid
  planId             String             @map("plan_id") @db.Uuid
  status             SubscriptionStatus
  startsAt           DateTime           @map("starts_at") @db.Timestamptz
  endsAt             DateTime?          @map("ends_at") @db.Timestamptz
  amount             Decimal            @db.Decimal(10, 2)
  currency           String             @default("INR") @db.VarChar(3)
  paymentReference   String?            @map("payment_reference") @db.VarChar(255)
  createdAt          DateTime           @default(now()) @map("created_at") @db.Timestamptz

  tenant  Tenant @relation(fields: [tenantId], references: [id])
  plan    Plan   @relation(fields: [planId], references: [id])

  @@index([tenantId], name: "idx_subscriptions_tenant_id")
  @@map("subscriptions")
}

model PlatformUser {
  id           String       @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  name         String       @db.VarChar(255)
  email        String       @unique @db.VarChar(255)
  passwordHash String       @map("password_hash")
  platformRole PlatformRole @map("platform_role")
  isActive     Boolean      @default(true) @map("is_active")
  lastLoginAt  DateTime?    @map("last_login_at") @db.Timestamptz
  createdAt    DateTime     @default(now()) @map("created_at") @db.Timestamptz
  updatedAt    DateTime     @updatedAt @map("updated_at") @db.Timestamptz

  assignedTickets SupportTicket[] @relation("AssignedTickets")

  @@map("platform_users")
}

model SupportTicket {
  id           String          @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId     String          @map("tenant_id") @db.Uuid
  raisedBy     String          @map("raised_by") @db.Uuid
  assignedTo   String?         @map("assigned_to") @db.Uuid
  subject      String          @db.VarChar(255)
  description  String
  priority     TicketPriority  @default(MEDIUM)
  status       TicketStatus    @default(OPEN)
  resolvedAt   DateTime?       @map("resolved_at") @db.Timestamptz
  createdAt    DateTime        @default(now()) @map("created_at") @db.Timestamptz
  updatedAt    DateTime        @updatedAt @map("updated_at") @db.Timestamptz

  tenant       Tenant          @relation(fields: [tenantId], references: [id])
  raisedByUser User            @relation("RaisedTickets", fields: [raisedBy], references: [id])
  assignedUser PlatformUser?   @relation("AssignedTickets", fields: [assignedTo], references: [id])

  @@index([tenantId], name: "idx_tickets_tenant_id")
  @@index([status], name: "idx_tickets_status")
  @@map("support_tickets")
}


// ─────────────────────────────────────────────
// LAYER 2: RBAC
// ─────────────────────────────────────────────

model Module {
  id            String         @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  key           String         @unique @db.VarChar(50)
  name          String         @db.VarChar(100)
  description   String?
  isCore        Boolean        @default(false) @map("is_core")
  icon          String?        @db.VarChar(50)
  sortOrder     Int            @default(0) @map("sort_order")

  tenantModules TenantModule[]
  roles         Role[]

  @@map("modules")
}

model TenantModule {
  id          String    @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId    String    @map("tenant_id") @db.Uuid
  moduleKey   String    @map("module_key") @db.VarChar(50)
  isEnabled   Boolean   @default(false) @map("is_enabled")
  enabledAt   DateTime? @map("enabled_at") @db.Timestamptz
  enabledBy   String?   @map("enabled_by") @db.Uuid
  disabledAt  DateTime? @map("disabled_at") @db.Timestamptz
  disabledBy  String?   @map("disabled_by") @db.Uuid

  tenant           Tenant  @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  module           Module  @relation(fields: [moduleKey], references: [key])
  enabledByUser    User?   @relation("EnabledModules", fields: [enabledBy], references: [id])
  disabledByUser   User?   @relation("DisabledModules", fields: [disabledBy], references: [id])

  @@unique([tenantId, moduleKey], name: "uq_tenant_module")
  @@index([tenantId, isEnabled], name: "idx_tm_tenant_enabled")
  @@map("tenant_modules")
}

model Role {
  id          String     @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  name        String     @unique @db.VarChar(100)
  label       String     @db.VarChar(100)
  scopeLevel  ScopeLevel @map("scope_level")
  isPlatform  Boolean    @default(false) @map("is_platform")
  isOptional  Boolean    @default(false) @map("is_optional")
  moduleKey   String?    @map("module_key") @db.VarChar(50)
  description String?

  module      Module?          @relation(fields: [moduleKey], references: [key])
  assignments RoleAssignment[]
  permissions Permission[]

  @@map("roles")
}

model Permission {
  id        String           @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  roleId    String           @map("role_id") @db.Uuid
  moduleKey String           @map("module_key") @db.VarChar(50)
  action    PermissionAction
  scope     PermissionScope

  role      Role @relation(fields: [roleId], references: [id], onDelete: Cascade)

  @@unique([roleId, moduleKey, action], name: "uq_permission")
  @@index([roleId], name: "idx_permissions_role_id")
  @@map("permissions")
}

model User {
  id                   String    @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId             String    @map("tenant_id") @db.Uuid
  name                 String    @db.VarChar(255)
  email                String?   @db.VarChar(255)
  phone                String?   @db.VarChar(20)
  passwordHash         String?   @map("password_hash")
  avatarUrl            String?   @map("avatar_url")
  gender               Gender?
  dateOfBirth          DateTime? @map("date_of_birth") @db.Date
  address              String?
  employeeCode         String?   @map("employee_code") @db.VarChar(50)
  studentRollNo        String?   @map("student_roll_no") @db.VarChar(50)
  isActive             Boolean   @default(true) @map("is_active")
  emailVerifiedAt      DateTime? @map("email_verified_at") @db.Timestamptz
  phoneVerifiedAt      DateTime? @map("phone_verified_at") @db.Timestamptz
  lastLoginAt          DateTime? @map("last_login_at") @db.Timestamptz
  passwordResetToken   String?   @map("password_reset_token") @db.VarChar(255)
  passwordResetExpires DateTime? @map("password_reset_expires") @db.Timestamptz
  createdAt            DateTime  @default(now()) @map("created_at") @db.Timestamptz
  updatedAt            DateTime  @updatedAt @map("updated_at") @db.Timestamptz
  deletedAt            DateTime? @map("deleted_at") @db.Timestamptz

  tenant               Tenant              @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  roleAssignments      RoleAssignment[]
  sessions             UserSession[]
  raisedTickets        SupportTicket[]     @relation("RaisedTickets")
  enabledModules       TenantModule[]      @relation("EnabledModules")
  disabledModules      TenantModule[]      @relation("DisabledModules")
  enrollments          StudentEnrollment[]
  parentLinks          ParentStudentLink[] @relation("ParentLinks")
  childLinks           ParentStudentLink[] @relation("ChildLinks")
  taughtSubjects       TeacherSubject[]    @relation("TaughtSubjects")
  attendanceMarked     AttendanceSession[]
  attendanceRecords    AttendanceRecord[]
  leaveRequests        AttendanceLeave[]   @relation("StudentLeaves")
  examsCreated         Exam[]
  examAttempts         ExamAttempt[]
  assignmentsCreated   Assignment[]
  submissions          Submission[]
  noticesPosted        Notice[]
  discussionThreads    DiscussionThread[]
  discussionReplies    DiscussionReply[]
  contentUploaded      ContentItem[]
  notifications        Notification[]
  deviceTokens         DeviceToken[]
  staffProfile         StaffProfile?
  feePayments          FeePayment[]
  placementApplications PlacementApplication[]

  @@unique([tenantId, email], name: "uq_users_tenant_email")
  @@index([tenantId], name: "idx_users_tenant_id")
  @@index([isActive], name: "idx_users_is_active")
  @@map("users")
}

model RoleAssignment {
  id          String    @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  userId      String    @map("user_id") @db.Uuid
  roleId      String    @map("role_id") @db.Uuid
  tenantId    String    @map("tenant_id") @db.Uuid
  scopeId     String?   @map("scope_id") @db.Uuid
  scopeType   String?   @map("scope_type") @db.VarChar(50)
  assignedBy  String?   @map("assigned_by") @db.Uuid
  assignedAt  DateTime  @default(now()) @map("assigned_at") @db.Timestamptz
  expiresAt   DateTime? @map("expires_at") @db.Timestamptz
  isActive    Boolean   @default(true) @map("is_active")

  user        User @relation(fields: [userId], references: [id], onDelete: Cascade)
  role        Role @relation(fields: [roleId], references: [id])

  @@unique([userId, roleId, tenantId, scopeId], name: "uq_role_assignment")
  @@index([userId], name: "idx_ra_user_id")
  @@index([tenantId, roleId], name: "idx_ra_tenant_role")
  @@map("role_assignments")
}

model UserSession {
  id               String    @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  userId           String    @map("user_id") @db.Uuid
  refreshTokenHash String    @unique @map("refresh_token_hash") @db.VarChar(255)
  deviceInfo       String?   @map("device_info")
  ipAddress        String?   @map("ip_address")
  expiresAt        DateTime  @map("expires_at") @db.Timestamptz
  revokedAt        DateTime? @map("revoked_at") @db.Timestamptz
  createdAt        DateTime  @default(now()) @map("created_at") @db.Timestamptz

  user  User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@index([userId], name: "idx_sessions_user_id")
  @@index([expiresAt], name: "idx_sessions_expires_at")
  @@map("user_sessions")
}


// ─────────────────────────────────────────────
// LAYER 3: INSTITUTION STRUCTURE
// ─────────────────────────────────────────────

model AcademicYear {
  id          String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId    String   @map("tenant_id") @db.Uuid
  name        String   @db.VarChar(50)
  startDate   DateTime @map("start_date") @db.Date
  endDate     DateTime @map("end_date") @db.Date
  isCurrent   Boolean  @default(false) @map("is_current")
  createdAt   DateTime @default(now()) @map("created_at") @db.Timestamptz

  tenant      Tenant              @relation(fields: [tenantId], references: [id])
  classes     Class[]
  enrollments StudentEnrollment[]
  feeStructures FeeStructure[]

  @@unique([tenantId, name], name: "uq_academic_year")
  @@map("academic_years")
}

model Department {
  id          String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId    String   @map("tenant_id") @db.Uuid
  name        String   @db.VarChar(255)
  code        String   @db.VarChar(20)
  hodId       String?  @map("hod_id") @db.Uuid
  description String?
  isActive    Boolean  @default(true) @map("is_active")
  createdAt   DateTime @default(now()) @map("created_at") @db.Timestamptz
  updatedAt   DateTime @updatedAt @map("updated_at") @db.Timestamptz

  tenant      Tenant    @relation(fields: [tenantId], references: [id])
  classes     Class[]
  staffProfiles StaffProfile[]
  placementDriveEligibility Json? // referenced via drive_eligibility

  @@unique([tenantId, code], name: "uq_dept_code")
  @@index([tenantId], name: "idx_departments_tenant_id")
  @@map("departments")
}

model Class {
  id               String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId         String   @map("tenant_id") @db.Uuid
  departmentId     String   @map("department_id") @db.Uuid
  academicYearId   String   @map("academic_year_id") @db.Uuid
  name             String   @db.VarChar(100)
  code             String   @db.VarChar(20)
  maxStrength      Int      @default(60) @map("max_strength")
  classTeacherId   String?  @map("class_teacher_id") @db.Uuid
  roomNo           String?  @map("room_no") @db.VarChar(20)
  isActive         Boolean  @default(true) @map("is_active")
  createdAt        DateTime @default(now()) @map("created_at") @db.Timestamptz

  department       Department          @relation(fields: [departmentId], references: [id])
  academicYear     AcademicYear        @relation(fields: [academicYearId], references: [id])
  subjects         Subject[]
  enrollments      StudentEnrollment[]
  timetableSlots   TimetableSlot[]
  attendanceSessions AttendanceSession[]

  @@unique([tenantId, departmentId, academicYearId, code], name: "uq_class_code")
  @@index([tenantId], name: "idx_classes_tenant_id")
  @@index([departmentId], name: "idx_classes_department_id")
  @@index([academicYearId], name: "idx_classes_academic_year_id")
  @@map("classes")
}

model Subject {
  id            String      @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId      String      @map("tenant_id") @db.Uuid
  classId       String      @map("class_id") @db.Uuid
  name          String      @db.VarChar(255)
  code          String      @db.VarChar(30)
  subjectType   SubjectType @map("subject_type")
  credits       Int?
  maxMarks      Int         @default(100) @map("max_marks")
  passingMarks  Int         @default(35) @map("passing_marks")
  isActive      Boolean     @default(true) @map("is_active")
  createdAt     DateTime    @default(now()) @map("created_at") @db.Timestamptz

  class            Class            @relation(fields: [classId], references: [id])
  teacherSubjects  TeacherSubject[]
  attendanceSessions AttendanceSession[]
  exams            Exam[]
  assignments      Assignment[]
  contentItems     ContentItem[]
  timetableSlots   TimetableSlot[]

  @@unique([tenantId, classId, code], name: "uq_subject_code")
  @@index([classId], name: "idx_subjects_class_id")
  @@map("subjects")
}

model TeacherSubject {
  id            String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId      String   @map("tenant_id") @db.Uuid
  teacherId     String   @map("teacher_id") @db.Uuid
  subjectId     String   @map("subject_id") @db.Uuid
  roleInSubject String   @default("TEACHER") @map("role_in_subject") @db.VarChar(50)
  assignedAt    DateTime @default(now()) @map("assigned_at") @db.Timestamptz
  assignedBy    String?  @map("assigned_by") @db.Uuid

  teacher Subject @relation(fields: [subjectId], references: [id])
  teacherUser User @relation("TaughtSubjects", fields: [teacherId], references: [id])

  @@unique([teacherId, subjectId, roleInSubject], name: "uq_teacher_subject")
  @@index([teacherId], name: "idx_ts_teacher_id")
  @@index([subjectId], name: "idx_ts_subject_id")
  @@map("teacher_subjects")
}

model StudentEnrollment {
  id             String           @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId       String           @map("tenant_id") @db.Uuid
  studentId      String           @map("student_id") @db.Uuid
  classId        String           @map("class_id") @db.Uuid
  academicYearId String           @map("academic_year_id") @db.Uuid
  rollNumber     String?          @map("roll_number") @db.VarChar(50)
  enrollmentDate DateTime         @default(now()) @map("enrollment_date") @db.Date
  status         EnrollmentStatus @default(ACTIVE)
  transferredTo  String?          @map("transferred_to") @db.Uuid
  createdAt      DateTime         @default(now()) @map("created_at") @db.Timestamptz

  student      User         @relation(fields: [studentId], references: [id])
  class        Class        @relation(fields: [classId], references: [id])
  academicYear AcademicYear @relation(fields: [academicYearId], references: [id])

  @@unique([studentId, classId, academicYearId], name: "uq_enrollment")
  @@index([studentId], name: "idx_enrollments_student_id")
  @@index([classId], name: "idx_enrollments_class_id")
  @@map("student_enrollments")
}

model ParentStudentLink {
  id        String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId  String   @map("tenant_id") @db.Uuid
  parentId  String   @map("parent_id") @db.Uuid
  studentId String   @map("student_id") @db.Uuid
  relation  String   @db.VarChar(50)
  isPrimary Boolean  @default(false) @map("is_primary")
  createdAt DateTime @default(now()) @map("created_at") @db.Timestamptz

  parent  User @relation("ParentLinks", fields: [parentId], references: [id])
  student User @relation("ChildLinks", fields: [studentId], references: [id])

  @@unique([parentId, studentId], name: "uq_parent_student")
  @@index([parentId], name: "idx_psl_parent_id")
  @@index([studentId], name: "idx_psl_student_id")
  @@map("parent_student_links")
}


// ─────────────────────────────────────────────
// LAYER 4: CORE MODULES
// ─────────────────────────────────────────────

// --- ATTENDANCE ---

model AttendanceSession {
  id            String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId      String   @map("tenant_id") @db.Uuid
  subjectId     String   @map("subject_id") @db.Uuid
  classId       String   @map("class_id") @db.Uuid
  teacherId     String   @map("teacher_id") @db.Uuid
  academicYearId String  @map("academic_year_id") @db.Uuid
  date          DateTime @db.Date
  periodLabel   String   @map("period_label") @db.VarChar(30)
  startTime     DateTime? @map("start_time") @db.Time
  endTime       DateTime? @map("end_time") @db.Time
  totalPresent  Int      @default(0) @map("total_present")
  totalAbsent   Int      @default(0) @map("total_absent")
  notes         String?
  isLocked      Boolean  @default(false) @map("is_locked")
  lockedAt      DateTime? @map("locked_at") @db.Timestamptz
  createdAt     DateTime @default(now()) @map("created_at") @db.Timestamptz

  subject   Subject            @relation(fields: [subjectId], references: [id])
  class     Class              @relation(fields: [classId], references: [id])
  teacher   User               @relation(fields: [teacherId], references: [id])
  records   AttendanceRecord[]

  @@unique([tenantId, subjectId, classId, date, periodLabel], name: "uq_att_session")
  @@index([classId, date], name: "idx_att_sessions_class_date")
  @@index([teacherId], name: "idx_att_sessions_teacher_id")
  @@map("attendance_sessions")
}

model AttendanceRecord {
  id          String           @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId    String           @map("tenant_id") @db.Uuid
  sessionId   String           @map("session_id") @db.Uuid
  studentId   String           @map("student_id") @db.Uuid
  status      AttendanceStatus
  lateByMinutes Int?           @map("late_by_minutes")
  remarks     String?          @db.VarChar(255)
  markedAt    DateTime         @default(now()) @map("marked_at") @db.Timestamptz
  updatedBy   String?          @map("updated_by") @db.Uuid

  session     AttendanceSession @relation(fields: [sessionId], references: [id], onDelete: Cascade)
  student     User              @relation(fields: [studentId], references: [id])

  @@unique([sessionId, studentId], name: "uq_att_record")
  @@index([sessionId], name: "idx_att_records_session_id")
  @@index([studentId], name: "idx_att_records_student_id")
  @@map("attendance_records")
}

model AttendanceLeave {
  id          String      @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId    String      @map("tenant_id") @db.Uuid
  studentId   String      @map("student_id") @db.Uuid
  classId     String      @map("class_id") @db.Uuid
  fromDate    DateTime    @map("from_date") @db.Date
  toDate      DateTime    @map("to_date") @db.Date
  reason      String
  documentUrl String?     @map("document_url")
  status      LeaveStatus @default(PENDING)
  reviewedBy  String?     @map("reviewed_by") @db.Uuid
  reviewedAt  DateTime?   @map("reviewed_at") @db.Timestamptz
  createdAt   DateTime    @default(now()) @map("created_at") @db.Timestamptz

  student User @relation("StudentLeaves", fields: [studentId], references: [id])

  @@index([studentId], name: "idx_att_leaves_student_id")
  @@map("attendance_leaves")
}

// --- EXAMINATION ---

model Exam {
  id                   String     @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId             String     @map("tenant_id") @db.Uuid
  title                String     @db.VarChar(255)
  subjectId            String     @map("subject_id") @db.Uuid
  classId              String     @map("class_id") @db.Uuid
  academicYearId       String     @map("academic_year_id") @db.Uuid
  examType             ExamType   @map("exam_type")
  mode                 ExamMode   @default(ONLINE)
  totalMarks           Int        @map("total_marks")
  passingMarks         Int        @map("passing_marks")
  durationMinutes      Int        @map("duration_minutes")
  instructions         String?
  scheduledAt          DateTime   @map("scheduled_at") @db.Timestamptz
  windowEndAt          DateTime?  @map("window_end_at") @db.Timestamptz
  resultsReleaseAt     DateTime?  @map("results_release_at") @db.Timestamptz
  status               ExamStatus @default(DRAFT)
  allowReview          Boolean    @default(false) @map("allow_review")
  shuffleQuestions     Boolean    @default(false) @map("shuffle_questions")
  showScoreImmediately Boolean    @default(false) @map("show_score_immediately")
  createdBy            String     @map("created_by") @db.Uuid
  createdAt            DateTime   @default(now()) @map("created_at") @db.Timestamptz
  updatedAt            DateTime   @updatedAt @map("updated_at") @db.Timestamptz

  subject          Subject              @relation(fields: [subjectId], references: [id])
  createdByUser    User                 @relation(fields: [createdBy], references: [id])
  sections         ExamSection[]
  questions        Question[]
  attempts         ExamAttempt[]
  hallAllocations  ExamHallAllocation[]

  @@index([classId, subjectId], name: "idx_exams_class_subject")
  @@index([status, scheduledAt], name: "idx_exams_status_date")
  @@map("exams")
}

model ExamSection {
  id          String @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  examId      String @map("exam_id") @db.Uuid
  title       String @db.VarChar(100)
  description String?
  maxMarks    Int    @map("max_marks")
  sortOrder   Int    @default(0) @map("sort_order")

  exam      Exam       @relation(fields: [examId], references: [id], onDelete: Cascade)
  questions Question[]

  @@index([examId], name: "idx_exam_sections_exam_id")
  @@map("exam_sections")
}

model Question {
  id           String       @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  examId       String       @map("exam_id") @db.Uuid
  sectionId    String?      @map("section_id") @db.Uuid
  text         String
  richText     Json?        @map("rich_text")
  questionType QuestionType @map("question_type")
  marks        Decimal      @db.Decimal(5, 2)
  negativeMarks Decimal     @default(0) @db.Decimal(5, 2) @map("negative_marks")
  imageUrl     String?      @map("image_url")
  explanation  String?
  difficulty   DifficultyLevel?
  sortOrder    Int          @default(0) @map("sort_order")

  exam    Exam           @relation(fields: [examId], references: [id], onDelete: Cascade)
  section ExamSection?   @relation(fields: [sectionId], references: [id])
  options QuestionOption[]
  answers Answer[]

  @@index([examId, sortOrder], name: "idx_questions_exam_order")
  @@map("questions")
}

model QuestionOption {
  id         String  @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  questionId String  @map("question_id") @db.Uuid
  text       String
  imageUrl   String? @map("image_url")
  isCorrect  Boolean @default(false) @map("is_correct")
  sortOrder  Int     @default(0) @map("sort_order")

  question Question @relation(fields: [questionId], references: [id], onDelete: Cascade)
  answers  Answer[]

  @@index([questionId], name: "idx_options_question_id")
  @@map("question_options")
}

model ExamHallAllocation {
  id            String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId      String   @map("tenant_id") @db.Uuid
  examId        String   @map("exam_id") @db.Uuid
  roomNo        String   @map("room_no") @db.VarChar(50)
  invigilatorId String?  @map("invigilator_id") @db.Uuid
  studentIds    String[] @map("student_ids") @db.Uuid
  capacity      Int
  createdAt     DateTime @default(now()) @map("created_at") @db.Timestamptz

  exam Exam @relation(fields: [examId], references: [id])

  @@index([examId], name: "idx_hall_alloc_exam_id")
  @@map("exam_hall_allocations")
}

model ExamAttempt {
  id             String        @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId       String        @map("tenant_id") @db.Uuid
  examId         String        @map("exam_id") @db.Uuid
  studentId      String        @map("student_id") @db.Uuid
  startedAt      DateTime      @map("started_at") @db.Timestamptz
  submittedAt    DateTime?     @map("submitted_at") @db.Timestamptz
  autoSubmitted  Boolean       @default(false) @map("auto_submitted")
  totalScore     Decimal?      @db.Decimal(8, 2) @map("total_score")
  percentage     Decimal?      @db.Decimal(5, 2)
  grade          String?       @db.VarChar(5)
  status         AttemptStatus @default(IN_PROGRESS)
  tabSwitchCount Int           @default(0) @map("tab_switch_count")
  ipAddress      String?       @map("ip_address")
  deviceInfo     String?       @map("device_info")
  createdAt      DateTime      @default(now()) @map("created_at") @db.Timestamptz

  exam            Exam             @relation(fields: [examId], references: [id])
  student         User             @relation(fields: [studentId], references: [id])
  answers         Answer[]
  malpractices    MalpracticeLog[]

  @@unique([examId, studentId], name: "uq_attempt")
  @@index([examId], name: "idx_attempts_exam_id")
  @@index([studentId], name: "idx_attempts_student_id")
  @@index([status], name: "idx_attempts_status")
  @@map("exam_attempts")
}

model Answer {
  id               String    @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  attemptId        String    @map("attempt_id") @db.Uuid
  questionId       String    @map("question_id") @db.Uuid
  selectedOptionId String?   @map("selected_option_id") @db.Uuid
  textAnswer       String?   @map("text_answer")
  matchedPairs     Json?     @map("matched_pairs")
  score            Decimal?  @db.Decimal(5, 2)
  isAutoGraded     Boolean   @default(false) @map("is_auto_graded")
  feedback         String?
  gradedBy         String?   @map("graded_by") @db.Uuid
  gradedAt         DateTime? @map("graded_at") @db.Timestamptz
  answeredAt       DateTime? @map("answered_at") @db.Timestamptz

  attempt        ExamAttempt    @relation(fields: [attemptId], references: [id], onDelete: Cascade)
  question       Question       @relation(fields: [questionId], references: [id])
  selectedOption QuestionOption? @relation(fields: [selectedOptionId], references: [id])

  @@unique([attemptId, questionId], name: "uq_answer")
  @@index([attemptId], name: "idx_answers_attempt_id")
  @@map("answers")
}

model MalpracticeLog {
  id          String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId    String   @map("tenant_id") @db.Uuid
  attemptId   String   @map("attempt_id") @db.Uuid
  studentId   String   @map("student_id") @db.Uuid
  type        String   @db.VarChar(50)
  description String?
  evidenceUrl String?  @map("evidence_url")
  actionTaken String?  @map("action_taken") @db.VarChar(255)
  loggedAt    DateTime @default(now()) @map("logged_at") @db.Timestamptz
  handledBy   String?  @map("handled_by") @db.Uuid

  attempt ExamAttempt @relation(fields: [attemptId], references: [id])

  @@index([attemptId], name: "idx_malpractice_attempt_id")
  @@map("malpractice_logs")
}

// --- ASSIGNMENT ---

model Assignment {
  id                 String           @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId           String           @map("tenant_id") @db.Uuid
  title              String           @db.VarChar(255)
  description        String
  subjectId          String           @map("subject_id") @db.Uuid
  classId            String           @map("class_id") @db.Uuid
  academicYearId     String           @map("academic_year_id") @db.Uuid
  teacherId          String           @map("teacher_id") @db.Uuid
  type               AssignmentType
  totalMarks         Int              @map("total_marks")
  passingMarks       Int              @map("passing_marks")
  dueDate            DateTime         @map("due_date") @db.Timestamptz
  allowLateSubmission Boolean         @default(false) @map("allow_late_submission")
  latePenaltyPercent Int              @default(0) @map("late_penalty_percent")
  maxFileSizeMb      Int              @default(10) @map("max_file_size_mb")
  allowedFileTypes   String[]         @default(["pdf", "doc", "docx", "zip"]) @map("allowed_file_types")
  status             AssignmentStatus @default(DRAFT)
  instructionsUrl    String?          @map("instructions_url")
  createdAt          DateTime         @default(now()) @map("created_at") @db.Timestamptz
  updatedAt          DateTime         @updatedAt @map("updated_at") @db.Timestamptz

  subject     Subject      @relation(fields: [subjectId], references: [id])
  teacher     User         @relation(fields: [teacherId], references: [id])
  milestones  Milestone[]
  submissions Submission[]

  @@index([classId, dueDate], name: "idx_assignments_class_due")
  @@index([teacherId], name: "idx_assignments_teacher_id")
  @@map("assignments")
}

model Milestone {
  id                      String    @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  assignmentId            String    @map("assignment_id") @db.Uuid
  title                   String    @db.VarChar(255)
  description             String?
  sortOrder               Int       @map("sort_order")
  marks                   Int
  dueDate                 DateTime? @map("due_date") @db.Timestamptz
  unlockAfterMilestoneId  String?   @map("unlock_after_milestone_id") @db.Uuid

  assignment     Assignment  @relation(fields: [assignmentId], references: [id], onDelete: Cascade)
  unlockAfter    Milestone?  @relation("MilestoneUnlock", fields: [unlockAfterMilestoneId], references: [id])
  unlockedBy     Milestone[] @relation("MilestoneUnlock")
  submissions    Submission[]

  @@index([assignmentId], name: "idx_milestones_assignment_id")
  @@map("milestones")
}

model Submission {
  id           String           @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId     String           @map("tenant_id") @db.Uuid
  assignmentId String           @map("assignment_id") @db.Uuid
  milestoneId  String?          @map("milestone_id") @db.Uuid
  studentId    String           @map("student_id") @db.Uuid
  textResponse String?          @map("text_response")
  submittedAt  DateTime         @default(now()) @map("submitted_at") @db.Timestamptz
  isLate       Boolean          @default(false) @map("is_late")
  lateByMinutes Int?            @map("late_by_minutes")
  score        Decimal?         @db.Decimal(5, 2)
  grade        String?          @db.VarChar(5)
  feedback     String?
  status       SubmissionStatus @default(SUBMITTED)
  reviewedBy   String?          @map("reviewed_by") @db.Uuid
  reviewedAt   DateTime?        @map("reviewed_at") @db.Timestamptz
  version      Int              @default(1)

  assignment   Assignment       @relation(fields: [assignmentId], references: [id])
  milestone    Milestone?       @relation(fields: [milestoneId], references: [id])
  student      User             @relation(fields: [studentId], references: [id])
  files        SubmissionFile[]

  @@index([assignmentId, studentId], name: "idx_submissions_assignment_student")
  @@index([status], name: "idx_submissions_status")
  @@map("submissions")
}

model SubmissionFile {
  id           String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  submissionId String   @map("submission_id") @db.Uuid
  fileName     String   @map("file_name") @db.VarChar(255)
  fileKey      String   @map("file_key")
  fileSizeBytes BigInt  @map("file_size_bytes")
  mimeType     String   @map("mime_type") @db.VarChar(100)
  uploadedAt   DateTime @default(now()) @map("uploaded_at") @db.Timestamptz

  submission Submission @relation(fields: [submissionId], references: [id], onDelete: Cascade)

  @@map("submission_files")
}

// --- NOTICE BOARD ---

model Notice {
  id          String        @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId    String        @map("tenant_id") @db.Uuid
  title       String        @db.VarChar(255)
  body        String
  authorId    String        @map("author_id") @db.Uuid
  targetScope NoticeScope   @map("target_scope")
  targetId    String?       @map("target_id") @db.Uuid
  priority    NoticePriority @default(NORMAL)
  isPinned    Boolean       @default(false) @map("is_pinned")
  publishedAt DateTime      @default(now()) @map("published_at") @db.Timestamptz
  expiresAt   DateTime?     @map("expires_at") @db.Timestamptz
  createdAt   DateTime      @default(now()) @map("created_at") @db.Timestamptz
  updatedAt   DateTime      @updatedAt @map("updated_at") @db.Timestamptz
  deletedAt   DateTime?     @map("deleted_at") @db.Timestamptz

  author      User               @relation(fields: [authorId], references: [id])
  attachments NoticeAttachment[]
  reads       NoticeRead[]

  @@index([tenantId, targetScope, targetId], name: "idx_notices_scope_target")
  @@index([expiresAt], name: "idx_notices_expiry")
  @@map("notices")
}

model NoticeAttachment {
  id            String @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  noticeId      String @map("notice_id") @db.Uuid
  fileName      String @map("file_name") @db.VarChar(255)
  fileKey       String @map("file_key")
  fileSizeBytes BigInt @map("file_size_bytes")
  mimeType      String @map("mime_type") @db.VarChar(100)

  notice Notice @relation(fields: [noticeId], references: [id], onDelete: Cascade)

  @@map("notice_attachments")
}

model NoticeRead {
  id       String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  noticeId String   @map("notice_id") @db.Uuid
  userId   String   @map("user_id") @db.Uuid
  readAt   DateTime @default(now()) @map("read_at") @db.Timestamptz

  notice Notice @relation(fields: [noticeId], references: [id], onDelete: Cascade)
  user   User   @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([noticeId, userId], name: "uq_notice_read")
  @@map("notice_reads")
}

// --- DISCUSSION ---

model DiscussionThread {
  id         String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId   String   @map("tenant_id") @db.Uuid
  title      String   @db.VarChar(255)
  body       String
  authorId   String   @map("author_id") @db.Uuid
  scopeType  String   @map("scope_type") @db.VarChar(20)
  scopeId    String   @map("scope_id") @db.Uuid
  tags       String[]
  isPinned   Boolean  @default(false) @map("is_pinned")
  isLocked   Boolean  @default(false) @map("is_locked")
  isResolved Boolean  @default(false) @map("is_resolved")
  resolvedBy String?  @map("resolved_by") @db.Uuid
  replyCount Int      @default(0) @map("reply_count")
  upvoteCount Int     @default(0) @map("upvote_count")
  viewCount  Int      @default(0) @map("view_count")
  createdAt  DateTime @default(now()) @map("created_at") @db.Timestamptz
  updatedAt  DateTime @updatedAt @map("updated_at") @db.Timestamptz
  deletedAt  DateTime? @map("deleted_at") @db.Timestamptz

  author  User              @relation(fields: [authorId], references: [id])
  replies DiscussionReply[]
  votes   DiscussionVote[]

  @@index([scopeType, scopeId, createdAt(sort: Desc)], name: "idx_threads_scope")
  @@map("discussion_threads")
}

model DiscussionReply {
  id               String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId         String   @map("tenant_id") @db.Uuid
  threadId         String   @map("thread_id") @db.Uuid
  authorId         String   @map("author_id") @db.Uuid
  body             String
  isAcceptedAnswer Boolean  @default(false) @map("is_accepted_answer")
  upvoteCount      Int      @default(0) @map("upvote_count")
  createdAt        DateTime @default(now()) @map("created_at") @db.Timestamptz
  updatedAt        DateTime @updatedAt @map("updated_at") @db.Timestamptz
  deletedAt        DateTime? @map("deleted_at") @db.Timestamptz

  thread DiscussionThread @relation(fields: [threadId], references: [id], onDelete: Cascade)
  author User             @relation(fields: [authorId], references: [id])

  @@index([threadId, createdAt], name: "idx_replies_thread_id")
  @@map("discussion_replies")
}

model DiscussionVote {
  id         String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  userId     String   @map("user_id") @db.Uuid
  targetType String   @map("target_type") @db.VarChar(10)
  targetId   String   @map("target_id") @db.Uuid
  createdAt  DateTime @default(now()) @map("created_at") @db.Timestamptz

  thread DiscussionThread @relation(fields: [targetId], references: [id], onDelete: Cascade)
  user   User             @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([userId, targetType, targetId], name: "uq_vote")
  @@map("discussion_votes")
}

// --- CONTENT ---

model ContentItem {
  id              String      @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId        String      @map("tenant_id") @db.Uuid
  title           String      @db.VarChar(255)
  description     String?
  subjectId       String      @map("subject_id") @db.Uuid
  classId         String      @map("class_id") @db.Uuid
  uploadedBy      String      @map("uploaded_by") @db.Uuid
  contentType     ContentType @map("content_type")
  fileKey         String?     @map("file_key")
  externalUrl     String?     @map("external_url")
  fileSizeBytes   BigInt?     @map("file_size_bytes")
  durationSeconds Int?        @map("duration_seconds")
  chapter         String?     @db.VarChar(100)
  sortOrder       Int         @default(0) @map("sort_order")
  isVisible       Boolean     @default(true) @map("is_visible")
  downloadCount   Int         @default(0) @map("download_count")
  viewCount       Int         @default(0) @map("view_count")
  createdAt       DateTime    @default(now()) @map("created_at") @db.Timestamptz
  updatedAt       DateTime    @updatedAt @map("updated_at") @db.Timestamptz
  deletedAt       DateTime?   @map("deleted_at") @db.Timestamptz

  subject    Subject            @relation(fields: [subjectId], references: [id])
  uploader   User               @relation(fields: [uploadedBy], references: [id])
  tags       ContentTag[]
  accessLogs ContentAccessLog[]

  @@index([subjectId, classId, isVisible], name: "idx_content_subject_class")
  @@index([chapter], name: "idx_content_chapter")
  @@map("content_items")
}

model ContentTag {
  id        String @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  contentId String @map("content_id") @db.Uuid
  tag       String @db.VarChar(50)

  content ContentItem @relation(fields: [contentId], references: [id], onDelete: Cascade)

  @@unique([contentId, tag], name: "uq_content_tag")
  @@map("content_tags")
}

model ContentAccessLog {
  id        String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  contentId String   @map("content_id") @db.Uuid
  userId    String   @map("user_id") @db.Uuid
  action    String   @db.VarChar(10)
  accessedAt DateTime @default(now()) @map("accessed_at") @db.Timestamptz

  content ContentItem @relation(fields: [contentId], references: [id])
  user    User        @relation(fields: [userId], references: [id])

  @@index([contentId], name: "idx_access_content_id")
  @@map("content_access_logs")
}

// --- RESULTS ---

model ResultPublication {
  id                   String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId             String   @map("tenant_id") @db.Uuid
  title                String   @db.VarChar(255)
  academicYearId       String   @map("academic_year_id") @db.Uuid
  classId              String?  @map("class_id") @db.Uuid
  examIds              String[] @map("exam_ids") @db.Uuid
  publishedBy          String   @map("published_by") @db.Uuid
  publishedAt          DateTime @default(now()) @map("published_at") @db.Timestamptz
  isVisibleToStudents  Boolean  @default(false) @map("is_visible_to_students")

  results     StudentResult[]

  @@map("result_publications")
}

model StudentResult {
  id                   String        @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId             String        @map("tenant_id") @db.Uuid
  publicationId        String        @map("publication_id") @db.Uuid
  studentId            String        @map("student_id") @db.Uuid
  classId              String        @map("class_id") @db.Uuid
  totalMarksObtained   Decimal       @db.Decimal(8, 2) @map("total_marks_obtained")
  totalMarksPossible   Decimal       @db.Decimal(8, 2) @map("total_marks_possible")
  percentage           Decimal       @db.Decimal(5, 2)
  grade                String        @db.VarChar(5)
  rank                 Int?
  result               ResultOutcome
  subjectScores        Json          @map("subject_scores")
  remarks              String?
  createdAt            DateTime      @default(now()) @map("created_at") @db.Timestamptz

  publication ResultPublication @relation(fields: [publicationId], references: [id])
  gradeCards  GradeCard[]

  @@unique([publicationId, studentId], name: "uq_student_result")
  @@index([studentId], name: "idx_results_student_id")
  @@map("student_results")
}

model GradeCard {
  id              String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId        String   @map("tenant_id") @db.Uuid
  studentResultId String   @map("student_result_id") @db.Uuid
  fileKey         String   @map("file_key")
  generatedAt     DateTime @default(now()) @map("generated_at") @db.Timestamptz
  templateVersion String   @default("1.0") @map("template_version") @db.VarChar(20)

  studentResult StudentResult @relation(fields: [studentResultId], references: [id])

  @@map("grade_cards")
}

// --- TIMETABLE ---

model TimetableSlot {
  id             String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId       String   @map("tenant_id") @db.Uuid
  classId        String   @map("class_id") @db.Uuid
  academicYearId String   @map("academic_year_id") @db.Uuid
  dayOfWeek      Int      @map("day_of_week") @db.SmallInt
  periodNumber   Int      @map("period_number") @db.SmallInt
  startTime      DateTime @map("start_time") @db.Time
  endTime        DateTime @map("end_time") @db.Time
  subjectId      String?  @map("subject_id") @db.Uuid
  teacherId      String?  @map("teacher_id") @db.Uuid
  roomNo         String?  @map("room_no") @db.VarChar(20)
  slotType       SlotType @default(CLASS) @map("slot_type")
  effectiveFrom  DateTime @map("effective_from") @db.Date
  effectiveTo    DateTime? @map("effective_to") @db.Date

  class    Class    @relation(fields: [classId], references: [id])
  subject  Subject? @relation(fields: [subjectId], references: [id])
  substitutions TimetableSubstitution[]

  @@unique([classId, dayOfWeek, periodNumber, effectiveFrom], name: "uq_timetable_slot")
  @@index([classId, dayOfWeek], name: "idx_timetable_class_day")
  @@index([teacherId], name: "idx_timetable_teacher_id")
  @@map("timetable_slots")
}

model TimetableSubstitution {
  id                  String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId            String   @map("tenant_id") @db.Uuid
  slotId              String   @map("slot_id") @db.Uuid
  date                DateTime @db.Date
  substituteTeacherId String   @map("substitute_teacher_id") @db.Uuid
  originalTeacherId   String   @map("original_teacher_id") @db.Uuid
  reason              String?
  arrangedBy          String?  @map("arranged_by") @db.Uuid
  createdAt           DateTime @default(now()) @map("created_at") @db.Timestamptz

  slot TimetableSlot @relation(fields: [slotId], references: [id])

  @@unique([slotId, date], name: "uq_substitution")
  @@map("timetable_substitutions")
}


// ─────────────────────────────────────────────
// LAYER 5: OPTIONAL MODULES
// ─────────────────────────────────────────────

// Library, Hostel, Transport, Placement, HR,
// Admission, and Inventory models follow the
// same structural pattern above.
// Full definitions match the table specs in
// Sections 8.1 – 8.7 of this document.
// They are implemented in separate Prisma
// schema files and merged via:
//   prisma generate --schema=prisma/schema.prisma
// See: apps/api/prisma/modules/ for per-module
// schema fragments.


// ─────────────────────────────────────────────
// LAYER 6: PLATFORM ERP (FINANCE)
// ─────────────────────────────────────────────

model FeeStructure {
  id             String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId       String   @map("tenant_id") @db.Uuid
  academicYearId String   @map("academic_year_id") @db.Uuid
  name           String   @db.VarChar(100)
  applicableTo   String[] @map("applicable_to") @db.Uuid
  totalAmount    Decimal  @db.Decimal(12, 2) @map("total_amount")
  isActive       Boolean  @default(true) @map("is_active")
  createdAt      DateTime @default(now()) @map("created_at") @db.Timestamptz

  tenant       Tenant              @relation(fields: [tenantId], references: [id])
  academicYear AcademicYear        @relation(fields: [academicYearId], references: [id])
  feeHeads     FeeHead[]
  feeAccounts  StudentFeeAccount[]

  @@map("fee_structures")
}

model FeeHead {
  id            String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  structureId   String   @map("structure_id") @db.Uuid
  tenantId      String   @map("tenant_id") @db.Uuid
  name          String   @db.VarChar(100)
  amount        Decimal  @db.Decimal(12, 2)
  isRefundable  Boolean  @default(false) @map("is_refundable")
  sortOrder     Int      @default(0) @map("sort_order")

  structure FeeStructure @relation(fields: [structureId], references: [id], onDelete: Cascade)

  @@map("fee_heads")
}

model StudentFeeAccount {
  id                String    @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId          String    @map("tenant_id") @db.Uuid
  studentId         String    @map("student_id") @db.Uuid
  academicYearId    String    @map("academic_year_id") @db.Uuid
  structureId       String    @map("structure_id") @db.Uuid
  totalFee          Decimal   @db.Decimal(12, 2) @map("total_fee")
  concessionAmount  Decimal   @default(0) @db.Decimal(12, 2) @map("concession_amount")
  scholarshipAmount Decimal   @default(0) @db.Decimal(12, 2) @map("scholarship_amount")
  netPayable        Decimal   @db.Decimal(12, 2) @map("net_payable")
  totalPaid         Decimal   @default(0) @db.Decimal(12, 2) @map("total_paid")
  balanceDue        Decimal   @db.Decimal(12, 2) @map("balance_due")
  status            FeeStatus @default(UNPAID)
  createdAt         DateTime  @default(now()) @map("created_at") @db.Timestamptz
  updatedAt         DateTime  @updatedAt @map("updated_at") @db.Timestamptz

  structure     FeeStructure      @relation(fields: [structureId], references: [id])
  installments  FeeInstallment[]
  payments      FeePayment[]
  scholarshipGrants ScholarshipGrant[]

  @@unique([studentId, academicYearId], name: "uq_fee_account")
  @@map("student_fee_accounts")
}

model FeeInstallment {
  id                String             @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  feeAccountId      String             @map("fee_account_id") @db.Uuid
  tenantId          String             @map("tenant_id") @db.Uuid
  installmentNumber Int                @map("installment_number") @db.SmallInt
  label             String             @db.VarChar(50)
  amount            Decimal            @db.Decimal(12, 2)
  dueDate           DateTime           @map("due_date") @db.Date
  paidAmount        Decimal            @default(0) @db.Decimal(12, 2) @map("paid_amount")
  status            InstallmentStatus  @default(PENDING)
  lateFine          Decimal            @default(0) @db.Decimal(8, 2) @map("late_fine")

  feeAccount StudentFeeAccount @relation(fields: [feeAccountId], references: [id])
  payments   FeePayment[]

  @@index([dueDate, status], name: "idx_installments_due_status")
  @@map("fee_installments")
}

model FeePayment {
  id                   String      @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId             String      @map("tenant_id") @db.Uuid
  feeAccountId         String      @map("fee_account_id") @db.Uuid
  installmentId        String?     @map("installment_id") @db.Uuid
  studentId            String      @map("student_id") @db.Uuid
  amount               Decimal     @db.Decimal(12, 2)
  paymentMode          PaymentMode @map("payment_mode")
  transactionReference String?     @map("transaction_reference") @db.VarChar(255)
  paymentDate          DateTime    @map("payment_date") @db.Date
  receiptNumber        String      @map("receipt_number") @db.VarChar(50)
  collectedBy          String      @map("collected_by") @db.Uuid
  notes                String?
  createdAt            DateTime    @default(now()) @map("created_at") @db.Timestamptz

  feeAccount  StudentFeeAccount @relation(fields: [feeAccountId], references: [id])
  installment FeeInstallment?   @relation(fields: [installmentId], references: [id])
  student     User              @relation(fields: [studentId], references: [id])

  @@unique([tenantId, receiptNumber], name: "uq_receipt_number")
  @@index([studentId], name: "idx_fee_payments_student_id")
  @@map("fee_payments")
}

model Scholarship {
  id        String           @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId  String           @map("tenant_id") @db.Uuid
  name      String           @db.VarChar(255)
  type      ScholarshipType
  value     Decimal          @db.Decimal(10, 2)
  criteria  String?
  isActive  Boolean          @default(true) @map("is_active")

  tenant Tenant             @relation(fields: [tenantId], references: [id])
  grants ScholarshipGrant[]

  @@map("scholarships")
}

model ScholarshipGrant {
  id             String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId       String   @map("tenant_id") @db.Uuid
  scholarshipId  String   @map("scholarship_id") @db.Uuid
  studentId      String   @map("student_id") @db.Uuid
  feeAccountId   String   @map("fee_account_id") @db.Uuid
  academicYearId String   @map("academic_year_id") @db.Uuid
  amountGranted  Decimal  @db.Decimal(12, 2) @map("amount_granted")
  grantedBy      String?  @map("granted_by") @db.Uuid
  grantedAt      DateTime @default(now()) @map("granted_at") @db.Timestamptz
  remarks        String?

  scholarship Scholarship       @relation(fields: [scholarshipId], references: [id])
  feeAccount  StudentFeeAccount @relation(fields: [feeAccountId], references: [id])

  @@map("scholarship_grants")
}


// ─────────────────────────────────────────────
// LAYER 7: NOTIFICATIONS & AUDIT
// ─────────────────────────────────────────────

model Notification {
  id        String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId  String?  @map("tenant_id") @db.Uuid
  userId    String   @map("user_id") @db.Uuid
  title     String   @db.VarChar(255)
  body      String
  type      String   @db.VarChar(50)
  data      Json     @default("{}")
  isRead    Boolean  @default(false) @map("is_read")
  readAt    DateTime? @map("read_at") @db.Timestamptz
  createdAt DateTime @default(now()) @map("created_at") @db.Timestamptz

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@index([userId, isRead, createdAt(sort: Desc)], name: "idx_notif_user_unread")
  @@map("notifications")
}

model DeviceToken {
  id           String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  userId       String   @map("user_id") @db.Uuid
  token        String
  platform     String   @db.VarChar(10)
  registeredAt DateTime @default(now()) @map("registered_at") @db.Timestamptz
  lastUsedAt   DateTime? @map("last_used_at") @db.Timestamptz
  isActive     Boolean  @default(true) @map("is_active")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([userId, token], name: "uq_device_token")
  @@map("device_tokens")
}

model AuditLog {
  id        String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  tenantId  String?  @map("tenant_id") @db.Uuid
  userId    String   @map("user_id") @db.Uuid
  userRole  String   @map("user_role") @db.VarChar(100)
  action    String   @db.VarChar(100)
  entity    String   @db.VarChar(100)
  entityId  String?  @map("entity_id") @db.Uuid
  oldValue  Json?    @map("old_value")
  newValue  Json?    @map("new_value")
  ipAddress String?  @map("ip_address")
  userAgent String?  @map("user_agent")
  createdAt DateTime @default(now()) @map("created_at") @db.Timestamptz

  tenant Tenant? @relation(fields: [tenantId], references: [id])

  @@index([tenantId, createdAt(sort: Desc)], name: "idx_audit_tenant_time")
  @@index([entity, entityId], name: "idx_audit_entity_id")
  @@index([userId], name: "idx_audit_user_id")
  @@map("audit_logs")
}
```

---

## 16. Key Query Examples

### 16.1 Get Attendance Percentage for a Student

```sql
SELECT
  s.code AS subject_code,
  s.name AS subject_name,
  COUNT(ar.id) AS total_sessions,
  COUNT(ar.id) FILTER (WHERE ar.status = 'PRESENT') AS present,
  COUNT(ar.id) FILTER (WHERE ar.status = 'ABSENT') AS absent,
  ROUND(
    COUNT(ar.id) FILTER (WHERE ar.status IN ('PRESENT','LATE')) * 100.0
    / NULLIF(COUNT(ar.id), 0), 2
  ) AS attendance_pct
FROM attendance_records ar
JOIN attendance_sessions ase ON ase.id = ar.session_id
JOIN subjects s ON s.id = ase.subject_id
WHERE
  ar.tenant_id = :tenant_id
  AND ar.student_id = :student_id
  AND ase.date BETWEEN :from_date AND :to_date
GROUP BY s.id, s.code, s.name
ORDER BY s.code;
```

---

### 16.2 Auto-Grade an MCQ Exam Attempt

```sql
UPDATE answers a
SET
  score = CASE
    WHEN q.question_type = 'MCQ'
      AND a.selected_option_id IS NOT NULL
      AND (SELECT is_correct FROM question_options WHERE id = a.selected_option_id) = TRUE
    THEN q.marks
    WHEN q.question_type = 'MCQ'
      AND a.selected_option_id IS NOT NULL
      AND (SELECT is_correct FROM question_options WHERE id = a.selected_option_id) = FALSE
    THEN -q.negative_marks
    ELSE 0
  END,
  is_auto_graded = TRUE,
  graded_at = NOW()
FROM questions q
WHERE
  a.question_id = q.id
  AND a.attempt_id = :attempt_id
  AND q.question_type IN ('MCQ', 'TRUE_FALSE');

-- Then update the attempt total
UPDATE exam_attempts
SET
  total_score = (
    SELECT COALESCE(SUM(score), 0) FROM answers WHERE attempt_id = :attempt_id
  ),
  percentage = (
    SELECT COALESCE(SUM(score), 0) * 100.0 / e.total_marks
    FROM answers a2
    JOIN exams e ON e.id = exam_attempts.exam_id
    WHERE a2.attempt_id = :attempt_id
  ),
  status = 'GRADED'
WHERE id = :attempt_id;
```

---

### 16.3 Get Notices for a Specific Student

```sql
SELECT n.*, u.name AS author_name
FROM notices n
JOIN users u ON u.id = n.author_id
WHERE
  n.tenant_id = :tenant_id
  AND n.deleted_at IS NULL
  AND (n.expires_at IS NULL OR n.expires_at >= NOW())
  AND (
    n.target_scope = 'INSTITUTION'
    OR (n.target_scope = 'DEPARTMENT' AND n.target_id = :dept_id)
    OR (n.target_scope = 'CLASS'      AND n.target_id = :class_id)
  )
ORDER BY n.is_pinned DESC, n.published_at DESC
LIMIT 50;
```

---

### 16.4 Check if a Module is Enabled (with Fallback for Core)

```sql
SELECT
  CASE
    WHEN m.is_core = TRUE THEN TRUE
    ELSE COALESCE(tm.is_enabled, FALSE)
  END AS is_active
FROM modules m
LEFT JOIN tenant_modules tm
  ON tm.module_key = m.key AND tm.tenant_id = :tenant_id
WHERE m.key = :module_key;
```

---

### 16.5 Get Class-wise Fee Defaulters

```sql
SELECT
  u.name AS student_name,
  u.student_roll_no,
  c.name AS class_name,
  sfa.net_payable,
  sfa.total_paid,
  sfa.balance_due,
  sfa.status
FROM student_fee_accounts sfa
JOIN users u ON u.id = sfa.student_id
JOIN student_enrollments se
  ON se.student_id = sfa.student_id
  AND se.academic_year_id = sfa.academic_year_id
JOIN classes c ON c.id = se.class_id
WHERE
  sfa.tenant_id = :tenant_id
  AND sfa.academic_year_id = :academic_year_id
  AND sfa.status IN ('UNPAID', 'PARTIAL')
  AND sfa.balance_due > 0
ORDER BY c.name, sfa.balance_due DESC;
```

---

### 16.6 Get Student's Next Unlocked Milestone

```sql
SELECT m.*
FROM milestones m
WHERE
  m.assignment_id = :assignment_id
  AND (
    m.unlock_after_milestone_id IS NULL
    OR EXISTS (
      SELECT 1 FROM submissions s
      WHERE
        s.milestone_id = m.unlock_after_milestone_id
        AND s.student_id = :student_id
        AND s.status = 'APPROVED'
    )
  )
  AND NOT EXISTS (
    SELECT 1 FROM submissions s2
    WHERE
      s2.milestone_id = m.id
      AND s2.student_id = :student_id
      AND s2.status NOT IN ('REJECTED', 'RESUBMIT_REQUESTED')
  )
ORDER BY m.sort_order
LIMIT 1;
```

---

## 17. Data Retention & Archival Policy

| Data Type | Retention Period | Action After |
|---|---|---|
| Academic records (attendance, results) | 10 years | Archive to cold storage (S3 Glacier) |
| Exam attempts & answers | 5 years | Archive |
| Audit logs | 7 years | Partition + archive |
| Notifications | 6 months | Purge (soft delete → hard delete) |
| Session tokens | 7 days | Auto-expire via Redis TTL |
| Content files | Until manually deleted | S3 versioning enabled |
| Deleted users | 30 days after soft-delete | Anonymize personal data |
| Support tickets | 3 years | Archive |

**Academic Year Archival:**  
When a new academic year is activated (`is_current = TRUE`), previous year data moves to read-only mode. Queries against past years use a dedicated `?year={id}` filter on all APIs.

---

## 18. Database Migration Order (First Deployment)

Run migrations in this exact order to respect foreign key dependencies:

```
1.  plans
2.  platform_users
3.  tenants
4.  tenant_settings
5.  subscriptions
6.  modules
7.  roles
8.  permissions
9.  users
10. tenant_modules
11. role_assignments
12. user_sessions
13. academic_years
14. departments
15. classes
16. subjects
17. teacher_subjects
18. student_enrollments
19. parent_student_links
20. attendance_sessions
21. attendance_records
22. attendance_leaves
23. exams
24. exam_sections
25. questions
26. question_options
27. exam_hall_allocations
28. exam_attempts
29. answers
30. malpractice_logs
31. assignments
32. milestones
33. submissions
34. submission_files
35. notices
36. notice_attachments
37. notice_reads
38. discussion_threads
39. discussion_replies
40. discussion_votes
41. content_items
42. content_tags
43. content_access_logs
44. result_publications
45. student_results
46. grade_cards
47. timetable_slots
48. timetable_substitutions
49. fee_structures
50. fee_heads
51. student_fee_accounts
52. fee_installments
53. fee_payments
54. scholarships
55. scholarship_grants
56. support_tickets
    [Optional modules: 57-97]
57. books
58. book_copies
59. book_issues
60. e_resources
61. hostel_blocks
62. hostel_rooms
63. hostel_allotments
64. hostel_attendance
65. hostel_leave_requests
66. hostel_complaints
67. transport_routes
68. transport_stops
69. vehicles
70. drivers
71. student_transport
72. companies
73. placement_drives
74. drive_eligibility
75. placement_applications
76. interview_rounds
77. placement_offers
78. staff_profiles
79. leave_policies
80. leave_requests
81. salary_structures
82. payroll_runs
83. payslips
84. appraisal_cycles
85. appraisals
86. staff_documents
87. admission_cycles
88. admission_applications
89. application_documents
90. merit_lists
91. inventory_categories
92. inventory_items
93. stock_transactions
94. vendors
95. purchase_orders
96. purchase_order_items
    [System tables last]
97. notifications
98. device_tokens
99. audit_logs
```

---

*Document version: 2.0 | 100 tables · 15 modules · 22 roles · PostgreSQL 15 · Prisma ORM*  
*Companion: Role-Based System Design v1.0 · Developer Deployment Guide v1.0*
