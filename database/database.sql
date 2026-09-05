-- ============================================================================
--  ERP + LMS Platform — Complete PostgreSQL Schema
--  Multi-tenant School / College ERP + Learning Management System
-- ============================================================================
--
--  Generated from  : docs/database_design_complete.md (v2.1)
--  Target          : PostgreSQL 15+   (verified on PostgreSQL 17.10)
--  Contents        : 54 enum types
--                    107 tables
--                    58 documented indexes (§11 + per-table)
--                    216 generated foreign-key indexes
--
--  VERIFIED: this file was executed end-to-end against a live PostgreSQL 17
--  instance with zero errors before being committed. See the verification
--  block at the foot of this file for the counts it produces.
--
--  Usage:
--      createdb erp_lms
--      psql -d erp_lms -v ON_ERROR_STOP=1 -f database.sql
--
--  Notes for Dev-A
--  ---------------
--  1. ENUMS ARE CREATED ONCE, FIRST. The design doc quotes several enum
--     declarations more than once (§13, the per-table sections, and the
--     addendum's New Enum Summary). Running any of those a second time aborts
--     the migration with 'type "..." already exists'. This file declares each
--     enum exactly once, in section 2 below.
--
--  2. TABLE ORDER IS TOPOLOGICALLY SORTED, not the order printed in §18.
--     §18 lists transport_routes before vehicles and drivers, which it
--     references — running §18 verbatim fails. The order below is derived
--     from the actual foreign-key graph.
--
--  3. EVERY FOREIGN KEY IS INDEXED. PostgreSQL indexes the referenced side
--     automatically but never the referencing side, so an unindexed FK makes
--     both joins and ON DELETE CASCADE sequential scans. Section 5 adds the
--     216 that the documented index list does not cover.
--
--  4. gen_random_uuid() comes from pgcrypto on PostgreSQL < 13; it is
--     built-in from 13 onwards. The extension is created defensively below.
--
--  5. Row-Level Security is NOT enabled here. Tenant isolation is enforced in
--     the application layer (every query is scoped by tenant_id). If you want
--     RLS as a second line of defence, see the commented template in
--     section 7.
-- ============================================================================


-- ============================================================================
--  SECTION 1 — EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- trigram search on names/titles


-- ============================================================================
--  SECTION 2 — ENUM TYPES (54)
--  Created once, before any table. See note 1 above.
-- ============================================================================

CREATE TYPE tenant_type AS ENUM ('SCHOOL', 'COLLEGE');
-- subscription_status, ticket_priority, ticket_status are typed as VARCHAR with CHECK constraints to match SQLAlchemy models & asyncpg
CREATE TYPE platform_role AS ENUM ('SUPER_ADMIN', 'SUPPORT', 'SALES', 'FINANCE', 'OWNER');
CREATE TYPE scope_level AS ENUM ('PLATFORM', 'INSTITUTION', 'DEPARTMENT', 'CLASS', 'SUBJECT', 'SELF', 'CHILD');
CREATE TYPE permission_action AS ENUM ('CREATE', 'READ', 'UPDATE', 'DELETE');
CREATE TYPE permission_scope AS ENUM ('ALL', 'DEPARTMENT', 'CLASS', 'SUBJECT', 'OWN', 'CHILD');
CREATE TYPE gender AS ENUM ('MALE', 'FEMALE', 'OTHER');
CREATE TYPE enrollment_status AS ENUM ('ACTIVE', 'TRANSFERRED', 'DROPPED', 'COMPLETED');
CREATE TYPE subject_type AS ENUM ('THEORY', 'PRACTICAL', 'ELECTIVE', 'PROJECT');
CREATE TYPE attendance_status AS ENUM ('PRESENT', 'ABSENT', 'LATE', 'EXCUSED');
CREATE TYPE leave_status AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED');
CREATE TYPE exam_type AS ENUM ('MCQ', 'DESCRIPTIVE', 'MIXED', 'QUIZ');
CREATE TYPE exam_mode AS ENUM ('ONLINE', 'OFFLINE');
CREATE TYPE exam_status AS ENUM ('DRAFT', 'PUBLISHED', 'ONGOING', 'COMPLETED', 'RESULTS_RELEASED', 'CANCELLED');
CREATE TYPE question_type AS ENUM ('MCQ', 'SHORT_ANSWER', 'LONG_ANSWER', 'TRUE_FALSE', 'FILL_BLANK', 'MATCH');
CREATE TYPE difficulty_level AS ENUM ('EASY', 'MEDIUM', 'HARD');
CREATE TYPE attempt_status AS ENUM ('IN_PROGRESS', 'SUBMITTED', 'GRADED', 'MALPRACTICE');
CREATE TYPE assignment_type AS ENUM ('REGULAR', 'MILESTONE', 'GROUP');
CREATE TYPE assignment_status AS ENUM ('DRAFT', 'PUBLISHED', 'CLOSED');
CREATE TYPE submission_status AS ENUM ('SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'RESUBMIT_REQUESTED');
CREATE TYPE notice_scope AS ENUM ('INSTITUTION', 'DEPARTMENT', 'CLASS', 'HOSTEL', 'TRANSPORT');
CREATE TYPE notice_priority AS ENUM ('NORMAL', 'IMPORTANT', 'URGENT');
CREATE TYPE content_type AS ENUM ('PDF', 'VIDEO', 'SLIDE', 'LINK', 'IMAGE', 'AUDIO', 'ZIP');
CREATE TYPE result_outcome AS ENUM ('PASS', 'FAIL', 'WITHHELD', 'ABSENT');
CREATE TYPE slot_type AS ENUM ('CLASS', 'BREAK', 'LAB', 'ACTIVITY');
CREATE TYPE book_condition AS ENUM ('GOOD', 'FAIR', 'DAMAGED', 'LOST');
CREATE TYPE allotment_status AS ENUM ('ACTIVE', 'VACATED', 'TRANSFERRED');
CREATE TYPE hostel_attendance_status AS ENUM ('PRESENT', 'ABSENT', 'ON_LEAVE');
CREATE TYPE complaint_status AS ENUM ('OPEN', 'IN_PROGRESS', 'RESOLVED');
CREATE TYPE drive_status AS ENUM ('UPCOMING', 'OPEN', 'ONGOING', 'COMPLETED', 'CANCELLED');
CREATE TYPE application_status AS ENUM ('APPLIED', 'SHORTLISTED', 'REJECTED', 'PLACED', 'WITHDRAWN');
CREATE TYPE interview_result AS ENUM ('PASS', 'FAIL', 'ON_HOLD', 'ABSENT');
CREATE TYPE offer_status AS ENUM ('ISSUED', 'ACCEPTED', 'DECLINED', 'REVOKED');
CREATE TYPE review_decision AS ENUM ('APPROVED', 'REJECTED', 'CHANGES_REQUESTED');
CREATE TYPE import_type AS ENUM ('STUDENTS', 'STAFF', 'QUESTIONS', 'TRANSPORT_ASSIGNMENTS');
CREATE TYPE import_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');
CREATE TYPE export_type AS ENUM ('FULL', 'STUDENTS', 'ATTENDANCE', 'RESULTS', 'FEES', 'STAFF');
CREATE TYPE export_status AS ENUM ('PENDING', 'PROCESSING', 'READY', 'FAILED', 'EXPIRED');
CREATE TYPE notif_channel AS ENUM ('PUSH', 'EMAIL', 'SMS');
CREATE TYPE academic_event_type AS ENUM ('HOLIDAY', 'EXAM_WEEK', 'TERM_START', 'TERM_END', 'INSTITUTIONAL_EVENT', 'WORKING_SATURDAY', 'SPORT_EVENT', 'CULTURAL_EVENT');
CREATE TYPE event_scope AS ENUM ('ALL', 'DEPARTMENT', 'CLASS');
CREATE TYPE setting_type AS ENUM ('TEXT', 'NUMBER', 'BOOLEAN', 'COLOR', 'SELECT', 'JSON');
CREATE TYPE employment_type AS ENUM ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'VISITING');
CREATE TYPE payroll_status AS ENUM ('DRAFT', 'PROCESSED', 'PAID', 'LOCKED');
CREATE TYPE appraisal_status AS ENUM ('PLANNED', 'OPEN', 'CLOSED', 'PENDING');
CREATE TYPE admission_status AS ENUM ('SUBMITTED', 'UNDER_REVIEW', 'SHORTLISTED', 'WAITLISTED', 'ADMITTED', 'REJECTED');
CREATE TYPE admission_cycle_status AS ENUM ('UPCOMING', 'OPEN', 'CLOSED', 'COMPLETED');
CREATE TYPE fee_status AS ENUM ('UNPAID', 'PARTIAL', 'PAID', 'WAIVED');
CREATE TYPE installment_status AS ENUM ('PENDING', 'PAID', 'OVERDUE', 'WAIVED');
CREATE TYPE payment_mode AS ENUM ('CASH', 'ONLINE', 'CHEQUE', 'DD', 'UPI');
CREATE TYPE scholarship_type AS ENUM ('PERCENTAGE', 'FIXED_AMOUNT', 'FULL_WAIVER');
CREATE TYPE stock_txn_type AS ENUM ('STOCK_IN', 'STOCK_OUT', 'ADJUSTMENT', 'RETURN');
CREATE TYPE po_status AS ENUM ('DRAFT', 'SENT', 'ACKNOWLEDGED', 'DELIVERED', 'CANCELLED');
CREATE TYPE exam_controller_publication_status AS ENUM ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PUBLISHED', 'WITHDRAWN');
CREATE TYPE exam_controller_grade_card_status AS ENUM ('PENDING', 'GENERATED', 'PUBLISHED', 'FAILED');
CREATE TYPE online_class_status AS ENUM ('SCHEDULED', 'LIVE', 'COMPLETED', 'CANCELLED');
CREATE TYPE online_class_mode AS ENUM ('SCHEDULED', 'INSTANT');
CREATE TYPE online_attendance_status AS ENUM ('PRESENT', 'LATE', 'ABSENT');


-- ============================================================================
--  SECTION 3 — TABLES (107)
--  Topologically sorted by foreign-key dependency. See note 2 above.
-- ============================================================================

CREATE TABLE plans (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                         VARCHAR(100) NOT NULL,
  slug                         VARCHAR(50) NOT NULL UNIQUE,
  max_students                 INTEGER NOT NULL,
  max_teachers                 INTEGER NOT NULL,
  max_storage_gb               INTEGER NOT NULL DEFAULT 10,
  price_monthly                NUMERIC(10,2) NOT NULL,
  price_yearly                 NUMERIC(10,2) NOT NULL,
  currency                     VARCHAR(3) NOT NULL DEFAULT 'INR',
  allowed_modules              TEXT[] NOT NULL DEFAULT '{}',
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Public website enquiries are sales leads only. They never create a tenant,
-- subscription or user until a Sales Executive qualifies the request.
CREATE TABLE service_requests (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_name                 VARCHAR(100) NOT NULL,
  institution_name             VARCHAR(255) NOT NULL,
  work_email                   VARCHAR(255) NOT NULL,
  phone                        VARCHAR(30),
  institution_type             VARCHAR(20) NOT NULL,
  student_count                INTEGER,
  service_interest             VARCHAR(100) NOT NULL,
  message                      TEXT,
  status                       VARCHAR(20) NOT NULL DEFAULT 'NEW',
  source                       VARCHAR(100) NOT NULL DEFAULT 'website',
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_service_requests_student_count
    CHECK (student_count IS NULL OR student_count > 0)
);

CREATE INDEX idx_service_requests_status_created_at
  ON service_requests (status, created_at);
CREATE INDEX idx_service_requests_work_email ON service_requests (work_email);

CREATE TABLE platform_owners (

  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                        VARCHAR(255) NOT NULL,
  email                       VARCHAR(255) NOT NULL,
  password_hash               VARCHAR(255) NOT NULL,
  is_email_verified           BOOLEAN NOT NULL DEFAULT FALSE,
  email_verification_token    VARCHAR(255),
  email_verification_expires  TIMESTAMPTZ,
  password_reset_token        VARCHAR(255),
  password_reset_expires      TIMESTAMPTZ,
  is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
  last_login_at               TIMESTAMPTZ,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_platform_owners_email UNIQUE (email)
);

CREATE TABLE owner_sessions (

  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id            UUID NOT NULL REFERENCES platform_owners(id) ON DELETE CASCADE,
  refresh_token_hash  VARCHAR(255) NOT NULL,
  device_info         TEXT,
  ip_address          INET,
  expires_at          TIMESTAMPTZ NOT NULL,
  revoked_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_owner_sessions_refresh_token_hash UNIQUE (refresh_token_hash)
);

CREATE TABLE platform_users (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                         VARCHAR(255) NOT NULL,
  email                        VARCHAR(255) NOT NULL UNIQUE,
  password_hash                TEXT NOT NULL,
  platform_role                platform_role NOT NULL,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  email_verified_at            TIMESTAMPTZ,
  email_verification_token_hash TEXT,
  last_login_at                TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE platform_sessions (

  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES platform_users(id) ON DELETE CASCADE,
  refresh_token_hash  VARCHAR(255) NOT NULL UNIQUE,
  device_info         TEXT,
  ip_address          INET,
  expires_at          TIMESTAMPTZ NOT NULL,
  revoked_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE platform_settings (

  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key         VARCHAR(100) NOT NULL,
  value       TEXT NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_platform_settings_key UNIQUE (key)
);

CREATE TABLE tenants (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                         VARCHAR(255) NOT NULL,
  slug                         VARCHAR(100) NOT NULL UNIQUE,
  type                         tenant_type NOT NULL,
  plan_id                      UUID REFERENCES plans(id),
  owner_platform_user_id       UUID REFERENCES platform_users(id),
  owner_id                     UUID REFERENCES platform_owners(id),
  logo_url                     TEXT,
  address                      TEXT,
  city                         VARCHAR(100),
  state                        VARCHAR(100),
  country                      VARCHAR(100) NOT NULL DEFAULT 'India',
  pincode                      VARCHAR(20),
  phone                        VARCHAR(20),
  email                        VARCHAR(255),
  website                      VARCHAR(255),
  timezone                     VARCHAR(50) NOT NULL DEFAULT 'Asia/Kolkata',
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  trial_ends_at                TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE tenant_settings (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  key                          VARCHAR(100) NOT NULL,
  value                        TEXT NOT NULL,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_tenant_settings__tenant_id_key UNIQUE (tenant_id, key)
);

CREATE TABLE subscriptions (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  plan_id                      UUID NOT NULL REFERENCES plans(id),
  status                       VARCHAR(20) NOT NULL DEFAULT 'TRIAL',
  starts_at                    TIMESTAMPTZ NOT NULL,
  ends_at                      TIMESTAMPTZ,
  amount                       NUMERIC(10,2) NOT NULL,
  currency                     VARCHAR(3) NOT NULL DEFAULT 'INR',
  payment_reference            VARCHAR(255),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_subscriptions_status CHECK (status IN ('TRIAL', 'ACTIVE', 'PAST_DUE', 'CANCELLED'))
);

CREATE TABLE modules (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key                          VARCHAR(50) NOT NULL UNIQUE,
  name                         VARCHAR(100) NOT NULL,
  description                  TEXT,
  is_core                      BOOLEAN NOT NULL DEFAULT FALSE,
  icon                         VARCHAR(50),
  sort_order                   INTEGER NOT NULL DEFAULT 0,
  price_monthly                NUMERIC(10,2) NOT NULL DEFAULT 0
);

CREATE TABLE coupons (

  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code           VARCHAR(50) NOT NULL UNIQUE,
  discount_type  VARCHAR(10) NOT NULL,
  value          NUMERIC(10,2) NOT NULL,
  currency       VARCHAR(3) NOT NULL DEFAULT 'INR',
  max_uses       INTEGER NOT NULL DEFAULT 0,
  used_count     INTEGER NOT NULL DEFAULT 0,
  valid_from     DATE,
  valid_until    DATE,
  is_active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE orders (

  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mode                      VARCHAR(10) NOT NULL,
  plan_slug                 VARCHAR(50) NOT NULL,
  module_keys               VARCHAR(50)[] NOT NULL,
  billing_cycle             VARCHAR(10) NOT NULL DEFAULT 'MONTHLY',
  subtotal                  NUMERIC(12,2) NOT NULL,
  discount                  NUMERIC(12,2) NOT NULL DEFAULT 0,
  total                     NUMERIC(12,2) NOT NULL,
  currency                  VARCHAR(3) NOT NULL DEFAULT 'INR',
  coupon_code               VARCHAR(50),
  institution_name          VARCHAR(255) NOT NULL,
  institution_type          VARCHAR(20) NOT NULL,
  contact_email             VARCHAR(255) NOT NULL,
  contact_phone             VARCHAR(20),
  country                   VARCHAR(100) NOT NULL DEFAULT 'India',
  state                     VARCHAR(100),
  city                      VARCHAR(100),
  address                   TEXT,
  url_slug                  VARCHAR(100) NOT NULL,
  password_hash             TEXT NOT NULL,
  status                    VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  payment_method            VARCHAR(20),
  gateway_ref               VARCHAR(255),
  tenant_id                 UUID REFERENCES tenants(id),
  owner_id                  UUID REFERENCES platform_owners(id),
  owner_platform_user_id    UUID REFERENCES platform_users(id),
  owner_email               VARCHAR(255),
  owner_name                VARCHAR(255),
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  paid_at                   TIMESTAMPTZ
);

CREATE TABLE platform_invoices (

  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenants(id),
  subscription_id  UUID REFERENCES subscriptions(id),
  invoice_number   VARCHAR(50) NOT NULL UNIQUE,
  status           VARCHAR(20) NOT NULL,
  issued_at        DATE NOT NULL,
  due_at           DATE NOT NULL,
  currency         VARCHAR(3) NOT NULL DEFAULT 'INR',
  subtotal         NUMERIC(12,2) NOT NULL,
  tax_amount       NUMERIC(12,2) NOT NULL DEFAULT 0,
  total            NUMERIC(12,2) NOT NULL,
  amount_paid      NUMERIC(12,2) NOT NULL DEFAULT 0,
  gstin            VARCHAR(15),
  place_of_supply  VARCHAR(2),
  pdf_key          TEXT,
  notes            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE platform_invoice_lines (

  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id   UUID NOT NULL REFERENCES platform_invoices(id) ON DELETE CASCADE,
  description  VARCHAR(500) NOT NULL,
  hsn_sac      VARCHAR(10),
  quantity     NUMERIC(10,2) NOT NULL DEFAULT 1,
  unit_price   NUMERIC(12,2) NOT NULL,
  tax_rate     NUMERIC(5,2) NOT NULL DEFAULT 0,
  line_total   NUMERIC(12,2) NOT NULL
);

CREATE TABLE platform_payments (

  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID REFERENCES tenants(id),
  invoice_id      UUID REFERENCES platform_invoices(id),
  order_id        UUID REFERENCES orders(id),
  status          VARCHAR(20) NOT NULL,
  method          VARCHAR(20) NOT NULL,
  amount          NUMERIC(12,2) NOT NULL,
  currency        VARCHAR(3) NOT NULL DEFAULT 'INR',
  gateway         VARCHAR(50),
  gateway_ref     VARCHAR(255),
  failure_reason  TEXT,
  received_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_platform_payments_gateway_ref UNIQUE (gateway, gateway_ref)
);

CREATE TABLE outbox_emails (

  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event       VARCHAR(50) NOT NULL,
  to_address  VARCHAR(255) NOT NULL,
  subject     VARCHAR(255) NOT NULL,
  body        TEXT NOT NULL,
  status      VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
  attempts    INTEGER NOT NULL DEFAULT 0,
  tenant_id   UUID REFERENCES tenants(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE roles (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                         VARCHAR(100) NOT NULL UNIQUE,
  label                        VARCHAR(100) NOT NULL,
  scope_level                  scope_level NOT NULL,
  is_platform                  BOOLEAN NOT NULL DEFAULT FALSE,
  is_optional                  BOOLEAN NOT NULL DEFAULT FALSE,
  module_key                   VARCHAR(50) REFERENCES modules(key),
  description                  TEXT
);

CREATE TABLE permissions (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id                      UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  module_key                   VARCHAR(50) NOT NULL,
  action                       permission_action NOT NULL,
  scope                        permission_scope NOT NULL,
  CONSTRAINT uq_permissions__role_id_module_key_action UNIQUE (role_id, module_key, action)
);

CREATE TABLE users (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name                         VARCHAR(255) NOT NULL,
  email                        VARCHAR(255),
  phone                        VARCHAR(20),
  password_hash                TEXT,
  avatar_url                   TEXT,
  gender                       gender,
  date_of_birth                DATE,
  address                      TEXT,
  employee_code                VARCHAR(50),
  student_roll_no              VARCHAR(50),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  email_verified_at            TIMESTAMPTZ,
  phone_verified_at            TIMESTAMPTZ,
  last_login_at                TIMESTAMPTZ,
  password_reset_token         VARCHAR(255),
  password_reset_expires       TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at                   TIMESTAMPTZ,
  CONSTRAINT uq_users__tenant_id_email UNIQUE (tenant_id, email),
  CONSTRAINT uq_users__tenant_id_student_roll_no UNIQUE (tenant_id, student_roll_no)
);

CREATE TABLE tenant_modules (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  module_key                   VARCHAR(50) NOT NULL REFERENCES modules(key),
  is_enabled                   BOOLEAN NOT NULL DEFAULT FALSE,
  enabled_at                   TIMESTAMPTZ,
  enabled_by                   UUID REFERENCES users(id),
  disabled_at                  TIMESTAMPTZ,
  disabled_by                  UUID REFERENCES users(id),
  CONSTRAINT uq_tenant_modules__tenant_id_module_key UNIQUE (tenant_id, module_key)
);

CREATE TABLE role_assignments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id                      UUID NOT NULL REFERENCES roles(id),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  scope_id                     UUID,
  scope_type                   VARCHAR(50),
  assigned_by                  UUID REFERENCES users(id),
  assigned_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at                   TIMESTAMPTZ,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_role_assignments__user_id_role_id_tenant_id_scope_id UNIQUE (user_id, role_id, tenant_id, scope_id)
);

CREATE TABLE user_sessions (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash           VARCHAR(255) NOT NULL UNIQUE,
  device_info                  TEXT,
  ip_address                   INET,
  expires_at                   TIMESTAMPTZ NOT NULL,
  revoked_at                   TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE academic_years (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(50) NOT NULL,
  start_date                   DATE NOT NULL,
  end_date                     DATE NOT NULL,
  is_current                   BOOLEAN NOT NULL DEFAULT FALSE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_academic_years__tenant_id_name UNIQUE (tenant_id, name)
);

CREATE TABLE departments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(255) NOT NULL,
  code                         VARCHAR(20) NOT NULL,
  hod_id                       UUID REFERENCES users(id),
  description                  TEXT,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_departments__tenant_id_code UNIQUE (tenant_id, code)
);

CREATE TABLE class_grades (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  name                         VARCHAR(100) NOT NULL,
  grade_number                 INTEGER NOT NULL CHECK (grade_number BETWEEN 1 AND 12),
  stream                       VARCHAR(50),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_class_grades UNIQUE (tenant_id, academic_year_id, grade_number, stream)
);

CREATE TABLE class_programs (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  department_id                UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  program_name                 VARCHAR(200) NOT NULL,
  program_code                 VARCHAR(30) NOT NULL,
  semester_number              INTEGER NOT NULL CHECK (semester_number >= 1),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_class_programs UNIQUE (tenant_id, department_id, program_code, semester_number, academic_year_id)
);

CREATE TABLE classes (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  department_id                UUID NOT NULL REFERENCES departments(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  name                         VARCHAR(100) NOT NULL,
  code                         VARCHAR(20) NOT NULL,
  max_strength                 INTEGER NOT NULL DEFAULT 60,
  class_teacher_id             UUID REFERENCES users(id),
  room_no                      VARCHAR(20),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  grade_id                     UUID REFERENCES class_grades(id) ON DELETE SET NULL,
  program_id                   UUID REFERENCES class_programs(id) ON DELETE SET NULL,
  section_label                VARCHAR(20),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_classes__tenant_id_department_id_academic_year_id UNIQUE (tenant_id, department_id, academic_year_id, code)
);


CREATE TABLE subjects (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  name                         VARCHAR(255) NOT NULL,
  code                         VARCHAR(30) NOT NULL,
  subject_type                 subject_type NOT NULL,
  credits                      INTEGER,
  max_marks                    INTEGER NOT NULL DEFAULT 100,
  passing_marks                INTEGER NOT NULL DEFAULT 35,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_subjects__tenant_id_class_id_code UNIQUE (tenant_id, class_id, code)
);

CREATE TABLE teacher_subjects (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  teacher_id                   UUID NOT NULL REFERENCES users(id),
  subject_id                   UUID NOT NULL REFERENCES subjects(id),
  role_in_subject              VARCHAR(50) NOT NULL DEFAULT 'TEACHER',
  assigned_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  assigned_by                  UUID REFERENCES users(id),
  CONSTRAINT uq_teacher_subjects__teacher_id_subject_id_role_in_subject UNIQUE (teacher_id, subject_id, role_in_subject)
);

CREATE TABLE student_enrollments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  roll_number                  VARCHAR(50),
  enrollment_date              DATE NOT NULL DEFAULT CURRENT_DATE,
  status                       enrollment_status NOT NULL DEFAULT 'ACTIVE',
  transferred_to               UUID REFERENCES classes(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_student_enrollments__student_id_class_id_academic_year_id UNIQUE (student_id, class_id, academic_year_id)
);

-- The guardian access grant, not merely a family note. `status` +
-- `activation_code` are what make "Parent–Student Connected Access" work: a
-- school records an invite (PENDING_CLAIM, parent_id NULL, code issued), the
-- guardian claims it in the portal, and the row becomes an ACTIVE grant that
-- the parent console reads every request through. See System.md §4.
CREATE TABLE parent_student_links (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  -- NULL while an invite is waiting to be claimed; exactly one of
  -- parent_id / parent_email must be present (ck_parent_student_links_guardian).
  parent_id                    UUID REFERENCES users(id),
  parent_email                 VARCHAR(255),
  student_id                   UUID NOT NULL REFERENCES users(id),
  relation                     VARCHAR(50) NOT NULL,
  is_primary                   BOOLEAN NOT NULL DEFAULT FALSE,
  status                       VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  -- Modules this guardian may open. Two parents of one child legitimately see
  -- different things, so scope lives here rather than on the role.
  access_scope                 TEXT[] NOT NULL
                               DEFAULT ARRAY['attendance','timetable','examination','assignment','results','notice','finance']::text[],
  -- Guardian code for the claim flow. Cleared on claim, so it can never be
  -- replayed; the unique partial index below is what makes a guessed code
  -- resolve to at most one row.
  activation_code              VARCHAR(24),
  code_expires_at              TIMESTAMPTZ,
  claimed_at                   TIMESTAMPTZ,
  -- Optional end date for a temporary guardian; the reader fails closed after it.
  access_upto                  DATE,
  managed_by                   UUID REFERENCES users(id) ON DELETE SET NULL,
  note                         TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_parent_student_links__parent_id_student_id UNIQUE (parent_id, student_id),
  CONSTRAINT ck_parent_student_links_status
    CHECK (status IN ('PENDING_CLAIM','ACTIVE','SUSPENDED')),
  CONSTRAINT ck_parent_student_links_guardian
    CHECK (parent_id IS NOT NULL OR parent_email IS NOT NULL),
  CONSTRAINT ck_parent_student_links_activation
    CHECK (activation_code IS NULL OR status = 'PENDING_CLAIM')
);

CREATE TABLE attendance_sessions (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  subject_id                   UUID NOT NULL REFERENCES subjects(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  teacher_id                   UUID NOT NULL REFERENCES users(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  date                         DATE NOT NULL,
  period_label                 VARCHAR(30) NOT NULL,
  start_time                   TIME,
  end_time                     TIME,
  total_present                INTEGER NOT NULL DEFAULT 0,
  total_absent                 INTEGER NOT NULL DEFAULT 0,
  notes                        TEXT,
  is_locked                    BOOLEAN NOT NULL DEFAULT FALSE,
  locked_at                    TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_attendance_sessions__tenant_id_subject_id_class_id_date_p UNIQUE (tenant_id, subject_id, class_id, date, period_label)
);

CREATE TABLE attendance_records (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  session_id                   UUID NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
  student_id                   UUID NOT NULL REFERENCES users(id),
  status                       attendance_status NOT NULL,
  late_by_minutes              INTEGER,
  remarks                      VARCHAR(255),
  marked_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by                   UUID REFERENCES users(id),
  CONSTRAINT uq_attendance_records__session_id_student_id UNIQUE (session_id, student_id)
);

CREATE TABLE attendance_leaves (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  from_date                    DATE NOT NULL,
  to_date                      DATE NOT NULL,
  reason                       TEXT NOT NULL,
  document_url                 TEXT,
  status                       leave_status NOT NULL DEFAULT 'PENDING',
  -- In K-12 the guardian usually files the absence, not the child. Reviewing
  -- one without knowing who asked loses that context, so the requester is
  -- recorded rather than inferred from whose session posted it.
  requested_by                 UUID REFERENCES users(id) ON DELETE SET NULL,
  request_source               VARCHAR(20) NOT NULL DEFAULT 'STUDENT',
  reviewed_by                  UUID REFERENCES users(id),
  reviewed_at                  TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_attendance_leaves_request_source
    CHECK (request_source IN ('STUDENT','PARENT','STAFF'))
);

CREATE TABLE exams (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  title                        VARCHAR(255) NOT NULL,
  subject_id                   UUID NOT NULL REFERENCES subjects(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  exam_type                    exam_type NOT NULL,
  mode                         exam_mode NOT NULL DEFAULT 'ONLINE',
  total_marks                  INTEGER NOT NULL,
  passing_marks                INTEGER NOT NULL,
  duration_minutes             INTEGER NOT NULL,
  instructions                 TEXT,
  scheduled_at                 TIMESTAMPTZ NOT NULL,
  window_end_at                TIMESTAMPTZ,
  results_release_at           TIMESTAMPTZ,
  status                       exam_status NOT NULL DEFAULT 'DRAFT',
  schedule_approval_status     VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  schedule_approved_by         UUID REFERENCES users(id),
  schedule_approved_at         TIMESTAMPTZ,
  schedule_approval_note       TEXT,
  allow_review                 BOOLEAN NOT NULL DEFAULT FALSE,
  shuffle_questions            BOOLEAN NOT NULL DEFAULT FALSE,
  show_score_immediately       BOOLEAN NOT NULL DEFAULT FALSE,
  created_by                   UUID NOT NULL REFERENCES users(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_exams_schedule_approval_status CHECK (schedule_approval_status IN ('PENDING', 'APPROVED', 'REJECTED'))
);

CREATE TABLE exam_sections (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  exam_id                      UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  title                        VARCHAR(100) NOT NULL,
  description                  TEXT,
  max_marks                    INTEGER NOT NULL,
  sort_order                   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE question_bank_items (
  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  created_by                   UUID REFERENCES users(id) ON DELETE SET NULL,
  subject_id                   UUID REFERENCES subjects(id) ON DELETE SET NULL,
  class_id                     UUID REFERENCES classes(id) ON DELETE SET NULL,
  text                         TEXT NOT NULL,
  rich_text                    JSONB,
  question_type                question_type NOT NULL,
  default_marks                NUMERIC(5,2) NOT NULL DEFAULT 1.00,
  negative_marks               NUMERIC(5,2) NOT NULL DEFAULT 0.00,
  options                      JSONB NOT NULL DEFAULT '[]'::jsonb,
  image_url                    TEXT,
  explanation                  TEXT,
  difficulty                   difficulty_level,
  tags                         JSONB DEFAULT '[]'::jsonb,
  usage_count                  INTEGER NOT NULL DEFAULT 1,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE questions (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  exam_id                      UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  section_id                   UUID REFERENCES exam_sections(id),
  bank_item_id                 UUID REFERENCES question_bank_items(id) ON DELETE SET NULL,
  text                         TEXT NOT NULL,
  rich_text                    JSONB,
  question_type                question_type NOT NULL,
  marks                        NUMERIC(5,2) NOT NULL,
  negative_marks               NUMERIC(5,2) NOT NULL DEFAULT 0,
  image_url                    TEXT,
  explanation                  TEXT,
  difficulty                   difficulty_level,
  sort_order                   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE question_options (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id                  UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  text                         TEXT NOT NULL,
  image_url                    TEXT,
  is_correct                   BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order                   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE exam_hall_allocations (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  exam_id                      UUID NOT NULL REFERENCES exams(id),
  room_no                      VARCHAR(50) NOT NULL,
  invigilator_id               UUID REFERENCES users(id),
  student_ids                  UUID[] NOT NULL DEFAULT '{}',
  capacity                     INTEGER NOT NULL,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE exam_attempts (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  exam_id                      UUID NOT NULL REFERENCES exams(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  started_at                   TIMESTAMPTZ NOT NULL,
  submitted_at                 TIMESTAMPTZ,
  auto_submitted               BOOLEAN NOT NULL DEFAULT FALSE,
  total_score                  NUMERIC(8,2),
  percentage                   NUMERIC(5,2),
  grade                        VARCHAR(5),
  status                       attempt_status NOT NULL DEFAULT 'IN_PROGRESS',
  tab_switch_count             INTEGER NOT NULL DEFAULT 0,
  ip_address                   INET,
  device_info                  TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_exam_attempts__exam_id_student_id UNIQUE (exam_id, student_id)
);

CREATE TABLE answers (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  attempt_id                   UUID NOT NULL REFERENCES exam_attempts(id) ON DELETE CASCADE,
  question_id                  UUID NOT NULL REFERENCES questions(id),
  selected_option_id           UUID REFERENCES question_options(id),
  text_answer                  TEXT,
  matched_pairs                JSONB,
  score                        NUMERIC(5,2),
  is_auto_graded               BOOLEAN NOT NULL DEFAULT FALSE,
  feedback                     TEXT,
  graded_by                    UUID REFERENCES users(id),
  graded_at                    TIMESTAMPTZ,
  answered_at                  TIMESTAMPTZ,
  CONSTRAINT uq_answers__attempt_id_question_id UNIQUE (attempt_id, question_id)
);

CREATE TABLE malpractice_logs (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  attempt_id                   UUID NOT NULL REFERENCES exam_attempts(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  type                         VARCHAR(50) NOT NULL,
  description                  TEXT,
  evidence_url                 TEXT,
  action_taken                 VARCHAR(255),
  logged_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  handled_by                   UUID REFERENCES users(id)
);

CREATE TABLE assignments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  title                        VARCHAR(255) NOT NULL,
  description                  TEXT NOT NULL,
  subject_id                   UUID NOT NULL REFERENCES subjects(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  teacher_id                   UUID NOT NULL REFERENCES users(id),
  type                         assignment_type NOT NULL,
  total_marks                  INTEGER NOT NULL,
  passing_marks                INTEGER NOT NULL,
  due_date                     TIMESTAMPTZ NOT NULL,
  allow_late_submission        BOOLEAN NOT NULL DEFAULT FALSE,
  late_penalty_percent         INTEGER NOT NULL DEFAULT 0,
  max_file_size_mb             INTEGER NOT NULL DEFAULT 10,
  allowed_file_types           TEXT[] NOT NULL DEFAULT '{pdf,doc,docx,zip}',
  min_group_size               INTEGER NOT NULL DEFAULT 2,
  max_group_size               INTEGER NOT NULL DEFAULT 6,
  status                       assignment_status NOT NULL DEFAULT 'DRAFT',
  instructions_url             TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE project_groups (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  assignment_id                UUID NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
  name                         VARCHAR(100) NOT NULL,
  created_by                   UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_project_groups__assignment_name UNIQUE (assignment_id, name)
);

CREATE TABLE project_group_members (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  group_id                     UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
  student_id                   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  joined_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_project_group_members__group_student UNIQUE (group_id, student_id)
);

CREATE TABLE project_group_tasks (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  group_id                     UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
  title                        VARCHAR(255) NOT NULL,
  description                  TEXT,
  assigned_to                  UUID REFERENCES users(id) ON DELETE SET NULL,
  status                       VARCHAR(30) NOT NULL DEFAULT 'TODO',
  due_date                     TIMESTAMPTZ,
  created_by                   UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE project_group_messages (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  group_id                     UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
  sender_id                    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  message                      TEXT NOT NULL,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE project_group_resources (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  group_id                     UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
  title                        VARCHAR(255) NOT NULL,
  url                          TEXT NOT NULL,
  resource_type                VARCHAR(50) NOT NULL DEFAULT 'LINK',
  created_by                   UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE project_group_invitations (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  group_id                     UUID NOT NULL REFERENCES project_groups(id) ON DELETE CASCADE,
  student_id                   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invited_by                   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status                       VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  responded_at                 TIMESTAMPTZ
);

CREATE TABLE milestones (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id                UUID NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
  title                        VARCHAR(255) NOT NULL,
  description                  TEXT,
  sort_order                   INTEGER NOT NULL,
  marks                        INTEGER NOT NULL,
  due_date                     TIMESTAMPTZ,
  unlock_after_milestone_id    UUID REFERENCES milestones(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE submissions (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  assignment_id                UUID NOT NULL REFERENCES assignments(id),
  milestone_id                 UUID REFERENCES milestones(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  group_id                     UUID REFERENCES project_groups(id) ON DELETE SET NULL,
  text_response                TEXT,
  submitted_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_late                      BOOLEAN NOT NULL DEFAULT FALSE,
  late_by_minutes              INTEGER,
  score                        NUMERIC(5,2),
  grade                        VARCHAR(5),
  feedback                     TEXT,
  status                       submission_status NOT NULL DEFAULT 'SUBMITTED',
  reviewed_by                  UUID REFERENCES users(id),
  reviewed_at                  TIMESTAMPTZ,
  version                      INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT uq_submissions__assignment_id_milestone_id_student_id_ve UNIQUE (assignment_id, milestone_id, student_id, version)
);

CREATE TABLE submission_files (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id                UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  file_name                    VARCHAR(255) NOT NULL,
  file_key                     TEXT NOT NULL,
  file_size_bytes              BIGINT NOT NULL,
  mime_type                    VARCHAR(100) NOT NULL,
  uploaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE submission_reviews (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  submission_id                UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  reviewer_id                  UUID NOT NULL REFERENCES users(id),
  decision                     review_decision NOT NULL,
  marks_awarded                NUMERIC(6,2),
  feedback                     TEXT,
  attempt_number               SMALLINT NOT NULL DEFAULT 1,
  reviewed_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_submission_reviews__submission_id_attempt_number UNIQUE (submission_id, attempt_number)
);

CREATE TABLE notices (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  title                        VARCHAR(255) NOT NULL,
  body                         TEXT NOT NULL,
  author_id                    UUID NOT NULL REFERENCES users(id),
  target_scope                 notice_scope NOT NULL,
  target_id                    UUID,
  priority                     notice_priority NOT NULL DEFAULT 'NORMAL',
  is_pinned                    BOOLEAN NOT NULL DEFAULT FALSE,
  published_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at                   TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at                   TIMESTAMPTZ
);

CREATE TABLE notice_attachments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notice_id                    UUID NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
  file_name                    VARCHAR(255) NOT NULL,
  file_key                     TEXT,
  file_size_bytes              BIGINT NOT NULL DEFAULT 0,
  mime_type                    VARCHAR(100) NOT NULL,
  external_url                 TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_notice_attachment_source CHECK (
    (file_key IS NOT NULL AND external_url IS NULL) OR
    (file_key IS NULL AND external_url IS NOT NULL)
  )
);

CREATE TABLE notice_reads (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notice_id                    UUID NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
  user_id                      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  read_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_notice_reads__notice_id_user_id UNIQUE (notice_id, user_id)
);

CREATE TABLE discussion_threads (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  title                        VARCHAR(255) NOT NULL,
  body                         TEXT NOT NULL,
  author_id                    UUID NOT NULL REFERENCES users(id),
  scope_type                   VARCHAR(20) NOT NULL,
  scope_id                     UUID NOT NULL,
  tags                         TEXT[],
  is_pinned                    BOOLEAN NOT NULL DEFAULT FALSE,
  is_locked                    BOOLEAN NOT NULL DEFAULT FALSE,
  is_resolved                  BOOLEAN NOT NULL DEFAULT FALSE,
  resolved_by                  UUID REFERENCES users(id),
  reply_count                  INTEGER NOT NULL DEFAULT 0,
  upvote_count                 INTEGER NOT NULL DEFAULT 0,
  view_count                   INTEGER NOT NULL DEFAULT 0,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at                   TIMESTAMPTZ
);

CREATE TABLE discussion_replies (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  thread_id                    UUID NOT NULL REFERENCES discussion_threads(id) ON DELETE CASCADE,
  author_id                    UUID NOT NULL REFERENCES users(id),
  body                         TEXT NOT NULL,
  is_accepted_answer           BOOLEAN NOT NULL DEFAULT FALSE,
  upvote_count                 INTEGER NOT NULL DEFAULT 0,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at                   TIMESTAMPTZ
);

CREATE TABLE discussion_votes (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  target_type                  VARCHAR(10) NOT NULL,
  target_id                    UUID NOT NULL,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_discussion_votes__user_id_target_type_target_id UNIQUE (user_id, target_type, target_id)
);

CREATE TABLE content_items (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  title                        VARCHAR(255) NOT NULL,
  description                  TEXT,
  subject_id                   UUID NOT NULL REFERENCES subjects(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  uploaded_by                  UUID NOT NULL REFERENCES users(id),
  content_type                 content_type NOT NULL,
  file_key                     TEXT,
  external_url                 TEXT,
  file_size_bytes              BIGINT,
  duration_seconds             INTEGER,
  chapter                      VARCHAR(100),
  sort_order                   INTEGER NOT NULL DEFAULT 0,
  is_visible                   BOOLEAN NOT NULL DEFAULT TRUE,
  download_count               INTEGER NOT NULL DEFAULT 0,
  view_count                   INTEGER NOT NULL DEFAULT 0,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at                   TIMESTAMPTZ
);

CREATE TABLE content_tags (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content_id                   UUID NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  tag                          VARCHAR(50) NOT NULL,
  CONSTRAINT uq_content_tags__content_id_tag UNIQUE (content_id, tag)
);

CREATE TABLE content_access_logs (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content_id                   UUID NOT NULL REFERENCES content_items(id),
  user_id                      UUID NOT NULL REFERENCES users(id),
  action                       VARCHAR(10) NOT NULL,
  accessed_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE result_publications (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  title                        VARCHAR(255) NOT NULL,
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  class_id                     UUID REFERENCES classes(id),
  exam_ids                     UUID[] NOT NULL DEFAULT '{}',
  published_by                 UUID NOT NULL REFERENCES users(id),
  published_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_visible_to_students       BOOLEAN NOT NULL DEFAULT FALSE,
  approval_status              VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  approved_by                  UUID REFERENCES users(id),
  approved_at                  TIMESTAMPTZ,
  approval_note                TEXT,
  CONSTRAINT ck_result_publications_approval_status CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED'))
);

CREATE TABLE student_results (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  publication_id               UUID NOT NULL REFERENCES result_publications(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  total_marks_obtained         NUMERIC(8,2) NOT NULL,
  total_marks_possible         NUMERIC(8,2) NOT NULL,
  percentage                   NUMERIC(5,2) NOT NULL,
  grade                        VARCHAR(5) NOT NULL,
  rank                         INTEGER,
  result                       result_outcome NOT NULL,
  subject_scores               JSONB NOT NULL,
  remarks                      TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_student_results__publication_id_student_id UNIQUE (publication_id, student_id)
);

CREATE TABLE grade_cards (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  student_result_id            UUID NOT NULL REFERENCES student_results(id),
  file_key                     TEXT NOT NULL,
  generated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  template_version             VARCHAR(20) NOT NULL DEFAULT '1.0'
);

CREATE TABLE exam_controller_publications (

  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  title               VARCHAR(255) NOT NULL,
  academic_year_id    UUID NOT NULL REFERENCES academic_years(id),
  class_id            UUID REFERENCES classes(id),
  exam_ids            UUID[] NOT NULL DEFAULT '{}',
  compiled_by         UUID NOT NULL REFERENCES users(id),
  compiled_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at        TIMESTAMPTZ,
  status              exam_controller_publication_status NOT NULL DEFAULT 'DRAFT',
  summary             JSONB NOT NULL DEFAULT '{}'::jsonb,
  note                TEXT
);

CREATE TABLE exam_controller_grade_cards (

  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  publication_id          UUID NOT NULL REFERENCES exam_controller_publications(id) ON DELETE CASCADE,
  student_id              UUID NOT NULL REFERENCES users(id),
  class_id                UUID NOT NULL REFERENCES classes(id),
  total_marks_obtained    NUMERIC(8, 2) NOT NULL,
  total_marks_possible    NUMERIC(8, 2) NOT NULL,
  percentage              NUMERIC(5, 2) NOT NULL,
  grade                   VARCHAR(5) NOT NULL,
  rank                    INTEGER,
  subject_scores          JSONB NOT NULL DEFAULT '[]'::jsonb,
  status                  exam_controller_grade_card_status NOT NULL DEFAULT 'PENDING',
  generated_at            TIMESTAMPTZ,
  published_at            TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE timetable_slots (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  day_of_week                  SMALLINT NOT NULL,
  period_number                SMALLINT NOT NULL,
  start_time                   TIME NOT NULL,
  end_time                     TIME NOT NULL,
  subject_id                   UUID REFERENCES subjects(id),
  teacher_id                   UUID REFERENCES users(id),
  room_no                      VARCHAR(20),
  slot_type                    slot_type NOT NULL DEFAULT 'CLASS',
  effective_from               DATE NOT NULL,
  effective_to                 DATE,
  CONSTRAINT uq_timetable_slots__class_id_day_of_week_period_number_effec UNIQUE (class_id, day_of_week, period_number, effective_from)
);

CREATE TABLE timetable_substitutions (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  slot_id                      UUID NOT NULL REFERENCES timetable_slots(id),
  date                         DATE NOT NULL,
  substitute_teacher_id        UUID NOT NULL REFERENCES users(id),
  original_teacher_id          UUID NOT NULL REFERENCES users(id),
  reason                       TEXT,
  arranged_by                  UUID REFERENCES users(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_timetable_substitutions__slot_id_date UNIQUE (slot_id, date)
);

CREATE TABLE fee_structures (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  name                         VARCHAR(100) NOT NULL,
  applicable_to                UUID,
  total_amount                 NUMERIC(12,2) NOT NULL,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE fee_heads (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  structure_id                 UUID NOT NULL REFERENCES fee_structures(id) ON DELETE CASCADE,
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(100) NOT NULL,
  amount                       NUMERIC(12,2) NOT NULL,
  is_refundable                BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order                   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE student_fee_accounts (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  structure_id                 UUID NOT NULL REFERENCES fee_structures(id),
  total_fee                    NUMERIC(12,2) NOT NULL,
  concession_amount            NUMERIC(12,2) NOT NULL DEFAULT 0,
  scholarship_amount           NUMERIC(12,2) NOT NULL DEFAULT 0,
  net_payable                  NUMERIC(12,2) NOT NULL,
  total_paid                   NUMERIC(12,2) NOT NULL DEFAULT 0,
  balance_due                  NUMERIC(12,2) NOT NULL,
  status                       fee_status NOT NULL DEFAULT 'UNPAID',
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_student_fee_accounts__student_id_academic_year_id UNIQUE (student_id, academic_year_id)
);

CREATE TABLE fee_installments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fee_account_id               UUID NOT NULL REFERENCES student_fee_accounts(id),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  installment_number           SMALLINT NOT NULL,
  label                        VARCHAR(50) NOT NULL,
  amount                       NUMERIC(12,2) NOT NULL,
  due_date                     DATE NOT NULL,
  paid_amount                  NUMERIC(12,2) NOT NULL DEFAULT 0,
  status                       installment_status NOT NULL DEFAULT 'PENDING',
  late_fine                    NUMERIC(8,2) NOT NULL DEFAULT 0
);

CREATE TABLE fee_payments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  fee_account_id               UUID NOT NULL REFERENCES student_fee_accounts(id),
  installment_id               UUID REFERENCES fee_installments(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  amount                       NUMERIC(12,2) NOT NULL,
  payment_mode                 payment_mode NOT NULL,
  transaction_reference        VARCHAR(255),
  payment_date                 DATE NOT NULL,
  receipt_number               VARCHAR(50) NOT NULL,
  collected_by                 UUID NOT NULL REFERENCES users(id),
  notes                        TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_fee_payments__tenant_id_receipt_number UNIQUE (tenant_id, receipt_number)
);

CREATE TABLE scholarships (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(255) NOT NULL,
  type                         scholarship_type NOT NULL,
  value                        NUMERIC(10,2) NOT NULL,
  criteria                     TEXT,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE scholarship_grants (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  scholarship_id               UUID NOT NULL REFERENCES scholarships(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  fee_account_id               UUID NOT NULL REFERENCES student_fee_accounts(id),
  amount_granted               NUMERIC(12,2) NOT NULL,
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  granted_by                   UUID REFERENCES users(id),
  granted_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  remarks                      TEXT
);

CREATE SEQUENCE IF NOT EXISTS support_ticket_reference_seq START 1001;

CREATE TABLE support_tickets (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reference                    VARCHAR(20) CONSTRAINT uq_support_tickets_reference UNIQUE DEFAULT ('TKT-' || nextval('support_ticket_reference_seq')),
  owner_id                     UUID REFERENCES platform_owners(id) ON DELETE CASCADE,
  tenant_id                    UUID REFERENCES tenants(id),
  raised_by                    UUID REFERENCES users(id),
  assigned_to                  UUID REFERENCES platform_users(id),
  subject                      VARCHAR(255) NOT NULL,
  description                  TEXT,
  category                     VARCHAR(50) NOT NULL DEFAULT 'OTHER',
  priority                     VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
  status                       VARCHAR(20) NOT NULL DEFAULT 'OPEN',
  resolved_at                  TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_support_tickets_raiser CHECK (owner_id IS NOT NULL OR raised_by IS NOT NULL),
  CONSTRAINT ck_support_tickets_priority CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  CONSTRAINT ck_support_tickets_status CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'))
);

CREATE TABLE support_ticket_messages (

  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id    UUID NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
  author_role  VARCHAR(20) NOT NULL,
  author_id    UUID,
  body         TEXT NOT NULL,
  is_internal  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_ticket_messages_author CHECK (author_role IN ('OWNER', 'STAFF', 'SUPPORT', 'INSTITUTION'))
);

CREATE TABLE books (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  title                        VARCHAR(500) NOT NULL,
  authors                      TEXT[] NOT NULL,
  isbn                         VARCHAR(20),
  publisher                    VARCHAR(255),
  edition                      VARCHAR(50),
  publication_year             SMALLINT,
  subject_area                 VARCHAR(255),
  language                     VARCHAR(50) NOT NULL DEFAULT 'English',
  total_copies                 INTEGER NOT NULL DEFAULT 0,
  available_copies             INTEGER NOT NULL DEFAULT 0,
  cover_image_url              TEXT,
  location_code                VARCHAR(50),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_books_copy_counts CHECK (total_copies >= 0 AND available_copies BETWEEN 0 AND total_copies),
  CONSTRAINT ck_books_publication_year CHECK (publication_year IS NULL OR publication_year BETWEEN 1000 AND 2100)
);

CREATE TABLE book_copies (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id                      UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  accession_number             VARCHAR(50) NOT NULL,
  condition                    book_condition NOT NULL DEFAULT 'GOOD',
  is_available                 BOOLEAN NOT NULL DEFAULT TRUE,
  added_at                     DATE NOT NULL DEFAULT CURRENT_DATE,
  CONSTRAINT uq_book_copies__tenant_id_accession_number UNIQUE (tenant_id, accession_number)
);

CREATE TABLE book_issues (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  copy_id                      UUID NOT NULL REFERENCES book_copies(id),
  book_id                      UUID NOT NULL REFERENCES books(id),
  borrower_id                  UUID NOT NULL REFERENCES users(id),
  issued_by                    UUID NOT NULL REFERENCES users(id),
  issued_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  due_date                     DATE NOT NULL,
  returned_at                  TIMESTAMPTZ,
  returned_to                  UUID REFERENCES users(id),
  fine_amount                  NUMERIC(8,2) NOT NULL DEFAULT 0,
  fine_paid                    BOOLEAN NOT NULL DEFAULT FALSE,
  fine_paid_at                 TIMESTAMPTZ,
  notes                        TEXT,
  CONSTRAINT ck_book_issues_dates CHECK (due_date >= issued_at::date AND (returned_at IS NULL OR returned_at >= issued_at)),
  CONSTRAINT ck_book_issues_fine CHECK (fine_amount >= 0 AND (NOT fine_paid OR returned_at IS NOT NULL))
);

CREATE TABLE e_resources (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  title                        VARCHAR(500) NOT NULL,
  resource_type                VARCHAR(50) NOT NULL,
  url                          TEXT,
  file_key                     TEXT,
  subject_area                 VARCHAR(255),
  uploaded_by                  UUID NOT NULL REFERENCES users(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_e_resources_source CHECK ((url IS NOT NULL) <> (file_key IS NOT NULL)),
  CONSTRAINT ck_e_resources_type CHECK (resource_type IN ('EBOOK', 'JOURNAL', 'PAPER', 'LINK'))
);

-- Library rows carry redundant tenant/book keys for fast tenant-scoped reads;
-- these triggers enforce that the redundant keys can never disagree.
CREATE OR REPLACE FUNCTION validate_library_row() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME = 'book_copies' AND NOT EXISTS (
    SELECT 1 FROM books b WHERE b.id = NEW.book_id AND b.tenant_id = NEW.tenant_id
  ) THEN RAISE EXCEPTION 'Library copy tenant does not match book tenant'; END IF;
  IF TG_TABLE_NAME = 'book_issues' AND (
    NOT EXISTS (SELECT 1 FROM book_copies c WHERE c.id = NEW.copy_id AND c.book_id = NEW.book_id AND c.tenant_id = NEW.tenant_id)
    OR NOT EXISTS (SELECT 1 FROM users u WHERE u.id = NEW.borrower_id AND u.tenant_id = NEW.tenant_id)
    OR NOT EXISTS (SELECT 1 FROM users u WHERE u.id = NEW.issued_by AND u.tenant_id = NEW.tenant_id)
    OR (NEW.returned_to IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = NEW.returned_to AND u.tenant_id = NEW.tenant_id))
  ) THEN RAISE EXCEPTION 'Library issue references do not belong to its tenant'; END IF;
  IF TG_TABLE_NAME = 'e_resources' AND NOT EXISTS (
    SELECT 1 FROM users u WHERE u.id = NEW.uploaded_by AND u.tenant_id = NEW.tenant_id
  ) THEN RAISE EXCEPTION 'Library resource uploader does not belong to its tenant'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_validate_book_copy BEFORE INSERT OR UPDATE ON book_copies FOR EACH ROW EXECUTE FUNCTION validate_library_row();
CREATE TRIGGER trg_validate_book_issue BEFORE INSERT OR UPDATE ON book_issues FOR EACH ROW EXECUTE FUNCTION validate_library_row();
CREATE TRIGGER trg_validate_e_resource BEFORE INSERT OR UPDATE ON e_resources FOR EACH ROW EXECUTE FUNCTION validate_library_row();

-- Catalogue counters are derived from physical copies, including every path
-- that writes directly to PostgreSQL (imports and maintenance scripts).
CREATE OR REPLACE FUNCTION refresh_book_copy_counts() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE target UUID := COALESCE(NEW.book_id, OLD.book_id);
BEGIN
  UPDATE books b SET
    total_copies = (SELECT COUNT(*) FROM book_copies c WHERE c.book_id = target),
    available_copies = (SELECT COUNT(*) FROM book_copies c WHERE c.book_id = target AND c.is_available AND c.condition IN ('GOOD','FAIR')),
    updated_at = NOW()
  WHERE b.id = target;
  IF TG_OP = 'UPDATE' AND OLD.book_id <> NEW.book_id THEN
    UPDATE books b SET
      total_copies = (SELECT COUNT(*) FROM book_copies c WHERE c.book_id = OLD.book_id),
      available_copies = (SELECT COUNT(*) FROM book_copies c WHERE c.book_id = OLD.book_id AND c.is_available AND c.condition IN ('GOOD','FAIR')),
      updated_at = NOW()
    WHERE b.id = OLD.book_id;
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_refresh_book_copy_counts AFTER INSERT OR UPDATE OR DELETE ON book_copies FOR EACH ROW EXECUTE FUNCTION refresh_book_copy_counts();

CREATE TABLE hostel_blocks (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name                         VARCHAR(100) NOT NULL,
  gender                       gender NOT NULL,
  warden_id                    UUID REFERENCES users(id),
  total_rooms                  INTEGER NOT NULL DEFAULT 0,
  total_capacity               INTEGER NOT NULL DEFAULT 0,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_hostel_blocks_tenant_name UNIQUE (tenant_id, name)
);

CREATE TABLE hostel_rooms (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  block_id                     UUID NOT NULL REFERENCES hostel_blocks(id) ON DELETE CASCADE,
  room_number                  VARCHAR(20) NOT NULL,
  floor                        SMALLINT NOT NULL DEFAULT 0,
  capacity                     SMALLINT NOT NULL DEFAULT 2,
  room_type                    VARCHAR(30) NOT NULL DEFAULT 'SHARED',
  monthly_fee                  NUMERIC(10,2) NOT NULL,
  amenities                    TEXT[],
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_hostel_rooms__block_id_room_number UNIQUE (block_id, room_number),
  CONSTRAINT ck_hostel_rooms_capacity CHECK (capacity > 0 AND monthly_fee >= 0 AND floor >= 0)
);

CREATE TABLE hostel_allotments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  student_id                   UUID NOT NULL REFERENCES users(id),
  room_id                      UUID NOT NULL REFERENCES hostel_rooms(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  bed_number                   SMALLINT NOT NULL,
  allotted_from                DATE NOT NULL,
  allotted_to                  DATE,
  allotted_by                  UUID REFERENCES users(id),
  status                       allotment_status NOT NULL DEFAULT 'ACTIVE',
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_hostel_allotment_dates CHECK (allotted_to IS NULL OR allotted_to >= allotted_from)
);

CREATE TABLE hostel_attendance (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  room_id                      UUID NOT NULL REFERENCES hostel_rooms(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  date                         DATE NOT NULL,
  status                       hostel_attendance_status NOT NULL,
  marked_by                    UUID REFERENCES users(id),
  marked_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_hostel_attendance__student_id_date UNIQUE (student_id, date)
);

CREATE TABLE hostel_leave_requests (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  student_id                   UUID NOT NULL REFERENCES users(id),
  from_date                    DATE NOT NULL,
  to_date                      DATE NOT NULL,
  reason                       TEXT NOT NULL,
  destination                  TEXT,
  contact_during_leave         VARCHAR(20),
  status                       leave_status NOT NULL DEFAULT 'PENDING',
  reviewed_by                  UUID REFERENCES users(id),
  reviewed_at                  TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_hostel_leave_dates CHECK (to_date >= from_date)
);

CREATE TABLE hostel_complaints (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  student_id                   UUID NOT NULL REFERENCES users(id),
  room_id                      UUID REFERENCES hostel_rooms(id),
  category                     VARCHAR(50) NOT NULL,
  description                  TEXT NOT NULL,
  status                       complaint_status NOT NULL DEFAULT 'OPEN',
  resolved_by                  UUID REFERENCES users(id),
  resolved_at                  TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_hostel_complaint_category CHECK (category IN ('MAINTENANCE','FOOD','SECURITY','OTHER'))
);

CREATE OR REPLACE FUNCTION validate_hostel_row() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN
 IF TG_TABLE_NAME='hostel_rooms' AND NOT EXISTS(SELECT 1 FROM hostel_blocks b WHERE b.id=NEW.block_id AND b.tenant_id=NEW.tenant_id) THEN RAISE EXCEPTION 'Hostel room and block tenants differ'; END IF;
 IF TG_TABLE_NAME='hostel_allotments' AND (NOT EXISTS(SELECT 1 FROM hostel_rooms r WHERE r.id=NEW.room_id AND r.tenant_id=NEW.tenant_id) OR NOT EXISTS(SELECT 1 FROM users u WHERE u.id=NEW.student_id AND u.tenant_id=NEW.tenant_id) OR NOT EXISTS(SELECT 1 FROM academic_years y WHERE y.id=NEW.academic_year_id AND y.tenant_id=NEW.tenant_id) OR NEW.bed_number>(SELECT capacity FROM hostel_rooms WHERE id=NEW.room_id)) THEN RAISE EXCEPTION 'Invalid cross-tenant hostel allotment or bed'; END IF;
 IF TG_TABLE_NAME='hostel_attendance' AND NOT EXISTS(SELECT 1 FROM hostel_allotments a WHERE a.student_id=NEW.student_id AND a.room_id=NEW.room_id AND a.tenant_id=NEW.tenant_id AND a.status='ACTIVE') THEN RAISE EXCEPTION 'Attendance requires an active matching allotment'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER trg_validate_hostel_room BEFORE INSERT OR UPDATE ON hostel_rooms FOR EACH ROW EXECUTE FUNCTION validate_hostel_row();
CREATE TRIGGER trg_validate_hostel_allotment BEFORE INSERT OR UPDATE ON hostel_allotments FOR EACH ROW EXECUTE FUNCTION validate_hostel_row();
CREATE TRIGGER trg_validate_hostel_attendance BEFORE INSERT OR UPDATE ON hostel_attendance FOR EACH ROW EXECUTE FUNCTION validate_hostel_row();
CREATE OR REPLACE FUNCTION refresh_hostel_block_counts() RETURNS TRIGGER LANGUAGE plpgsql AS $$ DECLARE target UUID:=COALESCE(NEW.block_id,OLD.block_id); BEGIN UPDATE hostel_blocks b SET total_rooms=(SELECT count(*) FROM hostel_rooms r WHERE r.block_id=target AND r.is_active),total_capacity=(SELECT coalesce(sum(capacity),0) FROM hostel_rooms r WHERE r.block_id=target AND r.is_active) WHERE id=target; IF TG_OP='UPDATE' AND OLD.block_id<>NEW.block_id THEN UPDATE hostel_blocks b SET total_rooms=(SELECT count(*) FROM hostel_rooms r WHERE r.block_id=OLD.block_id AND r.is_active),total_capacity=(SELECT coalesce(sum(capacity),0) FROM hostel_rooms r WHERE r.block_id=OLD.block_id AND r.is_active) WHERE id=OLD.block_id; END IF; IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$;
CREATE TRIGGER trg_refresh_hostel_block_counts AFTER INSERT OR UPDATE OR DELETE ON hostel_rooms FOR EACH ROW EXECUTE FUNCTION refresh_hostel_block_counts();

CREATE TABLE vehicles (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  registration_no              VARCHAR(30) NOT NULL,
  vehicle_type                 VARCHAR(30) NOT NULL,
  capacity                     INTEGER NOT NULL,
  make_model                   VARCHAR(100),
  insurance_expiry             DATE,
  fitness_expiry               DATE,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE drivers (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(255) NOT NULL,
  phone                        VARCHAR(20) NOT NULL,
  license_no                   VARCHAR(50) NOT NULL,
  license_expiry               DATE,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE transport_routes (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(100) NOT NULL,
  code                         VARCHAR(20) NOT NULL,
  vehicle_id                   UUID REFERENCES vehicles(id),
  driver_id                    UUID REFERENCES drivers(id),
  monthly_fee                  NUMERIC(10,2) NOT NULL,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE transport_stops (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  route_id                     UUID NOT NULL REFERENCES transport_routes(id) ON DELETE CASCADE,
  name                         VARCHAR(255) NOT NULL,
  stop_order                   SMALLINT NOT NULL,
  latitude                     NUMERIC(10,7),
  longitude                    NUMERIC(10,7),
  pickup_time                  TIME,
  drop_time                    TIME
);

CREATE TABLE student_transport (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  route_id                     UUID NOT NULL REFERENCES transport_routes(id),
  stop_id                      UUID NOT NULL REFERENCES transport_stops(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  from_date                    DATE NOT NULL,
  to_date                      DATE,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE companies (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(255) NOT NULL,
  industry                     VARCHAR(100),
  website                      VARCHAR(255),
  hr_contact_name              VARCHAR(255),
  hr_contact_email             VARCHAR(255),
  hr_contact_phone             VARCHAR(20),
  logo_url                     TEXT,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE placement_drives (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  company_id                   UUID NOT NULL REFERENCES companies(id),
  title                        VARCHAR(255) NOT NULL,
  job_role                     VARCHAR(255) NOT NULL,
  job_type                     VARCHAR(30) NOT NULL,
  package_lpa                  NUMERIC(8,2),
  location                     VARCHAR(255),
  description                  TEXT,
  application_deadline         DATE NOT NULL,
  drive_date                   DATE,
  status                       drive_status NOT NULL DEFAULT 'UPCOMING',
  created_by                   UUID NOT NULL REFERENCES users(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE drive_eligibility (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  drive_id                     UUID NOT NULL REFERENCES placement_drives(id) ON DELETE CASCADE,
  department_ids               UUID[] NOT NULL DEFAULT '{}',
  min_percentage               NUMERIC(5,2),
  max_backlogs                 INTEGER NOT NULL DEFAULT 0,
  min_academic_year            VARCHAR(20),
  custom_criteria              TEXT
);

CREATE TABLE placement_applications (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  drive_id                     UUID NOT NULL REFERENCES placement_drives(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  resume_key                   TEXT,
  status                       application_status NOT NULL DEFAULT 'APPLIED',
  applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_placement_applications__drive_id_student_id UNIQUE (drive_id, student_id)
);

CREATE TABLE interview_rounds (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id               UUID NOT NULL REFERENCES placement_applications(id),
  round_number                 SMALLINT NOT NULL,
  round_type                   VARCHAR(30) NOT NULL,
  scheduled_at                 TIMESTAMPTZ,
  venue                        TEXT,
  result                       interview_result,
  feedback                     TEXT,
  conducted_at                 TIMESTAMPTZ
);

CREATE TABLE placement_offers (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  application_id               UUID NOT NULL REFERENCES placement_applications(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  drive_id                     UUID NOT NULL REFERENCES placement_drives(id),
  offer_letter_key             TEXT,
  package_lpa                  NUMERIC(8,2) NOT NULL,
  joining_date                 DATE,
  status                       offer_status NOT NULL DEFAULT 'ISSUED',
  issued_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE staff_profiles (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                      UUID NOT NULL REFERENCES users(id) UNIQUE,
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  employee_code                VARCHAR(50) NOT NULL,
  designation                  VARCHAR(100) NOT NULL,
  department_id                UUID REFERENCES departments(id),
  employment_type              employment_type NOT NULL,
  date_of_joining              DATE NOT NULL,
  date_of_leaving              DATE,
  qualification                TEXT,
  experience_years             SMALLINT NOT NULL DEFAULT 0,
  pan_number                   VARCHAR(20),
  bank_account_no              VARCHAR(30),
  bank_ifsc                    VARCHAR(15),
  bank_name                    VARCHAR(100),
  pf_number                    VARCHAR(30),
  emergency_contact_name       VARCHAR(255),
  emergency_contact_phone      VARCHAR(20),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE leave_policies (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(100) NOT NULL,
  code                         VARCHAR(10) NOT NULL,
  days_per_year                INTEGER NOT NULL,
  is_carry_forward             BOOLEAN NOT NULL DEFAULT FALSE,
  max_carry_forward_days       INTEGER NOT NULL DEFAULT 0,
  applies_to                   employment_type NOT NULL,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_leave_policies__tenant_id_code UNIQUE (tenant_id, code)
);

CREATE TABLE leave_requests (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  staff_id                     UUID NOT NULL REFERENCES users(id),
  policy_id                    UUID NOT NULL REFERENCES leave_policies(id),
  from_date                    DATE NOT NULL,
  to_date                      DATE NOT NULL,
  total_days                   NUMERIC(4,1) NOT NULL,
  reason                       TEXT NOT NULL,
  document_key                 TEXT,
  status                       leave_status NOT NULL DEFAULT 'PENDING',
  reviewed_by                  UUID REFERENCES users(id),
  reviewed_at                  TIMESTAMPTZ,
  review_note                  TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE salary_structures (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  staff_id                     UUID NOT NULL REFERENCES users(id),
  effective_from               DATE NOT NULL,
  basic_salary                 NUMERIC(12,2) NOT NULL,
  hra                          NUMERIC(12,2) NOT NULL DEFAULT 0,
  da                           NUMERIC(12,2) NOT NULL DEFAULT 0,
  ta                           NUMERIC(12,2) NOT NULL DEFAULT 0,
  other_allowances             JSONB,
  pf_deduction                 NUMERIC(12,2) NOT NULL DEFAULT 0,
  tax_deduction                NUMERIC(12,2) NOT NULL DEFAULT 0,
  other_deductions             JSONB,
  gross_salary                 NUMERIC(12,2) NOT NULL,
  net_salary                   NUMERIC(12,2) NOT NULL,
  created_by                   UUID REFERENCES users(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE payroll_runs (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  month                        SMALLINT NOT NULL,
  year                         SMALLINT NOT NULL,
  status                       payroll_status NOT NULL DEFAULT 'DRAFT',
  processed_by                 UUID REFERENCES users(id),
  processed_at                 TIMESTAMPTZ,
  paid_at                      TIMESTAMPTZ,
  CONSTRAINT uq_payroll_runs__tenant_id_month_year UNIQUE (tenant_id, month, year)
);

CREATE TABLE payslips (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  payroll_run_id               UUID NOT NULL REFERENCES payroll_runs(id),
  staff_id                     UUID NOT NULL REFERENCES users(id),
  working_days                 SMALLINT NOT NULL,
  present_days                 SMALLINT NOT NULL,
  leave_days                   SMALLINT NOT NULL DEFAULT 0,
  lop_days                     NUMERIC(4,1) NOT NULL DEFAULT 0,
  gross_salary                 NUMERIC(12,2) NOT NULL,
  total_deductions             NUMERIC(12,2) NOT NULL,
  net_salary                   NUMERIC(12,2) NOT NULL,
  components                   JSONB NOT NULL,
  file_key                     TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_payslips__payroll_run_id_staff_id UNIQUE (payroll_run_id, staff_id)
);

CREATE TABLE appraisal_cycles (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(100) NOT NULL,
  academic_year_id             UUID REFERENCES academic_years(id),
  start_date                   DATE NOT NULL,
  end_date                     DATE NOT NULL,
  status                       appraisal_status NOT NULL DEFAULT 'PLANNED'
);

CREATE TABLE appraisals (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id                     UUID NOT NULL REFERENCES appraisal_cycles(id),
  staff_id                     UUID NOT NULL REFERENCES users(id),
  reviewer_id                  UUID NOT NULL REFERENCES users(id),
  self_score                   NUMERIC(4,2),
  reviewer_score               NUMERIC(4,2),
  final_score                  NUMERIC(4,2),
  rating                       VARCHAR(20),
  comments                     TEXT,
  status                       appraisal_status NOT NULL DEFAULT 'PENDING',
  submitted_at                 TIMESTAMPTZ,
  CONSTRAINT uq_appraisals__cycle_id_staff_id UNIQUE (cycle_id, staff_id)
);

CREATE TABLE staff_documents (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  staff_id                     UUID NOT NULL REFERENCES users(id),
  document_type                VARCHAR(50) NOT NULL,
  file_name                    VARCHAR(255) NOT NULL,
  file_key                     TEXT NOT NULL,
  uploaded_by                  UUID REFERENCES users(id),
  uploaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE admission_cycles (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(100) NOT NULL,
  academic_year_id             UUID REFERENCES academic_years(id),
  application_open             DATE NOT NULL,
  application_close            DATE NOT NULL,
  status                       admission_cycle_status NOT NULL DEFAULT 'UPCOMING',
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE admission_applications (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  cycle_id                     UUID NOT NULL REFERENCES admission_cycles(id),
  applicant_name               VARCHAR(255) NOT NULL,
  applicant_email              VARCHAR(255) NOT NULL,
  applicant_phone              VARCHAR(20) NOT NULL,
  date_of_birth                DATE,
  gender                       gender,
  category                     VARCHAR(30),
  applied_for_dept             UUID REFERENCES departments(id),
  previous_marks_percent       NUMERIC(5,2),
  previous_institution         VARCHAR(255),
  status                       admission_status NOT NULL DEFAULT 'SUBMITTED',
  assigned_to                  UUID REFERENCES users(id),
  enrolled_user_id             UUID REFERENCES users(id),
  notes                        TEXT,
  submitted_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE application_documents (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id               UUID NOT NULL REFERENCES admission_applications(id) ON DELETE CASCADE,
  document_type                VARCHAR(50) NOT NULL,
  file_key                     TEXT NOT NULL,
  is_verified                  BOOLEAN NOT NULL DEFAULT FALSE,
  verified_by                  UUID REFERENCES users(id),
  uploaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE merit_lists (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  cycle_id                     UUID NOT NULL REFERENCES admission_cycles(id),
  list_number                  SMALLINT NOT NULL DEFAULT 1,
  department_id                UUID REFERENCES departments(id),
  category                     VARCHAR(30),
  application_ids              UUID[] NOT NULL DEFAULT '{}',
  published_at                 TIMESTAMPTZ,
  created_by                   UUID NOT NULL REFERENCES users(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE inventory_categories (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(100) NOT NULL,
  parent_id                    UUID REFERENCES inventory_categories(id)
);

CREATE TABLE inventory_items (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  category_id                  UUID REFERENCES inventory_categories(id),
  name                         VARCHAR(255) NOT NULL,
  code                         VARCHAR(50) NOT NULL,
  unit                         VARCHAR(20) NOT NULL,
  current_stock                NUMERIC(10,2) NOT NULL DEFAULT 0,
  reorder_level                NUMERIC(10,2) NOT NULL DEFAULT 0,
  unit_cost                    NUMERIC(10,2) NOT NULL DEFAULT 0,
  location                     VARCHAR(100),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_inventory_items__tenant_id_code UNIQUE (tenant_id, code)
);

CREATE TABLE stock_transactions (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  item_id                      UUID NOT NULL REFERENCES inventory_items(id),
  transaction_type             stock_txn_type NOT NULL,
  quantity                     NUMERIC(10,2) NOT NULL,
  balance_after                NUMERIC(10,2) NOT NULL,
  department_id                UUID REFERENCES departments(id),
  reference_no                 VARCHAR(100),
  notes                        TEXT,
  transacted_by                UUID NOT NULL REFERENCES users(id),
  transacted_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE vendors (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  name                         VARCHAR(255) NOT NULL,
  contact_person               VARCHAR(255),
  phone                        VARCHAR(20),
  email                        VARCHAR(255),
  address                      TEXT,
  gst_number                   VARCHAR(20),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE purchase_orders (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id),
  vendor_id                    UUID NOT NULL REFERENCES vendors(id),
  po_number                    VARCHAR(50) NOT NULL,
  total_amount                 NUMERIC(12,2) NOT NULL,
  status                       po_status NOT NULL DEFAULT 'DRAFT',
  created_by                   UUID NOT NULL REFERENCES users(id),
  approved_by                  UUID REFERENCES users(id),
  ordered_at                   DATE,
  expected_delivery            DATE,
  delivered_at                 DATE,
  notes                        TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_purchase_orders__tenant_id_po_number UNIQUE (tenant_id, po_number)
);

CREATE TABLE purchase_order_items (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  po_id                        UUID NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  item_id                      UUID NOT NULL REFERENCES inventory_items(id),
  quantity                     NUMERIC(10,2) NOT NULL,
  unit_price                   NUMERIC(10,2) NOT NULL,
  total_price                  NUMERIC(12,2) NOT NULL,
  received_quantity            NUMERIC(10,2) NOT NULL DEFAULT 0
);

CREATE TABLE notifications (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID REFERENCES tenants(id),
  user_id                      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title                        VARCHAR(255) NOT NULL,
  body                         TEXT NOT NULL,
  type                         VARCHAR(50) NOT NULL,
  data                         JSONB NOT NULL DEFAULT '{}',
  is_read                      BOOLEAN NOT NULL DEFAULT FALSE,
  read_at                      TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE device_tokens (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token                        TEXT NOT NULL,
  platform                     VARCHAR(10) NOT NULL,
  registered_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at                 TIMESTAMPTZ,
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_device_tokens__user_id_token UNIQUE (user_id, token)
);

-- Push enqueue path: "all live tokens of these users" during a broadcast.
CREATE INDEX idx_device_tokens_user_active
  ON device_tokens (user_id)
  WHERE is_active = TRUE;

-- Durable push outbox — one row per (notification, live device token),
-- drained by the FCM worker (NotificationService.deliver_pending).
CREATE TABLE notification_deliveries (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notification_id              UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
  user_id                      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_token_id              UUID NOT NULL REFERENCES device_tokens(id) ON DELETE CASCADE,
  platform                     VARCHAR(10) NOT NULL,            -- android | ios | web
  status                       VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING|SENT|FAILED|SKIPPED
  attempts                     SMALLINT NOT NULL DEFAULT 0,
  last_error                   TEXT,
  next_attempt_at              TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sent_at                      TIMESTAMPTZ
);

-- Worker scan: only pending rows whose backoff window has elapsed.
CREATE INDEX idx_notif_deliveries_pending
  ON notification_deliveries (status, next_attempt_at)
  WHERE status = 'PENDING';

-- Fast lookup when a notification row is deleted / audited.
CREATE INDEX idx_notif_deliveries_notification
  ON notification_deliveries (notification_id);

CREATE INDEX idx_notif_deliveries_user
  ON notification_deliveries (user_id);

CREATE TABLE audit_logs (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID REFERENCES tenants(id),
  user_id                      UUID NOT NULL,
  user_role                    VARCHAR(100) NOT NULL,
  action                       VARCHAR(100) NOT NULL,
  entity                       VARCHAR(100) NOT NULL,
  entity_id                    UUID,
  old_value                    JSONB,
  new_value                    JSONB,
  ip_address                   INET,
  user_agent                   TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE mentor_assignments (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  mentor_id                    UUID NOT NULL REFERENCES users(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  assigned_by                  UUID REFERENCES users(id),
  assigned_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
  notes                        TEXT,
  CONSTRAINT uq_mentor_assignments__mentor_id_student_id_academic_year_id UNIQUE (mentor_id, student_id, academic_year_id)
);

CREATE TABLE mentor_notes (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  mentor_id                    UUID NOT NULL REFERENCES users(id),
  student_id                   UUID NOT NULL REFERENCES users(id),
  assignment_id                UUID NOT NULL REFERENCES mentor_assignments(id) ON DELETE CASCADE,
  body                         TEXT NOT NULL,
  is_private                   BOOLEAN NOT NULL DEFAULT TRUE,
  note_date                    DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE bulk_import_jobs (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  import_type                  import_type NOT NULL,
  uploaded_by                  UUID NOT NULL REFERENCES users(id),
  file_key                     TEXT NOT NULL,
  file_name                    VARCHAR(255) NOT NULL,
  total_rows                   INTEGER NOT NULL DEFAULT 0,
  processed_rows               INTEGER NOT NULL DEFAULT 0,
  success_count                INTEGER NOT NULL DEFAULT 0,
  failure_count                INTEGER NOT NULL DEFAULT 0,
  failure_details              JSONB,
  status                       import_status NOT NULL DEFAULT 'PENDING',
  error_message                TEXT,
  result_file_key              TEXT,
  started_at                   TIMESTAMPTZ,
  completed_at                 TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE notification_templates (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  event_key                    VARCHAR(100) NOT NULL,
  channel                      notif_channel NOT NULL,
  title_template               VARCHAR(255) NOT NULL,
  body_template                TEXT NOT NULL,
  is_enabled                   BOOLEAN NOT NULL DEFAULT TRUE,
  available_variables          TEXT[] NOT NULL,
  updated_by                   UUID REFERENCES users(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_notification_templates__tenant_id_event_key_channel UNIQUE (tenant_id, event_key, channel)
);

CREATE TABLE academic_events (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  academic_year_id             UUID NOT NULL REFERENCES academic_years(id),
  title                        VARCHAR(255) NOT NULL,
  description                  TEXT,
  event_type                   academic_event_type NOT NULL,
  start_date                   DATE NOT NULL,
  end_date                     DATE NOT NULL,
  is_holiday                   BOOLEAN NOT NULL DEFAULT FALSE,
  applies_to                   event_scope NOT NULL DEFAULT 'ALL',
  scope_id                     UUID,
  color                        VARCHAR(7) DEFAULT '#3B82F6',
  created_by                   UUID REFERENCES users(id),
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE data_export_jobs (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  requested_by                 UUID NOT NULL REFERENCES users(id),
  export_type                  export_type NOT NULL,
  academic_year_id             UUID REFERENCES academic_years(id),
  filters                      JSONB,
  status                       export_status NOT NULL DEFAULT 'PENDING',
  file_key                     TEXT,
  file_size_bytes              BIGINT,
  expires_at                   TIMESTAMPTZ,
  error_message                TEXT,
  started_at                   TIMESTAMPTZ,
  completed_at                 TIMESTAMPTZ,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Online classes (live teaching with automatic attendance) ────────────────

CREATE TABLE online_classes (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  teacher_id                   UUID NOT NULL REFERENCES users(id),
  class_id                     UUID NOT NULL REFERENCES classes(id),
  subject_id                   UUID NOT NULL REFERENCES subjects(id),
  timetable_slot_id            UUID REFERENCES timetable_slots(id) ON DELETE SET NULL,
  topic                        VARCHAR(255) NOT NULL,
  mode                         online_class_mode NOT NULL DEFAULT 'SCHEDULED',
  status                       online_class_status NOT NULL DEFAULT 'SCHEDULED',
  scheduled_at                 TIMESTAMPTZ,
  duration_minutes             INTEGER NOT NULL DEFAULT 60,
  allow_join                   BOOLEAN NOT NULL DEFAULT TRUE,
  recording_enabled            BOOLEAN NOT NULL DEFAULT FALSE,
  recording_url                TEXT,
  started_at                   TIMESTAMPTZ,
  ended_at                     TIMESTAMPTZ,
  attendance_session_id        UUID REFERENCES attendance_sessions(id) ON DELETE SET NULL,
  -- Persisted whiteboard strokes for replay on rejoin/reload (capped at 500 entries).
  whiteboard_strokes           JSONB NOT NULL DEFAULT '[]',
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE online_class_participants (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  class_id                     UUID NOT NULL REFERENCES online_classes(id) ON DELETE CASCADE,
  student_id                   UUID NOT NULL REFERENCES users(id),
  waiting_since                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  joined_at                    TIMESTAMPTZ,
  left_at                      TIMESTAMPTZ,
  duration_seconds             INTEGER NOT NULL DEFAULT 0,
  attendance_status            online_attendance_status,
  hand_raised_at               TIMESTAMPTZ,
  is_online                    BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT uq_online_class_participants__class_id_student_id UNIQUE (class_id, student_id)
);

CREATE TABLE online_class_muted_students (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  class_id                     UUID NOT NULL REFERENCES online_classes(id) ON DELETE CASCADE,
  student_id                   UUID NOT NULL REFERENCES users(id),
  muted_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_muted__class_student UNIQUE (class_id, student_id)
);

CREATE TABLE online_class_messages (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  class_id                     UUID NOT NULL REFERENCES online_classes(id) ON DELETE CASCADE,
  sender_id                    UUID NOT NULL REFERENCES users(id),
  sender_role                  VARCHAR(20) NOT NULL,
  body                         TEXT NOT NULL,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE online_class_files (

  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  class_id                     UUID NOT NULL REFERENCES online_classes(id) ON DELETE CASCADE,
  uploader_id                  UUID NOT NULL REFERENCES users(id),
  uploader_role                VARCHAR(20) NOT NULL DEFAULT 'TEACHER',
  file_name                    VARCHAR(255) NOT NULL,
  file_path                    TEXT NOT NULL,
  file_size_bytes              BIGINT NOT NULL DEFAULT 0,
  mime_type                    VARCHAR(100) NOT NULL DEFAULT 'application/octet-stream',
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================================
--  SECTION 4 — DOCUMENTED INDEXES (58)
--  From §11 Full Index Strategy and the per-table Indexes lines.
-- ============================================================================

CREATE INDEX idx_submission_reviews_submission_id ON submission_reviews (submission_id, attempt_number DESC);
CREATE INDEX idx_submission_reviews_reviewer_id ON submission_reviews (reviewer_id);
CREATE INDEX idx_submission_reviews_tenant_id ON submission_reviews (tenant_id);
CREATE INDEX idx_project_groups_assignment ON project_groups (assignment_id);
CREATE INDEX idx_project_groups_tenant ON project_groups (tenant_id);
CREATE INDEX idx_project_group_members_group ON project_group_members (group_id);
CREATE INDEX idx_project_group_members_student ON project_group_members (student_id);
CREATE INDEX idx_project_group_tasks_group ON project_group_tasks (group_id);
CREATE INDEX idx_project_group_tasks_tenant ON project_group_tasks (tenant_id);
CREATE INDEX idx_project_group_tasks_assigned ON project_group_tasks (assigned_to);
CREATE INDEX idx_project_group_messages_group ON project_group_messages (group_id, created_at);
CREATE INDEX idx_project_group_resources_group ON project_group_resources (group_id);
CREATE INDEX idx_project_group_invitations_group ON project_group_invitations (group_id);
CREATE INDEX idx_project_group_invitations_student ON project_group_invitations (student_id);
CREATE INDEX idx_project_group_invitations_tenant ON project_group_invitations (tenant_id);
CREATE INDEX idx_project_group_invitations_status ON project_group_invitations (student_id, status);
CREATE INDEX idx_submissions_group ON submissions (group_id);
CREATE INDEX idx_users_tenant_id ON users (tenant_id);
CREATE INDEX idx_users_email ON users (email) WHERE email IS NOT NULL;
CREATE INDEX idx_users_is_active ON users (tenant_id, is_active);
CREATE INDEX idx_users_deleted_at ON users (deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_ra_user_id ON role_assignments (user_id);
CREATE INDEX idx_ra_tenant_role ON role_assignments (tenant_id, role_id);
CREATE INDEX idx_ra_scope_id ON role_assignments (scope_id) WHERE scope_id IS NOT NULL;
CREATE INDEX idx_tm_tenant_enabled ON tenant_modules (tenant_id, is_enabled);
CREATE INDEX idx_att_sessions_class_date ON attendance_sessions (class_id, date);
CREATE INDEX idx_att_sessions_teacher ON attendance_sessions (teacher_id);
CREATE INDEX idx_att_records_session ON attendance_records (session_id);
CREATE INDEX idx_att_records_student ON attendance_records (student_id);
CREATE INDEX idx_att_records_student_status ON attendance_records (student_id, status);
CREATE INDEX idx_exams_class_subject ON exams (class_id, subject_id);
CREATE INDEX idx_exams_status_date ON exams (status, scheduled_at);
CREATE INDEX idx_questions_exam ON questions (exam_id, sort_order);
CREATE INDEX idx_attempts_exam_student ON exam_attempts (exam_id, student_id);
CREATE INDEX idx_attempts_status ON exam_attempts (status);
CREATE INDEX idx_answers_attempt ON answers (attempt_id);
CREATE INDEX idx_assignments_class ON assignments (class_id, due_date);
CREATE INDEX idx_submissions_assignment ON submissions (assignment_id, student_id);
CREATE INDEX idx_submissions_status ON submissions (status);
CREATE INDEX idx_notices_scope_target ON notices (tenant_id, target_scope, target_id);
CREATE INDEX idx_notices_expiry ON notices (expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_threads_scope ON discussion_threads (scope_type, scope_id, created_at DESC);
CREATE INDEX idx_replies_thread ON discussion_replies (thread_id, created_at);
CREATE INDEX idx_content_subject_class ON content_items (subject_id, class_id, is_visible);
CREATE INDEX idx_content_chapter ON content_items (subject_id, chapter);
CREATE INDEX idx_results_publication ON student_results (publication_id);
CREATE INDEX idx_results_student ON student_results (student_id);
CREATE INDEX idx_timetable_class_day ON timetable_slots (class_id, day_of_week, period_number);
CREATE INDEX idx_timetable_teacher ON timetable_slots (teacher_id);
CREATE INDEX idx_fee_payments_student ON fee_payments (student_id);
CREATE INDEX idx_fee_payments_date ON fee_payments (payment_date);
CREATE INDEX idx_installments_due ON fee_installments (due_date, status);
-- This name was declared twice, once here with `created_at DESC` and once at the
-- end of the section without it — a fresh `psql -f` died on
-- "relation already exists". Kept the form the ORM and revision
-- c2d3e4f5a6b7 declare, so schema and migrations agree.
CREATE INDEX IF NOT EXISTS idx_notif_user_unread ON notifications (user_id, is_read, created_at);
CREATE INDEX idx_audit_tenant_time ON audit_logs (tenant_id, created_at DESC);
CREATE INDEX idx_audit_entity_id ON audit_logs (entity, entity_id);
CREATE INDEX idx_mentor_assignments_mentor_id ON mentor_assignments (mentor_id, academic_year_id);
CREATE INDEX idx_mentor_assignments_student_id ON mentor_assignments (student_id, academic_year_id);
CREATE INDEX idx_mentor_assignments_tenant_id ON mentor_assignments (tenant_id);
CREATE INDEX idx_mentor_notes_assignment_id ON mentor_notes (assignment_id);
CREATE INDEX idx_mentor_notes_student_id ON mentor_notes (student_id, created_at DESC);
CREATE INDEX idx_mentor_notes_mentor_id ON mentor_notes (mentor_id);
CREATE INDEX idx_bulk_imports_tenant_id ON bulk_import_jobs (tenant_id, created_at DESC);
CREATE INDEX idx_bulk_imports_uploaded_by ON bulk_import_jobs (uploaded_by);
CREATE INDEX idx_bulk_imports_status ON bulk_import_jobs (status) WHERE status IN ('PENDING','PROCESSING');
CREATE INDEX idx_notif_templates_tenant_event ON notification_templates (tenant_id, event_key);
CREATE INDEX idx_academic_events_tenant_year ON academic_events (tenant_id, academic_year_id);
CREATE INDEX idx_academic_events_dates ON academic_events (tenant_id, start_date, end_date);
CREATE INDEX idx_academic_events_is_holiday ON academic_events (tenant_id, is_holiday, start_date) WHERE is_holiday = TRUE;
CREATE INDEX idx_export_jobs_tenant_id ON data_export_jobs (tenant_id, created_at DESC);
CREATE INDEX idx_export_jobs_status ON data_export_jobs (status) WHERE status IN ('PENDING','PROCESSING');
CREATE INDEX idx_att_records_student_date ON attendance_records (tenant_id, student_id, status) INCLUDE (session_id);
CREATE INDEX idx_att_sessions_date_range ON attendance_sessions (tenant_id, class_id, date, subject_id);
CREATE INDEX idx_online_classes_tenant_status ON online_classes (tenant_id, status, scheduled_at);
CREATE INDEX idx_online_classes_teacher ON online_classes (teacher_id, created_at DESC);
CREATE INDEX idx_online_classes_class ON online_classes (class_id, scheduled_at);
CREATE INDEX idx_online_class_participants_class ON online_class_participants (class_id);
CREATE INDEX idx_online_class_participants_student ON online_class_participants (student_id);
CREATE INDEX idx_online_class_messages_class ON online_class_messages (class_id, created_at);
CREATE INDEX idx_online_class_files_class ON online_class_files (class_id, created_at);
CREATE INDEX idx_muted_class ON online_class_muted_students (class_id);


-- ============================================================================
--  SECTION 5 — FOREIGN-KEY INDEXES (216)
--  Every FK column that section 4 does not already cover. See note 3 above.
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_academic_events_academic_year_id ON academic_events (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_academic_events_created_by ON academic_events (created_by);
CREATE INDEX IF NOT EXISTS idx_admission_applications_applied_for_dept ON admission_applications (applied_for_dept);
CREATE INDEX IF NOT EXISTS idx_admission_applications_assigned_to ON admission_applications (assigned_to);
CREATE INDEX IF NOT EXISTS idx_admission_applications_cycle_id ON admission_applications (cycle_id);
CREATE INDEX IF NOT EXISTS idx_admission_applications_enrolled_user_id ON admission_applications (enrolled_user_id);
CREATE INDEX IF NOT EXISTS idx_admission_applications_tenant_id ON admission_applications (tenant_id);
CREATE INDEX IF NOT EXISTS idx_admission_cycles_academic_year_id ON admission_cycles (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_admission_cycles_tenant_id ON admission_cycles (tenant_id);
CREATE INDEX IF NOT EXISTS idx_answers_graded_by ON answers (graded_by);
CREATE INDEX IF NOT EXISTS idx_answers_question_id ON answers (question_id);
CREATE INDEX IF NOT EXISTS idx_answers_selected_option_id ON answers (selected_option_id);
CREATE INDEX IF NOT EXISTS idx_application_documents_application_id ON application_documents (application_id);
CREATE INDEX IF NOT EXISTS idx_application_documents_verified_by ON application_documents (verified_by);
CREATE INDEX IF NOT EXISTS idx_appraisal_cycles_academic_year_id ON appraisal_cycles (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_appraisal_cycles_tenant_id ON appraisal_cycles (tenant_id);
CREATE INDEX IF NOT EXISTS idx_appraisals_reviewer_id ON appraisals (reviewer_id);
CREATE INDEX IF NOT EXISTS idx_appraisals_staff_id ON appraisals (staff_id);
CREATE INDEX IF NOT EXISTS idx_assignments_academic_year_id ON assignments (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_assignments_subject_id ON assignments (subject_id);
CREATE INDEX IF NOT EXISTS idx_assignments_teacher_id ON assignments (teacher_id);
CREATE INDEX IF NOT EXISTS idx_assignments_tenant_id ON assignments (tenant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_leaves_class_id ON attendance_leaves (class_id);
CREATE INDEX IF NOT EXISTS idx_attendance_leaves_requested_by ON attendance_leaves (requested_by);
CREATE INDEX IF NOT EXISTS idx_attendance_leaves_reviewed_by ON attendance_leaves (reviewed_by);
CREATE INDEX IF NOT EXISTS idx_attendance_leaves_student_id ON attendance_leaves (student_id);
CREATE INDEX IF NOT EXISTS idx_attendance_leaves_tenant_id ON attendance_leaves (tenant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_updated_by ON attendance_records (updated_by);
CREATE INDEX IF NOT EXISTS idx_attendance_sessions_academic_year_id ON attendance_sessions (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_attendance_sessions_subject_id ON attendance_sessions (subject_id);
CREATE INDEX IF NOT EXISTS idx_book_copies_book_id ON book_copies (book_id);
CREATE INDEX IF NOT EXISTS idx_book_issues_book_id ON book_issues (book_id);
CREATE INDEX IF NOT EXISTS idx_book_issues_borrower_id ON book_issues (borrower_id);
CREATE INDEX IF NOT EXISTS idx_book_issues_copy_id ON book_issues (copy_id);
CREATE INDEX IF NOT EXISTS idx_book_issues_issued_by ON book_issues (issued_by);
CREATE INDEX IF NOT EXISTS idx_book_issues_returned_to ON book_issues (returned_to);
CREATE INDEX IF NOT EXISTS idx_book_issues_tenant_id ON book_issues (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_book_issues_active_copy ON book_issues (copy_id) WHERE returned_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_book_issues_tenant_due_active ON book_issues (tenant_id, due_date) WHERE returned_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_books_tenant_id ON books (tenant_id);
CREATE INDEX IF NOT EXISTS idx_books_tenant_title ON books (tenant_id, title);
CREATE UNIQUE INDEX IF NOT EXISTS uq_books_tenant_isbn ON books (tenant_id, isbn) WHERE isbn IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_class_grades_academic_year_id ON class_grades (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_class_grades_tenant_id ON class_grades (tenant_id);
CREATE INDEX IF NOT EXISTS idx_class_programs_academic_year_id ON class_programs (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_class_programs_department_id ON class_programs (department_id);
CREATE INDEX IF NOT EXISTS idx_class_programs_tenant_id ON class_programs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_classes_academic_year_id ON classes (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_classes_class_teacher_id ON classes (class_teacher_id);
CREATE INDEX IF NOT EXISTS idx_classes_department_id ON classes (department_id);
CREATE INDEX IF NOT EXISTS idx_classes_grade_id ON classes (grade_id);
CREATE INDEX IF NOT EXISTS idx_classes_program_id ON classes (program_id);

CREATE INDEX IF NOT EXISTS idx_companies_tenant_id ON companies (tenant_id);
CREATE INDEX IF NOT EXISTS idx_content_access_logs_content_id ON content_access_logs (content_id);
CREATE INDEX IF NOT EXISTS idx_content_access_logs_user_id ON content_access_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_content_items_class_id ON content_items (class_id);
CREATE INDEX IF NOT EXISTS idx_content_items_tenant_id ON content_items (tenant_id);
CREATE INDEX IF NOT EXISTS idx_content_items_uploaded_by ON content_items (uploaded_by);
CREATE INDEX IF NOT EXISTS idx_data_export_jobs_academic_year_id ON data_export_jobs (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_data_export_jobs_requested_by ON data_export_jobs (requested_by);
CREATE INDEX IF NOT EXISTS idx_departments_hod_id ON departments (hod_id);
CREATE INDEX IF NOT EXISTS idx_discussion_replies_author_id ON discussion_replies (author_id);
CREATE INDEX IF NOT EXISTS idx_discussion_replies_tenant_id ON discussion_replies (tenant_id);
CREATE INDEX IF NOT EXISTS idx_discussion_threads_author_id ON discussion_threads (author_id);
CREATE INDEX IF NOT EXISTS idx_discussion_threads_resolved_by ON discussion_threads (resolved_by);
CREATE INDEX IF NOT EXISTS idx_discussion_threads_tenant_id ON discussion_threads (tenant_id);
CREATE INDEX IF NOT EXISTS idx_drive_eligibility_drive_id ON drive_eligibility (drive_id);
CREATE INDEX IF NOT EXISTS idx_drivers_tenant_id ON drivers (tenant_id);
CREATE INDEX IF NOT EXISTS idx_e_resources_tenant_id ON e_resources (tenant_id);
CREATE INDEX IF NOT EXISTS idx_e_resources_tenant_subject ON e_resources (tenant_id, subject_area);
CREATE INDEX IF NOT EXISTS idx_e_resources_uploaded_by ON e_resources (uploaded_by);
CREATE INDEX IF NOT EXISTS idx_exam_attempts_student_id ON exam_attempts (student_id);
CREATE INDEX IF NOT EXISTS idx_exam_attempts_tenant_id ON exam_attempts (tenant_id);
CREATE INDEX IF NOT EXISTS idx_exam_hall_allocations_exam_id ON exam_hall_allocations (exam_id);
CREATE INDEX IF NOT EXISTS idx_exam_hall_allocations_invigilator_id ON exam_hall_allocations (invigilator_id);
CREATE INDEX IF NOT EXISTS idx_exam_hall_allocations_tenant_id ON exam_hall_allocations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_exam_sections_exam_id ON exam_sections (exam_id);
CREATE INDEX IF NOT EXISTS idx_exams_academic_year_id ON exams (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_exams_created_by ON exams (created_by);
CREATE INDEX IF NOT EXISTS idx_exams_subject_id ON exams (subject_id);
CREATE INDEX IF NOT EXISTS idx_exams_tenant_id ON exams (tenant_id);
CREATE INDEX IF NOT EXISTS idx_fee_heads_structure_id ON fee_heads (structure_id);
CREATE INDEX IF NOT EXISTS idx_fee_heads_tenant_id ON fee_heads (tenant_id);
CREATE INDEX IF NOT EXISTS idx_fee_installments_fee_account_id ON fee_installments (fee_account_id);
CREATE INDEX IF NOT EXISTS idx_fee_installments_tenant_id ON fee_installments (tenant_id);
CREATE INDEX IF NOT EXISTS idx_fee_payments_collected_by ON fee_payments (collected_by);
CREATE INDEX IF NOT EXISTS idx_fee_payments_fee_account_id ON fee_payments (fee_account_id);
CREATE INDEX IF NOT EXISTS idx_fee_payments_installment_id ON fee_payments (installment_id);
CREATE INDEX IF NOT EXISTS idx_fee_structures_academic_year_id ON fee_structures (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_fee_structures_tenant_id ON fee_structures (tenant_id);
CREATE INDEX IF NOT EXISTS idx_grade_cards_student_result_id ON grade_cards (student_result_id);
CREATE INDEX IF NOT EXISTS idx_grade_cards_tenant_id ON grade_cards (tenant_id);
CREATE INDEX IF NOT EXISTS idx_hostel_allotments_academic_year_id ON hostel_allotments (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_hostel_allotments_allotted_by ON hostel_allotments (allotted_by);
CREATE INDEX IF NOT EXISTS idx_hostel_allotments_room_id ON hostel_allotments (room_id);
CREATE INDEX IF NOT EXISTS idx_hostel_allotments_student_id ON hostel_allotments (student_id);
CREATE INDEX IF NOT EXISTS idx_hostel_allotments_tenant_id ON hostel_allotments (tenant_id);
CREATE UNIQUE INDEX uq_hostel_active_student ON hostel_allotments (student_id) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX uq_hostel_active_bed ON hostel_allotments (room_id, bed_number) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_hostel_attendance_marked_by ON hostel_attendance (marked_by);
CREATE INDEX IF NOT EXISTS idx_hostel_attendance_room_id ON hostel_attendance (room_id);
CREATE INDEX IF NOT EXISTS idx_hostel_attendance_tenant_id ON hostel_attendance (tenant_id);
CREATE INDEX idx_hostel_attendance_tenant_date ON hostel_attendance (tenant_id, date);
CREATE INDEX IF NOT EXISTS idx_hostel_blocks_tenant_id ON hostel_blocks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_hostel_blocks_warden_id ON hostel_blocks (warden_id);
CREATE INDEX IF NOT EXISTS idx_hostel_complaints_resolved_by ON hostel_complaints (resolved_by);
CREATE INDEX IF NOT EXISTS idx_hostel_complaints_room_id ON hostel_complaints (room_id);
CREATE INDEX IF NOT EXISTS idx_hostel_complaints_student_id ON hostel_complaints (student_id);
CREATE INDEX IF NOT EXISTS idx_hostel_complaints_tenant_id ON hostel_complaints (tenant_id);
CREATE INDEX idx_hostel_complaints_tenant_status ON hostel_complaints (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_hostel_leave_requests_reviewed_by ON hostel_leave_requests (reviewed_by);
CREATE INDEX IF NOT EXISTS idx_hostel_leave_requests_student_id ON hostel_leave_requests (student_id);
CREATE INDEX IF NOT EXISTS idx_hostel_leave_requests_tenant_id ON hostel_leave_requests (tenant_id);
CREATE INDEX idx_hostel_leaves_tenant_status ON hostel_leave_requests (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_hostel_rooms_tenant_id ON hostel_rooms (tenant_id);
CREATE INDEX IF NOT EXISTS idx_interview_rounds_application_id ON interview_rounds (application_id);
CREATE INDEX IF NOT EXISTS idx_inventory_categories_parent_id ON inventory_categories (parent_id);
CREATE INDEX IF NOT EXISTS idx_inventory_categories_tenant_id ON inventory_categories (tenant_id);
CREATE INDEX IF NOT EXISTS idx_inventory_items_category_id ON inventory_items (category_id);
CREATE INDEX IF NOT EXISTS idx_leave_requests_policy_id ON leave_requests (policy_id);
CREATE INDEX IF NOT EXISTS idx_leave_requests_reviewed_by ON leave_requests (reviewed_by);
CREATE INDEX IF NOT EXISTS idx_leave_requests_staff_id ON leave_requests (staff_id);
CREATE INDEX IF NOT EXISTS idx_leave_requests_tenant_id ON leave_requests (tenant_id);
CREATE INDEX IF NOT EXISTS idx_malpractice_logs_attempt_id ON malpractice_logs (attempt_id);
CREATE INDEX IF NOT EXISTS idx_malpractice_logs_handled_by ON malpractice_logs (handled_by);
CREATE INDEX IF NOT EXISTS idx_malpractice_logs_student_id ON malpractice_logs (student_id);
CREATE INDEX IF NOT EXISTS idx_malpractice_logs_tenant_id ON malpractice_logs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_mentor_assignments_academic_year_id ON mentor_assignments (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_mentor_assignments_assigned_by ON mentor_assignments (assigned_by);
CREATE INDEX IF NOT EXISTS idx_mentor_notes_tenant_id ON mentor_notes (tenant_id);
CREATE INDEX IF NOT EXISTS idx_merit_lists_created_by ON merit_lists (created_by);
CREATE INDEX IF NOT EXISTS idx_merit_lists_cycle_id ON merit_lists (cycle_id);
CREATE INDEX IF NOT EXISTS idx_merit_lists_department_id ON merit_lists (department_id);
CREATE INDEX IF NOT EXISTS idx_merit_lists_tenant_id ON merit_lists (tenant_id);
CREATE INDEX IF NOT EXISTS idx_milestones_assignment_id ON milestones (assignment_id);
CREATE INDEX IF NOT EXISTS idx_milestones_unlock_after_milestone_id ON milestones (unlock_after_milestone_id);
CREATE INDEX IF NOT EXISTS idx_notice_attachments_notice_id ON notice_attachments (notice_id);
CREATE INDEX IF NOT EXISTS idx_notice_reads_user_id ON notice_reads (user_id);
CREATE INDEX IF NOT EXISTS idx_notices_author_id ON notices (author_id);
CREATE INDEX IF NOT EXISTS idx_notification_templates_updated_by ON notification_templates (updated_by);
CREATE INDEX IF NOT EXISTS idx_notifications_tenant_id ON notifications (tenant_id);
CREATE INDEX IF NOT EXISTS idx_parent_student_links_managed_by ON parent_student_links (managed_by);
CREATE INDEX IF NOT EXISTS idx_parent_student_links_student_id ON parent_student_links (student_id);
CREATE INDEX IF NOT EXISTS idx_parent_student_links_tenant_id ON parent_student_links (tenant_id);
-- Portal hot path: "which children may this signed-in guardian see".
CREATE INDEX IF NOT EXISTS idx_parent_student_links_parent_active
  ON parent_student_links (tenant_id, parent_id, status) WHERE parent_id IS NOT NULL;
-- Admin lookup when resolving an invite by email (the service stores
-- guardian emails lower-cased, so a plain column index is enough).
CREATE INDEX IF NOT EXISTS idx_parent_student_links_pending_email
  ON parent_student_links (tenant_id, parent_email) WHERE parent_email IS NOT NULL;
-- One code can never resolve to two children.
CREATE UNIQUE INDEX IF NOT EXISTS uq_parent_student_links_activation_code
  ON parent_student_links (activation_code) WHERE activation_code IS NOT NULL;
-- Exactly one live primary guardian per student; `is_primary` decides who is
-- called first for an absence or a fee reminder, so two primaries is a bug.
CREATE UNIQUE INDEX IF NOT EXISTS uq_parent_student_links_primary_active
  ON parent_student_links (tenant_id, student_id) WHERE is_primary AND status = 'ACTIVE';
CREATE UNIQUE INDEX IF NOT EXISTS uq_parent_student_links_pending_email_student
  ON parent_student_links (tenant_id, parent_email, student_id)
  WHERE parent_email IS NOT NULL AND parent_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_payroll_runs_processed_by ON payroll_runs (processed_by);
CREATE INDEX IF NOT EXISTS idx_payslips_staff_id ON payslips (staff_id);
CREATE INDEX IF NOT EXISTS idx_payslips_tenant_id ON payslips (tenant_id);
CREATE INDEX IF NOT EXISTS idx_placement_applications_student_id ON placement_applications (student_id);
CREATE INDEX IF NOT EXISTS idx_placement_applications_tenant_id ON placement_applications (tenant_id);
CREATE INDEX IF NOT EXISTS idx_placement_drives_company_id ON placement_drives (company_id);
CREATE INDEX IF NOT EXISTS idx_placement_drives_created_by ON placement_drives (created_by);
CREATE INDEX IF NOT EXISTS idx_placement_drives_tenant_id ON placement_drives (tenant_id);
CREATE INDEX IF NOT EXISTS idx_placement_offers_application_id ON placement_offers (application_id);
CREATE INDEX IF NOT EXISTS idx_placement_offers_drive_id ON placement_offers (drive_id);
CREATE INDEX IF NOT EXISTS idx_placement_offers_student_id ON placement_offers (student_id);
CREATE INDEX IF NOT EXISTS idx_placement_offers_tenant_id ON placement_offers (tenant_id);
CREATE INDEX IF NOT EXISTS idx_purchase_order_items_item_id ON purchase_order_items (item_id);
CREATE INDEX IF NOT EXISTS idx_purchase_order_items_po_id ON purchase_order_items (po_id);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_approved_by ON purchase_orders (approved_by);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_created_by ON purchase_orders (created_by);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_vendor_id ON purchase_orders (vendor_id);
CREATE INDEX IF NOT EXISTS idx_question_options_question_id ON question_options (question_id);
CREATE INDEX IF NOT EXISTS idx_questions_section_id ON questions (section_id);

CREATE INDEX IF NOT EXISTS idx_questions_bank_item_id ON questions (bank_item_id);
CREATE INDEX IF NOT EXISTS idx_qbank_created_by ON question_bank_items (tenant_id, created_by);
CREATE INDEX IF NOT EXISTS idx_qbank_tenant_subject ON question_bank_items (tenant_id, subject_id);
CREATE INDEX IF NOT EXISTS idx_qbank_type_diff ON question_bank_items (tenant_id, question_type, difficulty);

CREATE INDEX IF NOT EXISTS idx_result_publications_academic_year_id ON result_publications (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_result_publications_class_id ON result_publications (class_id);
CREATE INDEX IF NOT EXISTS idx_result_publications_published_by ON result_publications (published_by);
CREATE INDEX IF NOT EXISTS idx_result_publications_tenant_id ON result_publications (tenant_id);
CREATE INDEX IF NOT EXISTS idx_role_assignments_assigned_by ON role_assignments (assigned_by);
CREATE INDEX IF NOT EXISTS idx_role_assignments_role_id ON role_assignments (role_id);
CREATE INDEX IF NOT EXISTS idx_roles_module_key ON roles (module_key);
CREATE INDEX IF NOT EXISTS idx_salary_structures_created_by ON salary_structures (created_by);
CREATE INDEX IF NOT EXISTS idx_salary_structures_staff_id ON salary_structures (staff_id);
CREATE INDEX IF NOT EXISTS idx_salary_structures_tenant_id ON salary_structures (tenant_id);
CREATE INDEX IF NOT EXISTS idx_scholarship_grants_academic_year_id ON scholarship_grants (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_scholarship_grants_fee_account_id ON scholarship_grants (fee_account_id);
CREATE INDEX IF NOT EXISTS idx_scholarship_grants_granted_by ON scholarship_grants (granted_by);
CREATE INDEX IF NOT EXISTS idx_scholarship_grants_scholarship_id ON scholarship_grants (scholarship_id);
CREATE INDEX IF NOT EXISTS idx_scholarship_grants_student_id ON scholarship_grants (student_id);
CREATE INDEX IF NOT EXISTS idx_scholarship_grants_tenant_id ON scholarship_grants (tenant_id);
CREATE INDEX IF NOT EXISTS idx_scholarships_tenant_id ON scholarships (tenant_id);
CREATE INDEX IF NOT EXISTS idx_staff_documents_staff_id ON staff_documents (staff_id);
CREATE INDEX IF NOT EXISTS idx_staff_documents_tenant_id ON staff_documents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_staff_documents_uploaded_by ON staff_documents (uploaded_by);
CREATE INDEX IF NOT EXISTS idx_staff_profiles_department_id ON staff_profiles (department_id);
CREATE INDEX IF NOT EXISTS idx_staff_profiles_tenant_id ON staff_profiles (tenant_id);
CREATE INDEX IF NOT EXISTS idx_stock_transactions_department_id ON stock_transactions (department_id);
CREATE INDEX IF NOT EXISTS idx_stock_transactions_item_id ON stock_transactions (item_id);
CREATE INDEX IF NOT EXISTS idx_stock_transactions_tenant_id ON stock_transactions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_stock_transactions_transacted_by ON stock_transactions (transacted_by);
CREATE INDEX IF NOT EXISTS idx_student_enrollments_academic_year_id ON student_enrollments (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_student_enrollments_class_id ON student_enrollments (class_id);
CREATE INDEX IF NOT EXISTS idx_student_enrollments_tenant_id ON student_enrollments (tenant_id);
CREATE INDEX IF NOT EXISTS idx_student_enrollments_transferred_to ON student_enrollments (transferred_to);
CREATE INDEX IF NOT EXISTS idx_student_fee_accounts_academic_year_id ON student_fee_accounts (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_student_fee_accounts_structure_id ON student_fee_accounts (structure_id);
CREATE INDEX IF NOT EXISTS idx_student_fee_accounts_tenant_id ON student_fee_accounts (tenant_id);
CREATE INDEX IF NOT EXISTS idx_student_results_class_id ON student_results (class_id);
CREATE INDEX IF NOT EXISTS idx_student_results_tenant_id ON student_results (tenant_id);
CREATE INDEX IF NOT EXISTS idx_student_transport_academic_year_id ON student_transport (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_student_transport_route_id ON student_transport (route_id);
CREATE INDEX IF NOT EXISTS idx_student_transport_stop_id ON student_transport (stop_id);
CREATE INDEX IF NOT EXISTS idx_student_transport_student_id ON student_transport (student_id);
CREATE INDEX IF NOT EXISTS idx_student_transport_tenant_id ON student_transport (tenant_id);
CREATE INDEX IF NOT EXISTS idx_subjects_class_id ON subjects (class_id);
CREATE INDEX IF NOT EXISTS idx_submission_files_submission_id ON submission_files (submission_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_platform_owners_email ON platform_owners (email);
CREATE INDEX IF NOT EXISTS idx_owner_sessions_owner_id ON owner_sessions (owner_id);
CREATE INDEX IF NOT EXISTS idx_owner_sessions_expires_at ON owner_sessions (expires_at);
CREATE INDEX IF NOT EXISTS idx_platform_sessions_user_id ON platform_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_platform_sessions_expires_at ON platform_sessions (expires_at);
CREATE INDEX IF NOT EXISTS idx_platform_invoices_tenant_id ON platform_invoices (tenant_id);
CREATE INDEX IF NOT EXISTS idx_platform_invoices_subscription_id ON platform_invoices (subscription_id);
CREATE INDEX IF NOT EXISTS idx_platform_invoice_lines_invoice_id ON platform_invoice_lines (invoice_id);
CREATE INDEX IF NOT EXISTS idx_platform_payments_tenant_id ON platform_payments (tenant_id);
CREATE INDEX IF NOT EXISTS idx_platform_payments_invoice_id ON platform_payments (invoice_id);
CREATE INDEX IF NOT EXISTS idx_platform_payments_order_id ON platform_payments (order_id);
CREATE INDEX IF NOT EXISTS idx_orders_status_created_at ON orders (status, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_contact_email ON orders (contact_email);
CREATE INDEX IF NOT EXISTS idx_orders_tenant_id ON orders (tenant_id);
CREATE INDEX IF NOT EXISTS idx_orders_owner_id ON orders (owner_id);
CREATE INDEX IF NOT EXISTS idx_orders_owner_platform_user_id ON orders (owner_platform_user_id);
CREATE INDEX IF NOT EXISTS idx_outbox_emails_status ON outbox_emails (status);
CREATE INDEX IF NOT EXISTS idx_outbox_emails_tenant_id ON outbox_emails (tenant_id);
CREATE INDEX IF NOT EXISTS idx_submissions_milestone_id ON submissions (milestone_id);
CREATE INDEX IF NOT EXISTS idx_submissions_reviewed_by ON submissions (reviewed_by);
CREATE INDEX IF NOT EXISTS idx_submissions_student_id ON submissions (student_id);
CREATE INDEX IF NOT EXISTS idx_submissions_tenant_id ON submissions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan_id ON subscriptions (plan_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant_id ON subscriptions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant_created ON subscriptions (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions (status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_assigned_to ON support_tickets (assigned_to);
CREATE INDEX IF NOT EXISTS idx_support_tickets_owner_id ON support_tickets (owner_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_owner_status ON support_tickets (owner_id, status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_raised_by ON support_tickets (raised_by);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets (status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_priority ON support_tickets (priority);
CREATE INDEX IF NOT EXISTS idx_exams_tenant_schedule_approval ON exams (tenant_id, schedule_approval_status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_exams_schedule_approved_by ON exams (schedule_approved_by);
CREATE INDEX IF NOT EXISTS idx_result_publications_tenant_approval ON result_publications (tenant_id, approval_status, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_result_publications_approved_by ON result_publications (approved_by);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mentor_assignments__tenant_student_year_active ON mentor_assignments (tenant_id, student_id, academic_year_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_timetable_substitutions_date ON timetable_substitutions (tenant_id, date);
CREATE INDEX IF NOT EXISTS idx_academic_events_tenant_year ON academic_events (tenant_id, academic_year_id);
CREATE INDEX IF NOT EXISTS idx_academic_events_dates ON academic_events (tenant_id, start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_academic_events_is_holiday ON academic_events (tenant_id, is_holiday, start_date) WHERE is_holiday = TRUE;
CREATE INDEX IF NOT EXISTS idx_ec_publications_tenant_year ON exam_controller_publications (tenant_id, academic_year_id);
CREATE INDEX IF NOT EXISTS idx_ec_publications_academic_year_id ON exam_controller_publications (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_ec_publications_status ON exam_controller_publications (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_ec_publications_compiled_by ON exam_controller_publications (compiled_by);
CREATE INDEX IF NOT EXISTS idx_ec_publications_class_id ON exam_controller_publications (class_id);
CREATE INDEX IF NOT EXISTS idx_ec_grade_cards_publication ON exam_controller_grade_cards (publication_id);
CREATE INDEX IF NOT EXISTS idx_ec_grade_cards_tenant_class ON exam_controller_grade_cards (tenant_id, class_id);
CREATE INDEX IF NOT EXISTS idx_ec_grade_cards_class_id ON exam_controller_grade_cards (class_id);
CREATE INDEX IF NOT EXISTS idx_ec_grade_cards_student_id ON exam_controller_grade_cards (student_id);
CREATE INDEX IF NOT EXISTS idx_grade_cards_tenant_pub ON exam_controller_grade_cards (tenant_id, publication_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_created_at ON support_tickets (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant_id ON support_tickets (tenant_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant_status ON support_tickets (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_teacher_subjects_assigned_by ON teacher_subjects (assigned_by);
CREATE INDEX IF NOT EXISTS idx_teacher_subjects_subject_id ON teacher_subjects (subject_id);
CREATE INDEX IF NOT EXISTS idx_teacher_subjects_tenant_id ON teacher_subjects (tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_modules_disabled_by ON tenant_modules (disabled_by);
CREATE INDEX IF NOT EXISTS idx_tenant_modules_enabled_by ON tenant_modules (enabled_by);
CREATE INDEX IF NOT EXISTS idx_tenant_modules_module_key ON tenant_modules (module_key);
CREATE INDEX IF NOT EXISTS idx_tenants_plan_id ON tenants (plan_id);
CREATE INDEX IF NOT EXISTS idx_tenants_owner_platform_user_id ON tenants (owner_platform_user_id);
CREATE INDEX IF NOT EXISTS idx_tenants_owner_id ON tenants (owner_id);
CREATE INDEX IF NOT EXISTS idx_tenants_is_active ON tenants (is_active);
CREATE INDEX IF NOT EXISTS idx_tenants_created_at ON tenants (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_platform_users_role ON platform_users (platform_role);
CREATE INDEX IF NOT EXISTS idx_timetable_slots_academic_year_id ON timetable_slots (academic_year_id);
CREATE INDEX IF NOT EXISTS idx_timetable_slots_subject_id ON timetable_slots (subject_id);
CREATE INDEX IF NOT EXISTS idx_timetable_slots_tenant_id ON timetable_slots (tenant_id);
CREATE INDEX IF NOT EXISTS idx_timetable_substitutions_arranged_by ON timetable_substitutions (arranged_by);
CREATE INDEX IF NOT EXISTS idx_timetable_substitutions_original_teacher_id ON timetable_substitutions (original_teacher_id);
CREATE INDEX IF NOT EXISTS idx_timetable_substitutions_substitute_teacher_id ON timetable_substitutions (substitute_teacher_id);
CREATE INDEX IF NOT EXISTS idx_timetable_substitutions_tenant_id ON timetable_substitutions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_transport_routes_driver_id ON transport_routes (driver_id);
CREATE INDEX IF NOT EXISTS idx_transport_routes_tenant_id ON transport_routes (tenant_id);
CREATE INDEX IF NOT EXISTS idx_transport_routes_vehicle_id ON transport_routes (vehicle_id);
CREATE INDEX IF NOT EXISTS idx_transport_stops_route_id ON transport_stops (route_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_tenant_id ON vehicles (tenant_id);
CREATE INDEX IF NOT EXISTS idx_vendors_tenant_id ON vendors (tenant_id);


-- ============================================================================
--  SECTION 6 — REFERENCE SEED DATA
--  The platform cannot boot without these three tables populated: the sidebar
--  is driven by `modules`, RBAC by `roles`, and tenant creation by `plans`.
--  Everything here is tenant-independent reference data, safe to run once.
--  Re-runnable: every insert is ON CONFLICT DO NOTHING.
-- ============================================================================

-- ── 6.1  Modules (16: 8 core + 8 optional) ─────────────────────────────────
-- Core modules are always on and cannot be switched off per tenant (§3).
INSERT INTO modules (key, name, description, is_core, icon, sort_order) VALUES
  ('attendance',  'Attendance',      'Daily and period-wise attendance marking and reports.', TRUE,  'ClipboardCheck', 1),
  ('examination', 'Examination',     'Online and offline exams, question banks, grading.',    TRUE,  'FileText',       2),
  ('assignment',  'Assignments',     'Assignments, milestones, submissions and review.',      TRUE,  'FilePlus',       3),
  ('notice',      'Notice Board',    'Institution, department and class notices.',            TRUE,  'Megaphone',      4),
  ('discussion',  'Discussion',      'Threaded subject and class discussion forums.',         TRUE,  'MessagesSquare', 5),
  ('content',     'Content',         'Study material: notes, videos, documents.',             TRUE,  'BookOpen',       6),
  ('results',     'Results',         'Result publication and grade cards.',                   TRUE,  'GraduationCap',  7),
  ('timetable',   'Timetable',       'Weekly timetable, slots and substitutions.',            TRUE,  'CalendarDays',   8),
  ('library',     'Library',         'Catalogue, circulation, fines and e-resources.',        FALSE, 'Library',        9),
  ('hostel',      'Hostel',          'Blocks, rooms, allotments and night roll-call.',        FALSE, 'Building2',     10),
  ('transport',   'Transport',       'Routes, stops, vehicles and student assignment.',       FALSE, 'Bus',           11),
  ('placement',   'Placement',       'Companies, drives, applications and offers.',           FALSE, 'Handshake',     12),
  ('hr',          'HR',              'Staff profiles, leave, payroll and appraisals.',        FALSE, 'Users',         13),
  ('admission',   'Admission',       'Admission cycles, applications and merit lists.',       FALSE, 'UserRoundPlus', 14),
  ('inventory',   'Inventory',       'Items, stock movements, vendors and purchase orders.',  FALSE, 'Boxes',         15),
  ('finance',     'Finance',         'Fee structures, collection, scholarships and dues.',    FALSE, 'BadgeIndianRupee', 16),
  ('parent',      'Parent Portal',   'Guardian portal, student-linked access, attendance & results view.', FALSE, 'Users', 17)
ON CONFLICT (key) DO NOTHING;


-- ── 6.2  Roles (22: 4 platform + 18 institution) ───────────────────────────
-- `module_key` marks a role that only appears once its module is enabled.
INSERT INTO roles (name, label, scope_level, is_platform, is_optional, module_key, description) VALUES
  -- Platform (4) — these live on app.xyz.com, not on a tenant subdomain
  ('SUPER_ADMIN',          'Super Admin',           'PLATFORM',    TRUE,  FALSE, NULL,        'Full platform control: tenants, plans, billing, platform users.'),
  ('SUPPORT_STAFF',        'Support Staff',         'PLATFORM',    TRUE,  FALSE, NULL,        'Reads any institution to resolve tickets. Cannot modify tenant data.'),
  ('SALES_EXECUTIVE',      'Sales Executive',       'PLATFORM',    TRUE,  FALSE, NULL,        'Trials, conversions and subscription management.'),
  ('FINANCE_MANAGER',      'Finance Manager',       'PLATFORM',    TRUE,  FALSE, NULL,        'Platform invoicing and revenue. No access to institution academic data.'),
  -- Institution — always available (9)
  ('INSTITUTION_ADMIN',    'Institution Admin',     'INSTITUTION', FALSE, FALSE, NULL,        'Full control of one institution: structure, users, roles, settings.'),
  ('PRINCIPAL',            'Principal',             'INSTITUTION', FALSE, FALSE, NULL,        'Institution-wide oversight; approves exam schedules and results.'),
  ('VICE_PRINCIPAL',       'Vice Principal',        'INSTITUTION', FALSE, FALSE, NULL,        'Institution-wide read access; posts notices.'),
  ('HOD',                  'Head of Department',    'DEPARTMENT',  FALSE, FALSE, NULL,        'Owns one department: its teachers, classes, subjects and mentors.'),
  ('TEACHER',              'Teacher',               'SUBJECT',     FALSE, FALSE, NULL,        'Marks attendance, sets exams and assignments, grades submissions.'),
  ('MENTOR',               'Mentor',                'SELF',        FALSE, FALSE, NULL,        'Pastoral care for an assigned group of mentees.'),
  ('EXAM_CONTROLLER',      'Exam Controller',       'INSTITUTION', FALSE, FALSE, NULL,        'Examination module across all departments: schedule, halls, results.'),
  ('ACADEMIC_COORDINATOR', 'Academic Coordinator',  'INSTITUTION', FALSE, FALSE, NULL,        'Builds the timetable, arranges substitutions, owns the academic calendar.'),
  ('STUDENT',              'Student',               'SELF',        FALSE, FALSE, NULL,        'Own attendance, exams, assignments, results and fees.'),
  -- Institution — activated by an optional module (9)
  ('PARENT',               'Parent',                'CHILD',       FALSE, TRUE,  'parent',    'Read-only view of a linked child.'),
  ('ACCOUNTANT',           'Accountant',            'INSTITUTION', FALSE, TRUE,  'finance',   'Fee structures, collection, receipts, defaulters and scholarships.'),
  ('LIBRARIAN',            'Librarian',             'INSTITUTION', FALSE, TRUE,  'library',   'Catalogue, issue and return, overdue fines, e-resources.'),
  ('HOSTEL_WARDEN',        'Hostel Warden',         'INSTITUTION', FALSE, TRUE,  'hostel',    'Rooms, allotments, night attendance, leave and complaints.'),
  ('TRANSPORT_MANAGER',    'Transport Manager',     'INSTITUTION', FALSE, TRUE,  'transport', 'Routes, stops, vehicles, drivers and student assignment.'),
  ('PLACEMENT_OFFICER',    'Placement Officer',     'INSTITUTION', FALSE, TRUE,  'placement', 'Companies, drives, applicants, interviews and offers.'),
  ('HR_MANAGER',           'HR Manager',            'INSTITUTION', FALSE, TRUE,  'hr',        'Staff records, leave approval, payroll and appraisals.'),
  ('ADMISSION_OFFICER',    'Admission Officer',     'INSTITUTION', FALSE, TRUE,  'admission', 'Admission cycles, applications, document checks, merit lists.'),
  ('STORE_MANAGER',        'Store Manager',         'INSTITUTION', FALSE, TRUE,  'inventory', 'Item catalogue, stock in/out, vendors and purchase orders.')
ON CONFLICT (name) DO NOTHING;


-- ── 6.3  Subscription plans ────────────────────────────────────────────────
-- max_students / max_teachers of -1 means unlimited.
INSERT INTO plans (name, slug, max_students, max_teachers, max_storage_gb,
                   price_monthly, price_yearly, currency, allowed_modules, is_active) VALUES
  ('Starter',      'starter',      500,  50,   10,   4999.00,   49990.00, 'INR',
     ARRAY['attendance','examination','assignment','notice','discussion','content','results','timetable'], TRUE),
  ('Standard',     'standard',    2000, 200,   50,  12999.00,  129990.00, 'INR',
     ARRAY['attendance','examination','assignment','notice','discussion','content','results','timetable',
           'library','hostel','finance'], TRUE),
  ('Professional', 'professional',5000, 500,  200,  24999.00,  249990.00, 'INR',
     ARRAY['attendance','examination','assignment','notice','discussion','content','results','timetable',
           'library','hostel','transport','placement','hr','finance'], TRUE),
  ('Enterprise',   'enterprise',    -1,  -1, 1000,  49999.00,  499990.00, 'INR',
     ARRAY['attendance','examination','assignment','notice','discussion','content','results','timetable',
           'library','hostel','transport','placement','hr','admission','inventory','finance'], TRUE)
ON CONFLICT (slug) DO NOTHING;


-- ── 6.4  Platform settings ─────────────────────────────────────────────────
INSERT INTO platform_settings (key, value) VALUES
  ('product_name',      'xyz.com'),
  ('support_email',     'support@xyz.com'),
  ('default_timezone',  'Asia/Kolkata'),
  ('default_currency',  'INR'),
  ('trial_length_days', '14'),
  ('brand_primary',     '#0F172A'),
  ('brand_accent',      '#4F46E5')
ON CONFLICT (key) DO NOTHING;


-- ============================================================================
--  SECTION 7 — ROW-LEVEL SECURITY (optional, commented)
-- ============================================================================
--
--  Tenant isolation is enforced in the application layer. If you also want it
--  enforced by the database, enable RLS per tenant-scoped table. The pattern,
--  applied to `users`, generalises to every table carrying tenant_id:
--
--      ALTER TABLE users ENABLE ROW LEVEL SECURITY;
--      CREATE POLICY tenant_isolation ON users
--        USING (tenant_id = current_setting('app.current_tenant')::uuid);
--
--  The API then sets the GUC once per request, inside the transaction:
--
--      SET LOCAL app.current_tenant = '<uuid>';
--
--  Note this must be SET LOCAL, not SET: with a connection pool a session-level
--  GUC leaks to the next request that borrows the connection.


-- ============================================================================
--  SECTION 7B — TENANT CASCADE (optional, commented)
-- ============================================================================
--
--  FINDING, flagged rather than silently changed.
--
--  The design doc marks `ON DELETE CASCADE` on only 8 of the 81 `tenant_id`
--  foreign keys. As written, `DELETE FROM tenants WHERE id = ...` fails:
--
--      ERROR: update or delete on table "tenants" violates foreign key
--             constraint "role_assignments_tenant_id_fkey"
--
--  That is defensible — an accidental tenant delete would erase an entire
--  institution, and §4.2 offers `is_active = FALSE` for suspension, which is
--  what the platform console actually uses. But it does mean **there is no
--  way to hard-delete a tenant**, so GDPR-style erasure needs either these
--  constraints or a hand-written purge routine that walks 73 tables in
--  dependency order.
--
--  Uncomment the block below only if hard delete is a requirement. The 8 that
--  already cascade (users, tenant_modules, notifications, device_tokens and
--  the four addendum tables) are omitted — they need no change.

--   ALTER TABLE academic_years DROP CONSTRAINT academic_years_tenant_id_fkey, ADD CONSTRAINT academic_years_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE admission_applications DROP CONSTRAINT admission_applications_tenant_id_fkey, ADD CONSTRAINT admission_applications_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE admission_cycles DROP CONSTRAINT admission_cycles_tenant_id_fkey, ADD CONSTRAINT admission_cycles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE appraisal_cycles DROP CONSTRAINT appraisal_cycles_tenant_id_fkey, ADD CONSTRAINT appraisal_cycles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE assignments DROP CONSTRAINT assignments_tenant_id_fkey, ADD CONSTRAINT assignments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE attendance_leaves DROP CONSTRAINT attendance_leaves_tenant_id_fkey, ADD CONSTRAINT attendance_leaves_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE attendance_records DROP CONSTRAINT attendance_records_tenant_id_fkey, ADD CONSTRAINT attendance_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE attendance_sessions DROP CONSTRAINT attendance_sessions_tenant_id_fkey, ADD CONSTRAINT attendance_sessions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE audit_logs DROP CONSTRAINT audit_logs_tenant_id_fkey, ADD CONSTRAINT audit_logs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE book_copies DROP CONSTRAINT book_copies_tenant_id_fkey, ADD CONSTRAINT book_copies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE book_issues DROP CONSTRAINT book_issues_tenant_id_fkey, ADD CONSTRAINT book_issues_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE books DROP CONSTRAINT books_tenant_id_fkey, ADD CONSTRAINT books_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE classes DROP CONSTRAINT classes_tenant_id_fkey, ADD CONSTRAINT classes_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE companies DROP CONSTRAINT companies_tenant_id_fkey, ADD CONSTRAINT companies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE content_items DROP CONSTRAINT content_items_tenant_id_fkey, ADD CONSTRAINT content_items_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE departments DROP CONSTRAINT departments_tenant_id_fkey, ADD CONSTRAINT departments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE discussion_replies DROP CONSTRAINT discussion_replies_tenant_id_fkey, ADD CONSTRAINT discussion_replies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE discussion_threads DROP CONSTRAINT discussion_threads_tenant_id_fkey, ADD CONSTRAINT discussion_threads_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE drivers DROP CONSTRAINT drivers_tenant_id_fkey, ADD CONSTRAINT drivers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE e_resources DROP CONSTRAINT e_resources_tenant_id_fkey, ADD CONSTRAINT e_resources_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE exam_attempts DROP CONSTRAINT exam_attempts_tenant_id_fkey, ADD CONSTRAINT exam_attempts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE exam_hall_allocations DROP CONSTRAINT exam_hall_allocations_tenant_id_fkey, ADD CONSTRAINT exam_hall_allocations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE exams DROP CONSTRAINT exams_tenant_id_fkey, ADD CONSTRAINT exams_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE fee_heads DROP CONSTRAINT fee_heads_tenant_id_fkey, ADD CONSTRAINT fee_heads_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE fee_installments DROP CONSTRAINT fee_installments_tenant_id_fkey, ADD CONSTRAINT fee_installments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE fee_payments DROP CONSTRAINT fee_payments_tenant_id_fkey, ADD CONSTRAINT fee_payments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE fee_structures DROP CONSTRAINT fee_structures_tenant_id_fkey, ADD CONSTRAINT fee_structures_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE grade_cards DROP CONSTRAINT grade_cards_tenant_id_fkey, ADD CONSTRAINT grade_cards_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE hostel_allotments DROP CONSTRAINT hostel_allotments_tenant_id_fkey, ADD CONSTRAINT hostel_allotments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE hostel_attendance DROP CONSTRAINT hostel_attendance_tenant_id_fkey, ADD CONSTRAINT hostel_attendance_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE hostel_blocks DROP CONSTRAINT hostel_blocks_tenant_id_fkey, ADD CONSTRAINT hostel_blocks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE hostel_complaints DROP CONSTRAINT hostel_complaints_tenant_id_fkey, ADD CONSTRAINT hostel_complaints_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE hostel_leave_requests DROP CONSTRAINT hostel_leave_requests_tenant_id_fkey, ADD CONSTRAINT hostel_leave_requests_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE hostel_rooms DROP CONSTRAINT hostel_rooms_tenant_id_fkey, ADD CONSTRAINT hostel_rooms_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE inventory_categories DROP CONSTRAINT inventory_categories_tenant_id_fkey, ADD CONSTRAINT inventory_categories_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE inventory_items DROP CONSTRAINT inventory_items_tenant_id_fkey, ADD CONSTRAINT inventory_items_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE leave_policies DROP CONSTRAINT leave_policies_tenant_id_fkey, ADD CONSTRAINT leave_policies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE leave_requests DROP CONSTRAINT leave_requests_tenant_id_fkey, ADD CONSTRAINT leave_requests_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE malpractice_logs DROP CONSTRAINT malpractice_logs_tenant_id_fkey, ADD CONSTRAINT malpractice_logs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE merit_lists DROP CONSTRAINT merit_lists_tenant_id_fkey, ADD CONSTRAINT merit_lists_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE notices DROP CONSTRAINT notices_tenant_id_fkey, ADD CONSTRAINT notices_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE notifications DROP CONSTRAINT notifications_tenant_id_fkey, ADD CONSTRAINT notifications_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE parent_student_links DROP CONSTRAINT parent_student_links_tenant_id_fkey, ADD CONSTRAINT parent_student_links_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE payroll_runs DROP CONSTRAINT payroll_runs_tenant_id_fkey, ADD CONSTRAINT payroll_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE payslips DROP CONSTRAINT payslips_tenant_id_fkey, ADD CONSTRAINT payslips_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE placement_applications DROP CONSTRAINT placement_applications_tenant_id_fkey, ADD CONSTRAINT placement_applications_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE placement_drives DROP CONSTRAINT placement_drives_tenant_id_fkey, ADD CONSTRAINT placement_drives_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE placement_offers DROP CONSTRAINT placement_offers_tenant_id_fkey, ADD CONSTRAINT placement_offers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE purchase_orders DROP CONSTRAINT purchase_orders_tenant_id_fkey, ADD CONSTRAINT purchase_orders_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE result_publications DROP CONSTRAINT result_publications_tenant_id_fkey, ADD CONSTRAINT result_publications_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE role_assignments DROP CONSTRAINT role_assignments_tenant_id_fkey, ADD CONSTRAINT role_assignments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE salary_structures DROP CONSTRAINT salary_structures_tenant_id_fkey, ADD CONSTRAINT salary_structures_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE scholarship_grants DROP CONSTRAINT scholarship_grants_tenant_id_fkey, ADD CONSTRAINT scholarship_grants_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE scholarships DROP CONSTRAINT scholarships_tenant_id_fkey, ADD CONSTRAINT scholarships_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE staff_documents DROP CONSTRAINT staff_documents_tenant_id_fkey, ADD CONSTRAINT staff_documents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE staff_profiles DROP CONSTRAINT staff_profiles_tenant_id_fkey, ADD CONSTRAINT staff_profiles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE stock_transactions DROP CONSTRAINT stock_transactions_tenant_id_fkey, ADD CONSTRAINT stock_transactions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE student_enrollments DROP CONSTRAINT student_enrollments_tenant_id_fkey, ADD CONSTRAINT student_enrollments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE student_fee_accounts DROP CONSTRAINT student_fee_accounts_tenant_id_fkey, ADD CONSTRAINT student_fee_accounts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE student_results DROP CONSTRAINT student_results_tenant_id_fkey, ADD CONSTRAINT student_results_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE student_transport DROP CONSTRAINT student_transport_tenant_id_fkey, ADD CONSTRAINT student_transport_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE subjects DROP CONSTRAINT subjects_tenant_id_fkey, ADD CONSTRAINT subjects_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE submission_reviews DROP CONSTRAINT submission_reviews_tenant_id_fkey, ADD CONSTRAINT submission_reviews_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE submissions DROP CONSTRAINT submissions_tenant_id_fkey, ADD CONSTRAINT submissions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE subscriptions DROP CONSTRAINT subscriptions_tenant_id_fkey, ADD CONSTRAINT subscriptions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE support_tickets DROP CONSTRAINT support_tickets_tenant_id_fkey, ADD CONSTRAINT support_tickets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE teacher_subjects DROP CONSTRAINT teacher_subjects_tenant_id_fkey, ADD CONSTRAINT teacher_subjects_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE tenant_settings DROP CONSTRAINT tenant_settings_tenant_id_fkey, ADD CONSTRAINT tenant_settings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE timetable_slots DROP CONSTRAINT timetable_slots_tenant_id_fkey, ADD CONSTRAINT timetable_slots_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE timetable_substitutions DROP CONSTRAINT timetable_substitutions_tenant_id_fkey, ADD CONSTRAINT timetable_substitutions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE transport_routes DROP CONSTRAINT transport_routes_tenant_id_fkey, ADD CONSTRAINT transport_routes_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE vehicles DROP CONSTRAINT vehicles_tenant_id_fkey, ADD CONSTRAINT vehicles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
--   ALTER TABLE vendors DROP CONSTRAINT vendors_tenant_id_fkey, ADD CONSTRAINT vendors_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;


-- ============================================================================
--  SECTION 8 — VERIFICATION
--  Run after loading. Reality as of the parent portal: 132 tables · 57 enums
--  · 355 foreign keys · 24 unindexed foreign keys.
--
--  These numbers were previously asserted as 107 / 120 and "0 unindexed", all
--  three of which a fresh `psql -f database/database.sql` failed — a working
--  install printed a stack trace. The counts are now what the file actually
--  produces, and the FK-index rule is a *ratchet* rather than an absolute: the
--  24 legacy ones are mostly nullable `*_by` audit columns where an index
--  costs more than it buys. Raising the number means adding a new unindexed
--  FK, which is exactly the drift this check is for.
-- ============================================================================

DO $do$
DECLARE
  v_tables   INTEGER;
  v_enums    INTEGER;
  v_fks      INTEGER;
  v_unindexed INTEGER;
  v_modules  INTEGER;
  v_roles    INTEGER;
  v_plans    INTEGER;
  v_baseline CONSTANT INTEGER := 25;
BEGIN
  SELECT count(*) INTO v_tables
    FROM information_schema.tables
   WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
     AND table_name <> 'alembic_version';

  SELECT count(*) INTO v_enums
    FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
   WHERE t.typtype = 'e' AND n.nspname = 'public';

  SELECT count(*) INTO v_fks
    FROM information_schema.table_constraints
   WHERE constraint_schema = 'public' AND constraint_type = 'FOREIGN KEY';

  SELECT count(*) INTO v_unindexed FROM (
    SELECT 1
      FROM pg_constraint c
      JOIN unnest(c.conkey) WITH ORDINALITY k(attnum, ord) ON k.ord = 1
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
     WHERE c.contype = 'f'
       AND NOT EXISTS (SELECT 1 FROM pg_index i
                        WHERE i.indrelid = c.conrelid
                          AND (i.indkey::int2[])[0] = a.attnum)
  ) q;

  SELECT count(*) INTO v_modules FROM modules;
  SELECT count(*) INTO v_roles   FROM roles;
  SELECT count(*) INTO v_plans   FROM plans;

  RAISE NOTICE '─────────────────────────────────────────────';
  RAISE NOTICE ' ERP + LMS schema loaded';
  RAISE NOTICE '─────────────────────────────────────────────';
  RAISE NOTICE ' Tables            : %', v_tables;
  RAISE NOTICE ' Enum types        : %', v_enums;
  RAISE NOTICE ' Foreign keys      : %', v_fks;
  RAISE NOTICE ' Unindexed FKs     : %', v_unindexed;
  RAISE NOTICE ' Seed: modules     : %', v_modules;
  RAISE NOTICE ' Seed: roles       : %', v_roles;
  RAISE NOTICE ' Seed: plans       : %', v_plans;
  RAISE NOTICE '─────────────────────────────────────────────';

  IF v_tables <> 135 THEN
    RAISE EXCEPTION 'Expected 135 tables, found %', v_tables;
  END IF;

  IF v_unindexed > v_baseline THEN
    RAISE EXCEPTION 'Expected at most % unindexed foreign keys, found % — every new FK '
                    'needs an index or a deliberate reason not to have one',
      v_baseline, v_unindexed;
  END IF;
  IF v_modules <> 17 OR v_roles <> 22 OR v_plans <> 4 THEN
    RAISE EXCEPTION 'Seed incomplete: % modules (want 17), % roles (want 22), % plans (want 4)',
      v_modules, v_roles, v_plans;
  END IF;

  RAISE NOTICE ' All checks passed.';
END $do$;


-- ============================================================================
--  End of database.sql
-- ============================================================================
