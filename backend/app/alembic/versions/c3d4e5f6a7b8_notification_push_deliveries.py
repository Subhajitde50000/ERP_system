"""notification push deliveries (outbox + device_tokens index)

Revision ID: c3d4e5f6a7b8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-03

Adds the delivery layer for cross-platform (FCM Android/iOS/web) push:

* ``idx_device_tokens_user_active`` — partial index on the existing
  ``device_tokens`` registry used by the push enqueue path.
* ``notification_deliveries`` — durable push outbox drained by the FCM
  worker (NotificationService.deliver_pending).

Statements are written idempotently (IF NOT EXISTS) so the same upgrade can
run against a database that already received database/notification_push_update.sql.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fast path used when a notification is broadcast to many recipients.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_device_tokens_user_active
            ON device_tokens (user_id)
            WHERE is_active = TRUE
        """
    )

    # Durable push outbox (idempotent for databases that already applied the
    # plain-SQL update file).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_deliveries (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            notification_id    UUID NOT NULL REFERENCES notifications(id)    ON DELETE CASCADE,
            user_id            UUID NOT NULL REFERENCES users(id)            ON DELETE CASCADE,
            device_token_id    UUID NOT NULL REFERENCES device_tokens(id)    ON DELETE CASCADE,
            platform           VARCHAR(10) NOT NULL,
            status             VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            attempts           SMALLINT    NOT NULL DEFAULT 0,
            last_error         TEXT,
            next_attempt_at    TIMESTAMPTZ,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at            TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notif_deliveries_pending
            ON notification_deliveries (status, next_attempt_at)
            WHERE status = 'PENDING'
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notif_deliveries_notification "
        "ON notification_deliveries (notification_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notif_deliveries_user "
        "ON notification_deliveries (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_deliveries")
    op.execute("DROP INDEX IF EXISTS idx_device_tokens_user_active")
