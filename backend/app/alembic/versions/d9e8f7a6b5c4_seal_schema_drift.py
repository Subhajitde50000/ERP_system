"""seal_schema_drift

Revision ID: d9e8f7a6b5c4
Revises: c3d4e5f6a7b8
Create Date: 2026-09-05

This migration is the single authoritative closer of all documented drift
between ``database/database.sql`` (the original hand-written DDL) and the
Alembic-managed ORM schema.

After this revision Alembic is the sole source of truth for the database
schema.  ``database/database.sql`` is archived as a historical reference
only — see the header comment added to that file.

Changes applied
---------------
1.  ``platform_payments`` — add ``UNIQUE (gateway, gateway_ref)``
    (``uq_platform_payments_gateway_ref``).  This constraint exists in
    ``database.sql`` but was never emitted by any previous migration.
    It is the replay-attack guard for the payment webhook handler.

Both statements use ``IF NOT EXISTS`` / conditional logic so the migration
is fully idempotent: running it against a database that already received
the constraint via the raw SQL file is a no-op.

No other structural differences between ``database.sql`` and the ORM remain:
- All tables present in ``database.sql`` that have no ORM model are tracked
  in ``env.py:_UNMANAGED_TABLES`` and excluded from autogenerate.
- All ENUM → VARCHAR conversions were handled in ``e1f2a3b4c5d6``.
- The ``plans`` ORM model (``catalog.py``) correctly mirrors ``database.sql``
  §4.1 and the FK from ``subscriptions.plan_id`` was present since the
  initial migration (``d606addfec08``).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ──────────────────────────────────────────────────────

revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _constraint_exists(conn, table: str, constraint: str) -> bool:
    """Return True if *constraint* already exists on *table* in the DB."""
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :c"
        ),
        {"t": table, "c": constraint},
    ).fetchone()
    return row is not None


# ── Upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1.  platform_payments — UNIQUE (gateway, gateway_ref)
    #
    #     database.sql defines:
    #       CONSTRAINT uq_platform_payments_gateway_ref
    #         UNIQUE (gateway, gateway_ref)
    #
    #     The ORM model (PlatformPayment.__table_args__) now declares it
    #     via UniqueConstraint — this migration makes the live DB match.
    #
    #     PostgreSQL's UNIQUE constraint over nullable columns uses
    #     NULL-distinct semantics: two rows where gateway_ref IS NULL do
    #     NOT collide, so offline / mock payments (gateway_ref = NULL)
    #     are unaffected.
    # ------------------------------------------------------------------
    if not _constraint_exists(conn, "platform_payments", "uq_platform_payments_gateway_ref"):
        op.create_unique_constraint(
            "uq_platform_payments_gateway_ref",
            "platform_payments",
            ["gateway", "gateway_ref"],
        )

    # ------------------------------------------------------------------
    # 2.  Ensure the supporting indexes dropped by 1438cd26b844 and not
    #     recreated are present.  Both were in database.sql §indexes and
    #     are needed for the payment-lookup and invoice-lookup hot paths.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_platform_payments_invoice_id "
            "ON platform_payments (invoice_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_platform_payments_order_id "
            "ON platform_payments (order_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_platform_invoices_subscription_id "
            "ON platform_invoices (subscription_id)"
        )
    )


# ── Downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # Drop the indexes added above (IF EXISTS is safe across pg versions).
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS idx_platform_invoices_subscription_id"
        )
    )
    op.execute(
        sa.text("DROP INDEX IF EXISTS idx_platform_payments_order_id")
    )
    op.execute(
        sa.text("DROP INDEX IF EXISTS idx_platform_payments_invoice_id")
    )

    conn = op.get_bind()
    if _constraint_exists(conn, "platform_payments", "uq_platform_payments_gateway_ref"):
        op.drop_constraint(
            "uq_platform_payments_gateway_ref",
            "platform_payments",
            type_="unique",
        )
