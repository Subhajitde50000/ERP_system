-- ═══════════════════════════════════════════════════════════════════════════
--  ERP Notification Push Update
-- ─────────────────────────────────────────────────────────────────────────────
--  Adds the delivery layer that makes the notification system real-world
--  usable with Firebase Cloud Messaging (Android / iOS / web push):
--
--    1. device_tokens        already exists (registration registry) — this
--       update adds the partial index the push enqueue path queries.
--    2. notification_deliveries — NEW durable push outbox. When an in-app
--       notification row is created, one row per live device token is
--       enqueued here; the background worker (scheduler_service →
--       NotificationService.deliver_pending) drains it through FCM v1 with
--       retries/backoff. Keeping the queue in SQL makes delivery survive
--       worker restarts and lets several API workers share the load.
--
--  Idempotent: every statement is IF NOT EXISTS, so it can be re-run on a
--  database that already contains the objects (e.g. a fresh install that
--  imported database/database.sql, which now includes these objects too).
--
--  Apply with:
--      psql -U erp_user -d erp_db -f database/notification_push_update.sql
-- ═══════════════════════════════════════════════════════════════════════════

-- 1. Fast path for "all live tokens of these users" when a notification is
--    broadcast to many recipients in one INSERT … SELECT.
CREATE INDEX IF NOT EXISTS idx_device_tokens_user_active
    ON device_tokens (user_id)
    WHERE is_active = TRUE;

-- 2. Durable push outbox.
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id    UUID NOT NULL REFERENCES notifications(id)    ON DELETE CASCADE,
    user_id            UUID NOT NULL REFERENCES users(id)            ON DELETE CASCADE,
    device_token_id    UUID NOT NULL REFERENCES device_tokens(id)    ON DELETE CASCADE,
    platform           VARCHAR(10) NOT NULL,              -- android | ios | web
    status             VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING|SENT|FAILED|SKIPPED
    attempts           SMALLINT    NOT NULL DEFAULT 0,
    last_error         TEXT,
    next_attempt_at    TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at            TIMESTAMPTZ
);

-- Worker scan: only pending rows whose backoff window has elapsed.
CREATE INDEX IF NOT EXISTS idx_notif_deliveries_pending
    ON notification_deliveries (status, next_attempt_at)
    WHERE status = 'PENDING';

-- Fast lookup when a notification row is deleted / audited.
CREATE INDEX IF NOT EXISTS idx_notif_deliveries_notification
    ON notification_deliveries (notification_id);

CREATE INDEX IF NOT EXISTS idx_notif_deliveries_user
    ON notification_deliveries (user_id);

-- ── Optional (recommended) sanity constraint ---------------------------------
-- Uncomment if you want the database to reject a bad status outright:
--
-- ALTER TABLE notification_deliveries DROP CONSTRAINT IF EXISTS chk_notif_delivery_status;
-- ALTER TABLE notification_deliveries
--     ADD CONSTRAINT chk_notif_delivery_status
--     CHECK (status IN ('PENDING', 'SENT', 'FAILED', 'SKIPPED'));
