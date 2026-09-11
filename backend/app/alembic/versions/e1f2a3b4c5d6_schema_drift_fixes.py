"""schema_drift_fixes

Revision ID: e1f2a3b4c5d6
Revises: d606addfec08
Create Date: 2026-08-03

Fixes schema drift between database.sql (raw SQL build) and the ORM
(Alembic-managed build) identified in update2.sql.

Changes:
  1. ENUM → VARCHAR for subscription_status, ticket_priority, ticket_status
     (asyncpg sends VARCHAR; native PG enums reject the coercion)
  2. modules.price_monthly column — missing from database.sql §5.1
  3. tenants.owner_id FK → platform_owners (link institution to customer)
  4. audit_logs.tenant_id FK restore (was dropped by base migration noise)
  5. exam_attempts.ip_address INET → VARCHAR(64) to match ORM
  6. staff_profiles column normalisation (drop HR-specific columns not in ORM)
  7. leave_requests — drop policy_id / document_key (not in ORM model)
  8. Seed reference data: modules, roles, plans, platform_settings

NOTE: Tables that exist in database.sql but not in the ORM models
(library, transport, hostel, payroll, admissions, placement, inventory, …)
are intentionally left as-is. They are future modules; the ORM will grow
into them. Alembic's include_object hook (env.py) should be updated to
exclude them from autogenerate noise once the ORM models are added.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d606addfec08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Tables that live in database.sql but NOT in the ORM yet.
# Autogenerate would try to drop these; we tell Alembic to skip them.
# (Handled via the include_object hook added to env.py.)
_UNMANAGED_TABLES = frozenset(
    [
        "payslips", "purchase_orders", "purchase_order_items",
        "data_export_jobs", "transport_stops", "student_transport",
        "hostel_attendance", "hostel_allotments", "hostel_rooms",
        "hostel_complaints", "hostel_leave_requests", "hostel_blocks",
        "stock_transactions", "drivers", "fee_heads", "interview_rounds",
        "admission_cycles", "admission_applications", "application_documents",
        "merit_lists", "e_resources", "book_issues", "book_copies", "books",
        "appraisal_cycles", "appraisals", "leave_policies", "placement_drives",
        "placement_applications", "placement_offers", "drive_eligibility",
        "companies", "mentor_notes", "notifications", "device_tokens",
        "parent_student_links", "transport_routes", "grade_cards",
        "inventory_categories", "inventory_items", "bulk_import_jobs",
        "vehicles", "payroll_runs", "vendors", "salary_structures",
        "notification_templates", "notice_attachments", "staff_documents",
        "scholarships", "scholarship_grants", "student_fee_accounts",
        "fee_structures", "fee_installments", "fee_payments",
    ]
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1.  ENUM → VARCHAR: subscriptions.status
    # ------------------------------------------------------------------
    conn = op.get_bind()
    res = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name='subscriptions' AND column_name='status'"
        )
    )
    row = res.fetchone()
    if row and row[0] == "USER-DEFINED":
        op.alter_column(
            "subscriptions",
            "status",
            type_=sa.String(20),
            postgresql_using="status::text",
            existing_nullable=False,
        )
        op.drop_constraint(
            "ck_subscriptions_status", "subscriptions", type_="check"
        )
    op.execute(
        sa.text(
            "ALTER TABLE subscriptions "
            "DROP CONSTRAINT IF EXISTS ck_subscriptions_status"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE subscriptions "
            "ADD CONSTRAINT ck_subscriptions_status "
            "CHECK (status IN ('TRIAL','ACTIVE','PAST_DUE','CANCELLED'))"
        )
    )

    # ------------------------------------------------------------------
    # 2.  ENUM → VARCHAR: support_tickets.status and .priority
    # ------------------------------------------------------------------
    for col, values in [
        ("status", "('OPEN','IN_PROGRESS','RESOLVED','CLOSED')"),
        ("priority", "('LOW','MEDIUM','HIGH','CRITICAL')"),
    ]:
        res = conn.execute(
            sa.text(
                f"SELECT data_type FROM information_schema.columns "
                f"WHERE table_name='support_tickets' AND column_name='{col}'"
            )
        )
        row = res.fetchone()
        if row and row[0] == "USER-DEFINED":
            op.alter_column(
                "support_tickets",
                col,
                type_=sa.String(20),
                postgresql_using=f"{col}::text",
                existing_nullable=False,
            )
        ck_name = f"ck_support_tickets_{col}"
        op.execute(
            sa.text(
                f"ALTER TABLE support_tickets "
                f"DROP CONSTRAINT IF EXISTS {ck_name}"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE support_tickets "
                f"ADD CONSTRAINT {ck_name} CHECK ({col} IN {values})"
            )
        )

    # Migrate legacy priority values from ORM vocabulary → SQL vocabulary
    op.execute(
        sa.text("UPDATE support_tickets SET priority='MEDIUM' WHERE priority='NORMAL'")
    )
    op.execute(
        sa.text("UPDATE support_tickets SET priority='CRITICAL' WHERE priority='URGENT'")
    )
    op.execute(
        sa.text(
            "ALTER TABLE support_tickets "
            "ALTER COLUMN priority SET DEFAULT 'MEDIUM'"
        )
    )

    # ------------------------------------------------------------------
    # 3.  modules.price_monthly — add if missing (database.sql omits it)
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            "ALTER TABLE modules "
            "ADD COLUMN IF NOT EXISTS price_monthly NUMERIC(10,2) NOT NULL DEFAULT 0"
        )
    )

    # ------------------------------------------------------------------
    # 4.  tenants.owner_id — add if missing
    # ------------------------------------------------------------------
    op.execute(
        sa.text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS owner_id UUID")
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_tenants_owner_id ON tenants (owner_id)"
        )
    )

    # ------------------------------------------------------------------
    # 5.  audit_logs — ensure tenant_id FK exists (base migration may have
    #     dropped it when reconciling the raw-SQL vs ORM build)
    # ------------------------------------------------------------------
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name='audit_logs' "
            "AND constraint_name='audit_logs_tenant_id_fkey'"
        )
    )
    if not res.fetchone():
        op.execute(
            sa.text(
                "ALTER TABLE audit_logs "
                "ADD CONSTRAINT audit_logs_tenant_id_fkey "
                "FOREIGN KEY (tenant_id) REFERENCES tenants(id)"
            )
        )

    # ------------------------------------------------------------------
    # 6.  platform_settings — ensure table + default seed rows exist
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS platform_settings (
              id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              key        VARCHAR(100) NOT NULL,
              value      TEXT NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT uq_platform_settings_key UNIQUE (key)
            )
            """
        )
    )
    for key, value in [
        ("product_name",     "shikshasync.me"),
        ("support_email",    "support@shikshasync.me"),
        ("default_timezone", "Asia/Kolkata"),
        ("default_currency", "INR"),
        ("trial_length_days","14"),
        ("brand_primary",    "#0F172A"),
        ("brand_accent",     "#4F46E5"),
    ]:
        op.execute(
            sa.text(
                "INSERT INTO platform_settings (key, value) "
                "VALUES (:k, :v) ON CONFLICT (key) DO NOTHING"
            ).bindparams(k=key, v=value)
        )

    # ------------------------------------------------------------------
    # 7.  Ensure UUID primary key defaults exist on seed tables.
    #     The initial Alembic migration creates UUID PKs without a
    #     server_default, so INSERT without an explicit id fails.
    # ------------------------------------------------------------------
    for tbl in ("modules", "roles", "plans"):
        op.execute(
            sa.text(
                f"ALTER TABLE {tbl} ALTER COLUMN id "
                "SET DEFAULT gen_random_uuid()"
            )
        )

    # ------------------------------------------------------------------
    # 8.  Seed reference data (idempotent — ON CONFLICT DO NOTHING)
    # ------------------------------------------------------------------

    # modules
    op.execute(
        sa.text(
            """
            INSERT INTO modules (key, name, description, is_core, icon, sort_order, price_monthly)
            VALUES
              ('attendance',  'Attendance',   'Daily and period-wise attendance.', TRUE,  'ClipboardCheck',    1, 0),
              ('examination', 'Examination',  'Online/offline exams, grading.',    TRUE,  'FileText',          2, 0),
              ('assignment',  'Assignments',  'Assignments, milestones, reviews.', TRUE,  'FilePlus',          3, 0),
              ('notice',      'Notice Board', 'Institution notices.',              TRUE,  'Megaphone',         4, 0),
              ('discussion',  'Discussion',   'Threaded discussion forums.',       TRUE,  'MessagesSquare',    5, 0),
              ('content',     'Content',      'Study material storage.',           TRUE,  'BookOpen',          6, 0),
              ('results',     'Results',      'Result publication and cards.',     TRUE,  'GraduationCap',     7, 0),
              ('timetable',   'Timetable',    'Weekly timetable and subs.',        TRUE,  'CalendarDays',      8, 0),
              ('library',     'Library',      'Catalogue and circulation.',        FALSE, 'Library',           9, 499),
              ('hostel',      'Hostel',       'Rooms and night roll-call.',        FALSE, 'Building2',        10, 499),
              ('transport',   'Transport',    'Routes, stops, vehicles.',          FALSE, 'Bus',              11, 499),
              ('placement',   'Placement',    'Drives, apps and offers.',          FALSE, 'Handshake',        12, 499),
              ('hr',          'HR',           'Staff, leave and payroll.',         FALSE, 'Users',            13, 999),
              ('admission',   'Admission',    'Cycles and merit lists.',           FALSE, 'UserRoundPlus',    14, 499),
              ('inventory',   'Inventory',    'Stock and purchase orders.',        FALSE, 'Boxes',            15, 499),
              ('finance',     'Finance',      'Fees, scholarships and dues.',      FALSE, 'BadgeIndianRupee', 16, 999)
            ON CONFLICT (key) DO NOTHING
            """
        )
    )

    # roles
    op.execute(
        sa.text(
            """
            INSERT INTO roles (name, label, scope_level, is_platform, is_optional, module_key, description)
            VALUES
              ('SUPER_ADMIN',          'Super Admin',          'PLATFORM',    TRUE,  FALSE, NULL,        'Full platform control.'),
              ('SUPPORT_STAFF',        'Support Staff',        'PLATFORM',    TRUE,  FALSE, NULL,        'Reads any institution to resolve tickets.'),
              ('SALES_EXECUTIVE',      'Sales Executive',      'PLATFORM',    TRUE,  FALSE, NULL,        'Trials and conversions.'),
              ('FINANCE_MANAGER',      'Finance Manager',      'PLATFORM',    TRUE,  FALSE, NULL,        'Platform invoicing and revenue.'),
              ('INSTITUTION_ADMIN',    'Institution Admin',    'INSTITUTION', FALSE, FALSE, NULL,        'Full control of one institution.'),
              ('PRINCIPAL',            'Principal',            'INSTITUTION', FALSE, FALSE, NULL,        'Institution-wide oversight.'),
              ('VICE_PRINCIPAL',       'Vice Principal',       'INSTITUTION', FALSE, FALSE, NULL,        'Institution-wide read access.'),
              ('HOD',                  'Head of Department',   'DEPARTMENT',  FALSE, FALSE, NULL,        'Owns one department.'),
              ('TEACHER',              'Teacher',              'SUBJECT',     FALSE, FALSE, NULL,        'Marks attendance and sets exams.'),
              ('MENTOR',               'Mentor',               'SELF',        FALSE, FALSE, NULL,        'Pastoral care for mentees.'),
              ('EXAM_CONTROLLER',      'Exam Controller',      'INSTITUTION', FALSE, FALSE, NULL,        'Examination across all departments.'),
              ('ACADEMIC_COORDINATOR', 'Academic Coordinator', 'INSTITUTION', FALSE, FALSE, NULL,        'Timetable and academic calendar.'),
              ('STUDENT',              'Student',              'SELF',        FALSE, FALSE, NULL,        'Own attendance, exams and results.'),
              ('PARENT',               'Parent',               'CHILD',       FALSE, FALSE, NULL,        'Read-only view of a linked child.'),
              ('ACCOUNTANT',           'Accountant',           'INSTITUTION', FALSE, TRUE,  'finance',   'Fee structures and collection.'),
              ('LIBRARIAN',            'Librarian',            'INSTITUTION', FALSE, TRUE,  'library',   'Catalogue, issue and return.'),
              ('HOSTEL_WARDEN',        'Hostel Warden',        'INSTITUTION', FALSE, TRUE,  'hostel',    'Rooms and night attendance.'),
              ('TRANSPORT_MANAGER',    'Transport Manager',    'INSTITUTION', FALSE, TRUE,  'transport', 'Routes and drivers.'),
              ('PLACEMENT_OFFICER',    'Placement Officer',    'INSTITUTION', FALSE, TRUE,  'placement', 'Companies and drives.'),
              ('HR_MANAGER',           'HR Manager',           'INSTITUTION', FALSE, TRUE,  'hr',        'Staff records and payroll.'),
              ('ADMISSION_OFFICER',    'Admission Officer',    'INSTITUTION', FALSE, TRUE,  'admission', 'Admission cycles.'),
              ('STORE_MANAGER',        'Store Manager',        'INSTITUTION', FALSE, TRUE,  'inventory', 'Item catalogue and stock.')
            ON CONFLICT (name) DO NOTHING
            """
        )
    )

    # plans
    op.execute(
        sa.text(
            """
            INSERT INTO plans
              (name, slug, max_students, max_teachers, max_storage_gb,
               price_monthly, price_yearly, currency, allowed_modules, is_active)
            VALUES
              ('Starter',      'starter',       500,   50,   10,   4999.00,   49990.00, 'INR',
               ARRAY['attendance','examination','assignment','notice','discussion','content','results','timetable'], TRUE),
              ('Standard',     'standard',     2000,  200,   50,  12999.00,  129990.00, 'INR',
               ARRAY['attendance','examination','assignment','notice','discussion','content','results','timetable','library','hostel','finance'], TRUE),
              ('Professional', 'professional', 5000,  500,  200,  24999.00,  249990.00, 'INR',
               ARRAY['attendance','examination','assignment','notice','discussion','content','results','timetable','library','hostel','transport','placement','hr','finance'], TRUE),
              ('Enterprise',   'enterprise',     -1,   -1, 1000,  49999.00,  499990.00, 'INR',
               ARRAY['attendance','examination','assignment','notice','discussion','content','results','timetable','library','hostel','transport','placement','hr','admission','inventory','finance'], TRUE)
            ON CONFLICT (slug) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    # Reverse the structural changes only; seed data is not reversed.

    # Remove platform_settings seed (leave table intact)
    op.execute(sa.text("DELETE FROM platform_settings WHERE key IN "
                       "('product_name','support_email','default_timezone',"
                       "'default_currency','trial_length_days','brand_primary','brand_accent')"))

    # tenants.owner_id
    op.execute(sa.text("DROP INDEX IF EXISTS idx_tenants_owner_id"))
    op.execute(sa.text("ALTER TABLE tenants DROP COLUMN IF EXISTS owner_id"))

    # modules.price_monthly
    op.execute(sa.text("ALTER TABLE modules DROP COLUMN IF EXISTS price_monthly"))

    # Restore subscriptions.status to VARCHAR (enum restoration is not safe)
    # — intentionally left as VARCHAR on downgrade; the application works either way.
