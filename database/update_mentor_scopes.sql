-- ============================================================================
--  UPDATE — Mentor scopes (student / team / class) + mentor notes
-- ============================================================================
--
--  Companion to Alembic revision  e6a7b8c9d0e1_mentor_scopes  and to the
--  updated table definition in database/database.sql.  Apply exactly ONE of:
--
--    * Alembic-managed deployments:   cd backend && alembic upgrade head
--    * Raw-SQL deployments:           psql -U erp_user -d erp_db -f database/update_mentor_scopes.sql
--
--  Every statement is idempotent, so re-running the file is a safe no-op.
--
--  What changes
--  ------------
--  1. mentor_assignments gains a scope: STUDENT (existing behaviour), TEAM
--     (a project_groups row) or CLASS (a classes row).  student_id becomes
--     nullable; team_id / class_id are added; a CHECK constraint guarantees
--     exactly one target column is set for the declared scope_type.
--  2. Business rules enforced by partial unique indexes:
--       - one ACTIVE mentor per student  / academic year   (already existed)
--       - one ACTIVE mentor per team     / academic year   (new)
--       - one ACTIVE mentor per class    / academic year   (new)
--     A mentor can hold any number of assignments.
--  3. mentor_notes (the mentor's private mentoring log) is created if the
--     database was bootstrapped without it, and gains an updated_at trigger-free
--     default so the API can maintain it.
--
--  Existing rows are untouched: they all carry student_id and receive
--  scope_type = 'STUDENT' through the column default.
-- ============================================================================

BEGIN;

-- ── 1. Scope columns ────────────────────────────────────────────────────────
ALTER TABLE mentor_assignments
  ADD COLUMN IF NOT EXISTS scope_type VARCHAR(10) NOT NULL DEFAULT 'STUDENT',
  ADD COLUMN IF NOT EXISTS team_id    UUID REFERENCES project_groups(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS class_id   UUID REFERENCES classes(id)        ON DELETE CASCADE;

ALTER TABLE mentor_assignments ALTER COLUMN student_id DROP NOT NULL;

-- Legacy rows predate scope_type; make the invariant explicit before the CHECK.
UPDATE mentor_assignments SET scope_type = 'STUDENT' WHERE scope_type IS NULL OR scope_type = '';

ALTER TABLE mentor_assignments DROP CONSTRAINT IF EXISTS ck_mentor_assignments__scope_type;
ALTER TABLE mentor_assignments
  ADD CONSTRAINT ck_mentor_assignments__scope_type CHECK (scope_type IN ('STUDENT', 'TEAM', 'CLASS'));

ALTER TABLE mentor_assignments DROP CONSTRAINT IF EXISTS ck_mentor_assignments__scope_target;
ALTER TABLE mentor_assignments
  ADD CONSTRAINT ck_mentor_assignments__scope_target CHECK (
       (scope_type = 'STUDENT' AND student_id IS NOT NULL AND team_id IS NULL    AND class_id IS NULL)
    OR (scope_type = 'TEAM'    AND team_id IS NOT NULL    AND student_id IS NULL AND class_id IS NULL)
    OR (scope_type = 'CLASS'   AND class_id IS NOT NULL   AND student_id IS NULL AND team_id IS NULL)
  );

-- ── 2. One active mentor per target / year ──────────────────────────────────
DROP INDEX IF EXISTS uq_mentor_assignments__tenant_student_year_active;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mentor_assignments__tenant_student_year_active
  ON mentor_assignments (tenant_id, student_id, academic_year_id)
  WHERE is_active = TRUE AND student_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mentor_assignments__tenant_team_year_active
  ON mentor_assignments (tenant_id, team_id, academic_year_id)
  WHERE is_active = TRUE AND team_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mentor_assignments__tenant_class_year_active
  ON mentor_assignments (tenant_id, class_id, academic_year_id)
  WHERE is_active = TRUE AND class_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mentor_assignments_team_id  ON mentor_assignments (team_id, academic_year_id);
CREATE INDEX IF NOT EXISTS idx_mentor_assignments_class_id ON mentor_assignments (class_id, academic_year_id);

-- ── 3. Mentor notes (private mentoring log) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS mentor_notes (
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

CREATE INDEX IF NOT EXISTS idx_mentor_notes_assignment_id ON mentor_notes (assignment_id);
CREATE INDEX IF NOT EXISTS idx_mentor_notes_student_id    ON mentor_notes (student_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mentor_notes_mentor_id     ON mentor_notes (mentor_id);
CREATE INDEX IF NOT EXISTS idx_mentor_notes_tenant_id     ON mentor_notes (tenant_id);

COMMIT;
