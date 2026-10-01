-- Active: 1785483683689@@127.0.0.1@5432@erp_db
-- =============================================================================
-- Database update script — Teacher Feedback Campaign feature
--
-- Applies:   feedback_campaigns, feedback_campaign_targets, feedback_responses
-- Dialect:   PostgreSQL 14+
-- Idempotent: YES — every statement uses IF NOT EXISTS / DO $$ guards so this
--             script can be re-run safely on a database that already received
--             (part of) these changes.
--
-- Companion files:
--   backend/app/models/feedback.py
--   backend/app/alembic/versions/e2f3a4b5c6d7_add_feedback_campaigns.py
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Enum type: campaign_status
-- ---------------------------------------------------------------------------
DO $$

BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_status') THEN
        CREATE TYPE campaign_status AS ENUM ('DRAFT', 'ACTIVE', 'CLOSED');
    END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 2. feedback_campaigns
--    One row per campaign created by an Institution Admin / Principal.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback_campaigns (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID            NOT NULL REFERENCES tenants(id),
    title           VARCHAR(200)    NOT NULL,
    description     TEXT,
    starts_at       TIMESTAMPTZ     NOT NULL,
    ends_at         TIMESTAMPTZ     NOT NULL,
    -- If FALSE the teacher can see which student submitted each response.
    allow_anonymous BOOLEAN         NOT NULL DEFAULT TRUE,
    status          campaign_status NOT NULL DEFAULT 'DRAFT',
    created_by      UUID            NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ                             -- set on auto-close
);

CREATE INDEX IF NOT EXISTS idx_feedback_campaigns_tenant_id
    ON feedback_campaigns (tenant_id);

CREATE INDEX IF NOT EXISTS idx_feedback_campaigns_status
    ON feedback_campaigns (status);

-- ---------------------------------------------------------------------------
-- 3. feedback_campaign_targets
--    Each (teacher, optional subject, optional class) tuple in a campaign.
--    NULL subject_id means the rating covers the teacher overall.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback_campaign_targets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES feedback_campaigns(id) ON DELETE CASCADE,
    teacher_id  UUID NOT NULL REFERENCES users(id),
    subject_id  UUID          REFERENCES subjects(id),   -- NULL = teacher overall
    class_id    UUID          REFERENCES classes(id),    -- NULL = all classes
    CONSTRAINT uq_fct__campaign_teacher_subject
        UNIQUE (campaign_id, teacher_id, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_fct_campaign_id
    ON feedback_campaign_targets (campaign_id);

CREATE INDEX IF NOT EXISTS idx_fct_teacher_id
    ON feedback_campaign_targets (teacher_id);

-- ---------------------------------------------------------------------------
-- 4. feedback_responses
--    One row per student · target · campaign.
--    student_id is always stored for deduplication; teacher-facing API hides it
--    when the parent campaign has allow_anonymous = TRUE.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback_responses (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id       UUID        NOT NULL
                          REFERENCES feedback_campaigns(id)        ON DELETE CASCADE,
    target_id         UUID        NOT NULL
                          REFERENCES feedback_campaign_targets(id) ON DELETE CASCADE,
    student_id        UUID        NOT NULL REFERENCES users(id),
    -- Numeric rating dimensions (1–5); nullable for partial submissions.
    teaching_clarity  SMALLINT,
    subject_knowledge SMALLINT,
    interaction       SMALLINT,
    overall           SMALLINT,
    comment           TEXT,
    submitted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fr__campaign_target_student
        UNIQUE (campaign_id, target_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_fr_campaign_id
    ON feedback_responses (campaign_id);

CREATE INDEX IF NOT EXISTS idx_fr_target_id
    ON feedback_responses (target_id);

-- ---------------------------------------------------------------------------
-- 5. Permissions & ownership (ensures application user erp_user has access)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'erp_user') THEN
        ALTER TABLE feedback_campaigns OWNER TO erp_user;
        ALTER TABLE feedback_campaign_targets OWNER TO erp_user;
        ALTER TABLE feedback_responses OWNER TO erp_user;
        GRANT ALL ON feedback_campaigns TO erp_user;
        GRANT ALL ON feedback_campaign_targets TO erp_user;
        GRANT ALL ON feedback_responses TO erp_user;
    END IF;
END$$;

