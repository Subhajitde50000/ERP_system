"""mentor_scopes — student / team / class mentor assignments + mentor notes

Revision ID: e6a7b8c9d0e1
Revises: d9e8f7a6b5c4
Create Date: 2026-09-24

Mirrors ``database/update_mentor_scopes.sql``.

* ``mentor_assignments`` gains ``scope_type`` (STUDENT | TEAM | CLASS),
  nullable ``student_id`` and new ``team_id`` / ``class_id`` targets guarded
  by a CHECK constraint.
* Partial unique indexes enforce "one ACTIVE mentor per student / team /
  class per academic year" while a mentor may hold any number of assignments.
* ``mentor_notes`` (previously an unmanaged legacy table) becomes ORM-managed;
  it is created when missing so Alembic-only databases receive it.

Every step is idempotent so the revision can be applied to a database that
already received the raw SQL update.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6a7b8c9d0e1"
down_revision: Union[str, None] = "d9e8f7a6b5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. scope columns ────────────────────────────────────────────────────
    if not _column_exists(conn, "mentor_assignments", "scope_type"):
        op.add_column(
            "mentor_assignments",
            sa.Column("scope_type", sa.String(10), nullable=False, server_default="STUDENT"),
        )
    if not _column_exists(conn, "mentor_assignments", "team_id"):
        op.add_column(
            "mentor_assignments",
            sa.Column(
                "team_id",
                sa.UUID(),
                sa.ForeignKey("project_groups.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
    if not _column_exists(conn, "mentor_assignments", "class_id"):
        op.add_column(
            "mentor_assignments",
            sa.Column(
                "class_id",
                sa.UUID(),
                sa.ForeignKey("classes.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
    op.alter_column("mentor_assignments", "student_id", existing_type=sa.UUID(), nullable=True)
    op.execute("UPDATE mentor_assignments SET scope_type = 'STUDENT' WHERE scope_type IS NULL OR scope_type = ''")

    op.execute("ALTER TABLE mentor_assignments DROP CONSTRAINT IF EXISTS ck_mentor_assignments__scope_type")
    op.create_check_constraint(
        "ck_mentor_assignments__scope_type",
        "mentor_assignments",
        "scope_type IN ('STUDENT', 'TEAM', 'CLASS')",
    )
    op.execute("ALTER TABLE mentor_assignments DROP CONSTRAINT IF EXISTS ck_mentor_assignments__scope_target")
    op.create_check_constraint(
        "ck_mentor_assignments__scope_target",
        "mentor_assignments",
        "(scope_type = 'STUDENT' AND student_id IS NOT NULL AND team_id IS NULL AND class_id IS NULL) "
        "OR (scope_type = 'TEAM' AND team_id IS NOT NULL AND student_id IS NULL AND class_id IS NULL) "
        "OR (scope_type = 'CLASS' AND class_id IS NOT NULL AND student_id IS NULL AND team_id IS NULL)",
    )

    # ── 2. one active mentor per target / year ──────────────────────────────
    op.execute("DROP INDEX IF EXISTS uq_mentor_assignments__tenant_student_year_active")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mentor_assignments__tenant_student_year_active "
        "ON mentor_assignments (tenant_id, student_id, academic_year_id) "
        "WHERE is_active = TRUE AND student_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mentor_assignments__tenant_team_year_active "
        "ON mentor_assignments (tenant_id, team_id, academic_year_id) "
        "WHERE is_active = TRUE AND team_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mentor_assignments__tenant_class_year_active "
        "ON mentor_assignments (tenant_id, class_id, academic_year_id) "
        "WHERE is_active = TRUE AND class_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mentor_assignments_team_id "
        "ON mentor_assignments (team_id, academic_year_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mentor_assignments_class_id "
        "ON mentor_assignments (class_id, academic_year_id)"
    )

    # ── 3. mentor_notes becomes ORM-managed ─────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mentor_notes (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          mentor_id     UUID NOT NULL REFERENCES users(id),
          student_id    UUID NOT NULL REFERENCES users(id),
          assignment_id UUID NOT NULL REFERENCES mentor_assignments(id) ON DELETE CASCADE,
          body          TEXT NOT NULL,
          is_private    BOOLEAN NOT NULL DEFAULT TRUE,
          note_date     DATE NOT NULL DEFAULT CURRENT_DATE,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentor_notes_assignment_id ON mentor_notes (assignment_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentor_notes_student_id ON mentor_notes (student_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentor_notes_mentor_id ON mentor_notes (mentor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentor_notes_tenant_id ON mentor_notes (tenant_id)")


def downgrade() -> None:
    # Team / class rows cannot survive a NOT NULL student_id; remove them first.
    op.execute("DELETE FROM mentor_notes WHERE assignment_id IN (SELECT id FROM mentor_assignments WHERE scope_type <> 'STUDENT')")
    op.execute("DELETE FROM mentor_assignments WHERE scope_type <> 'STUDENT'")
    op.execute("DROP INDEX IF EXISTS idx_mentor_assignments_class_id")
    op.execute("DROP INDEX IF EXISTS idx_mentor_assignments_team_id")
    op.execute("DROP INDEX IF EXISTS uq_mentor_assignments__tenant_class_year_active")
    op.execute("DROP INDEX IF EXISTS uq_mentor_assignments__tenant_team_year_active")
    op.execute("DROP INDEX IF EXISTS uq_mentor_assignments__tenant_student_year_active")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mentor_assignments__tenant_student_year_active "
        "ON mentor_assignments (tenant_id, student_id, academic_year_id) WHERE is_active = TRUE"
    )
    op.execute("ALTER TABLE mentor_assignments DROP CONSTRAINT IF EXISTS ck_mentor_assignments__scope_target")
    op.execute("ALTER TABLE mentor_assignments DROP CONSTRAINT IF EXISTS ck_mentor_assignments__scope_type")
    op.alter_column("mentor_assignments", "student_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("mentor_assignments", "class_id")
    op.drop_column("mentor_assignments", "team_id")
    op.drop_column("mentor_assignments", "scope_type")
    # mentor_notes is left in place: it pre-dates this revision in raw-SQL deployments.
