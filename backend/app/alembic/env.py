import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.database import Base
import app.models  # load all models so Base.metadata is fully populated

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# ── Tables that exist in database.sql but are NOT yet in the ORM.
# Autogenerate would wrongly emit DROP TABLE for these; we exclude them
# from both autogenerate comparisons and drift-check runs.
# Remove entries here as ORM models are added for each module.
#
# NOTE: device_tokens, notification_deliveries, parent_student_links,
# hostel_*, book_*, e_resources, fee_*, scholarships, scholarship_grants,
# student_fee_accounts are ORM-managed (models exist) — do NOT list them here.
_UNMANAGED_TABLES = frozenset([
    # Finance / HR (no ORM model yet)
    "payslips", "purchase_orders", "purchase_order_items",
    "data_export_jobs",
    # Transport (no ORM model yet)
    "transport_stops", "student_transport", "transport_routes",
    "vehicles", "drivers",
    # Admission (no ORM model yet)
    "interview_rounds", "admission_cycles", "admission_applications",
    "application_documents", "merit_lists",
    # Placement (no ORM model yet)
    "placement_drives", "placement_applications", "placement_offers",
    "drive_eligibility", "companies",
    # HR / Payroll (no ORM model yet)
    "appraisal_cycles", "appraisals", "leave_policies",
    "payroll_runs", "vendors", "salary_structures",
    # Inventory (no ORM model yet)
    "stock_transactions", "fee_heads",
    "inventory_categories", "inventory_items",
    # Misc legacy (no ORM model yet)
    "bulk_import_jobs", "notification_templates", "staff_documents",
    "mentor_notes", "grade_cards",
])


def include_object(obj, name, type_, reflected, compare_to):
    """Exclude unmanaged tables from autogenerate / drift checks."""
    if type_ == "table" and name in _UNMANAGED_TABLES:
        return False
    return True


# ── Shared autogenerate options ───────────────────────────────────────────────
# compare_type=True   — detect column type changes (VARCHAR(20) → Text, etc.)
# compare_server_default=True — detect added/removed server_default values
# include_object      — filter out unmanaged legacy tables
_AUTOGENERATE_OPTS: dict = {
    "target_metadata": target_metadata,
    "include_object": include_object,
    "compare_type": True,
    "compare_server_default": True,
}


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_AUTOGENERATE_OPTS,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        **_AUTOGENERATE_OPTS,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
