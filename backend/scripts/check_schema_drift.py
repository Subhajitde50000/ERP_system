#!/usr/bin/env python3
"""
Schema-drift CI gate — backend/scripts/check_schema_drift.py

Connects to the database, runs every pending Alembic migration (upgrade head),
then asks Alembic to compare the live schema against the ORM metadata.

Exit codes:
  0  — schema matches ORM exactly; no drift detected
  1  — drift detected (printed to stdout) or migrations failed
  2  — configuration / environment error

Usage (local):
  DATABASE_URL=postgresql+asyncpg://... python scripts/check_schema_drift.py

Usage (CI — runs automatically inside the backend-ci job after pytest):
  see .github/workflows/ci.yml

How it works:
  Alembic's MigrationContext.configure() + MigrationContext.run_migrations()
  surface is used in "offline" inspection mode: we connect to the real DB,
  apply any pending migrations, then call alembic.runtime.migration to
  produce a diff.  A non-empty diff means ORM ↔ DB are out of sync and a
  migration has been forgotten.

  The script respects env.py's _UNMANAGED_TABLES exclusion list so legacy
  tables that intentionally have no ORM model do not produce false positives.
"""

import asyncio
import os
import sys
from pathlib import Path

# ── Path bootstrap ────────────────────────────────────────────────────────────
# Allow running from the repo root or from backend/
REPO_ROOT = Path(__file__).resolve().parents[1]   # backend/
sys.path.insert(0, str(REPO_ROOT))

# ── Ensure DATABASE_URL is set before importing app code ──────────────────────
_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not _DATABASE_URL:
    print(
        "ERROR: DATABASE_URL is not set.\n"
        "       Export it before running this script, e.g.:\n"
        "       DATABASE_URL=postgresql+asyncpg://erp_user:pass@localhost/erp_db "
        "python scripts/check_schema_drift.py",
        file=sys.stderr,
    )
    sys.exit(2)

# asyncpg driver is needed for SQLAlchemy async; psycopg2 is needed by Alembic
# for the synchronous comparison step.  We convert the URL for the sync path.
_SYNC_URL = _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
if _SYNC_URL.startswith("postgresql://"):
    _SYNC_URL = _SYNC_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine, text

import app.models  # noqa: F401 — registers all models on Base.metadata
from app.database import Base
from app.alembic.env import _UNMANAGED_TABLES   # reuse the canonical exclusion list


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_alembic_cfg() -> AlembicConfig:
    """Build an AlembicConfig pointing at the project's alembic.ini."""
    ini_path = REPO_ROOT / "alembic.ini"
    if not ini_path.exists():
        print(f"ERROR: alembic.ini not found at {ini_path}", file=sys.stderr)
        sys.exit(2)
    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", _SYNC_URL)
    return cfg


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Mirror env.py's include_object so unmanaged tables are excluded."""
    if type_ == "table" and name in _UNMANAGED_TABLES:
        return False
    return True


def _run_upgrade(cfg: AlembicConfig) -> None:
    """Apply any pending migrations so the live DB is at head."""
    print("→ Running alembic upgrade head …")
    alembic_command.upgrade(cfg, "head")
    print("  ✓ Migrations applied (or already at head).")


def _check_drift(engine) -> list:
    """
    Return a list of migration op objects representing ORM↔DB differences.
    An empty list means no drift.
    """
    with engine.connect() as conn:
        mc = MigrationContext.configure(
            conn,
            opts={
                "compare_type": True,
                "compare_server_default": True,
                "include_object": _include_object,
            },
        )
        return compare_metadata(mc, Base.metadata)


def _format_diff(diffs: list) -> str:
    """Pretty-print the diff list to a human-readable string."""
    lines = []
    for diff in diffs:
        lines.append(f"  • {diff}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    cfg = _make_alembic_cfg()

    # 1. Apply pending migrations
    try:
        _run_upgrade(cfg)
    except Exception as exc:
        print(f"\nFATAL: Migration failed — {exc}", file=sys.stderr)
        return 1

    # 2. Build a sync engine for the drift comparison
    #    (Alembic autogenerate works synchronously)
    try:
        engine = create_engine(
            _SYNC_URL,
            echo=False,
            connect_args={"connect_timeout": 10},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))   # quick connectivity check
    except Exception as exc:
        print(f"\nFATAL: Cannot connect to database — {exc}", file=sys.stderr)
        return 2

    # 3. Detect drift
    print("→ Comparing ORM metadata against live schema …")
    try:
        diffs = _check_drift(engine)
    except Exception as exc:
        print(f"\nFATAL: Drift comparison failed — {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    # 4. Report
    if not diffs:
        print(
            "\n✅  No schema drift detected.\n"
            "   The live database matches the ORM metadata exactly.\n"
            "   Alembic is the authoritative schema source."
        )
        return 0

    print(
        f"\n❌  Schema drift detected — {len(diffs)} difference(s) found:\n"
        f"{_format_diff(diffs)}\n\n"
        "   Action required:\n"
        "     1. Run:  alembic revision --autogenerate -m 'describe_the_change'\n"
        "        to generate a migration for these differences.\n"
        "     2. Review the generated file carefully — autogenerate is not\n"
        "        perfect; check that unmanaged tables are excluded via\n"
        "        env.py:_UNMANAGED_TABLES before committing.\n"
        "     3. Re-run this script to confirm zero drift before merging.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
