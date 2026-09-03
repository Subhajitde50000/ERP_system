import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.database import Base
import app.models  # load all models

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# ── Tables that exist in database.sql but are NOT yet in the ORM.
# Autogenerate would wrongly emit DROP TABLE for these; we exclude them.
# Remove entries here as ORM models are added for each module.
_UNMANAGED_TABLES = frozenset([
    "payslips", "purchase_orders", "purchase_order_items",
    "data_export_jobs", "transport_stops", "student_transport",
    "hostel_attendance", "hostel_allotments", "hostel_rooms",
    "hostel_complaints", "hostel_leave_requests", "hostel_blocks",
    "stock_transactions", "drivers", "fee_heads", "interview_rounds",
    "admission_cycles", "admission_applications", "application_documents",
    "merit_lists", "e_resources", "book_issues", "book_copies", "books",
    "appraisal_cycles", "appraisals", "leave_policies", "placement_drives",
    "placement_applications", "placement_offers", "drive_eligibility",
    "companies", "mentor_notes",
    # "device_tokens" removed: the ORM model now exists
    # (app/models/notification.py), so autogenerate must see its columns/indexes.
    # "notification_deliveries" is likewise ORM-managed and never excluded.
    # "parent_student_links" removed: the guardian portal's ORM model now exists
    # (app/models/parent.py), so autogenerate must see its columns and indexes.
    # Leaving it here would hide the link table from every future drift check.
    "transport_routes", "grade_cards",
    "inventory_categories", "inventory_items", "bulk_import_jobs",
    "vehicles", "payroll_runs", "vendors", "salary_structures",
    "notification_templates", "notice_attachments", "staff_documents",
    "scholarships", "scholarship_grants", "student_fee_accounts",
    "fee_structures", "fee_installments", "fee_payments",
])


def include_object(obj, name, type_, reflected, compare_to):
    """Skip tables that exist in the DB but have no ORM model yet."""
    if type_ == "table" and name in _UNMANAGED_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
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
