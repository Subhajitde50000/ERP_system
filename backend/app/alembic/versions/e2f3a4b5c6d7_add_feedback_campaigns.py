"""add feedback campaigns (campaigns, targets, responses)

Revision ID: e2f3a4b5c6d7
Revises: d9e8f7a6b5c4
Create Date: 2026-09-30

Introduces the teacher-feedback campaign subsystem:

* ``campaign_status``           — PG enum (DRAFT, ACTIVE, CLOSED).
* ``feedback_campaigns``        — campaign created by Admin / Principal.
* ``feedback_campaign_targets`` — (teacher, subject?, class?) tuples scoped
                                  to a campaign.
* ``feedback_responses``        — one row per student · target · campaign.

All DDL statements use ``IF NOT EXISTS`` so the migration is idempotent and
safe to run against a database that already received
``database/feedback_campaigns_migration.sql``.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d9e8f7a6b5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. PG enum type
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_status') THEN
                CREATE TYPE campaign_status AS ENUM ('DRAFT', 'ACTIVE', 'CLOSED');
            END IF;
        END$$
        """
    )

    # ------------------------------------------------------------------
    # 2. feedback_campaigns
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_campaigns (
            id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID            NOT NULL REFERENCES tenants(id),
            title           VARCHAR(200)    NOT NULL,
            description     TEXT,
            starts_at       TIMESTAMPTZ     NOT NULL,
            ends_at         TIMESTAMPTZ     NOT NULL,
            allow_anonymous BOOLEAN         NOT NULL DEFAULT TRUE,
            status          campaign_status NOT NULL DEFAULT 'DRAFT',
            created_by      UUID            NOT NULL REFERENCES users(id),
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            closed_at       TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_campaigns_tenant_id "
        "ON feedback_campaigns (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_campaigns_status "
        "ON feedback_campaigns (status)"
    )

    # ------------------------------------------------------------------
    # 3. feedback_campaign_targets
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_campaign_targets (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            campaign_id UUID NOT NULL REFERENCES feedback_campaigns(id) ON DELETE CASCADE,
            teacher_id  UUID NOT NULL REFERENCES users(id),
            subject_id  UUID REFERENCES subjects(id),
            class_id    UUID REFERENCES classes(id),
            CONSTRAINT uq_fct__campaign_teacher_subject
                UNIQUE (campaign_id, teacher_id, subject_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fct_campaign_id "
        "ON feedback_campaign_targets (campaign_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fct_teacher_id "
        "ON feedback_campaign_targets (teacher_id)"
    )

    # ------------------------------------------------------------------
    # 4. feedback_responses
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_responses (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            campaign_id       UUID        NOT NULL REFERENCES feedback_campaigns(id)        ON DELETE CASCADE,
            target_id         UUID        NOT NULL REFERENCES feedback_campaign_targets(id) ON DELETE CASCADE,
            student_id        UUID        NOT NULL REFERENCES users(id),
            teaching_clarity  SMALLINT,
            subject_knowledge SMALLINT,
            interaction       SMALLINT,
            overall           SMALLINT,
            comment           TEXT,
            submitted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_fr__campaign_target_student
                UNIQUE (campaign_id, target_id, student_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fr_campaign_id "
        "ON feedback_responses (campaign_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fr_target_id "
        "ON feedback_responses (target_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedback_responses")
    op.execute("DROP TABLE IF EXISTS feedback_campaign_targets")
    op.execute("DROP TABLE IF EXISTS feedback_campaigns")
    op.execute("DROP TYPE IF EXISTS campaign_status")
