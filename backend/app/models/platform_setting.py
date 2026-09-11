"""
ORM Model — platform_settings

Global configuration for C-SA-08: product name, support email, branding
colours, default timezone/currency and trial length. One row per key.

Deliberately key/value rather than a one-row table with a column per setting:
`tenant_settings` (§4.3) already uses that shape, so the same read/patch code
works for both, and adding a setting is an INSERT rather than a migration.

Defaults live in `PLATFORM_SETTING_DEFAULTS` rather than in the DB, so a fresh
install has a complete, working config with zero seed rows — the settings API
falls back to these for any key that has never been written.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<PlatformSetting {self.key}={self.value!r}>"


# The complete set of keys C-SA-08 exposes, with their factory defaults.
# `product_name` etc. are strings; `trial_length_days` is coerced to int by the
# service. Any key absent from the table reads back as its default here.
PLATFORM_SETTING_DEFAULTS: dict[str, str] = {
    "product_name": "shikshasync.me",
    "support_email": "support@shikshasync.me",
    "default_timezone": "Asia/Kolkata",
    "default_currency": "INR",
    "trial_length_days": "14",
    "brand_primary": "#0F172A",
    "brand_accent": "#4F46E5",
}

# Keys that must parse as a positive integer.
PLATFORM_SETTING_INT_KEYS = frozenset({"trial_length_days"})
