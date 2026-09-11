"""
ORM Model — platform_owners

The **customer / account-holder** — the person who signs up at shikshasync.me, pays
the bills and owns one or more institutions. Think of this as the AWS / Shopify
/ Zoho "account": Rahul (rahul@gmail.com) logs in once and manages every
institution he owns from a single platform dashboard.

This is deliberately a *third* identity table, distinct from:

  • `platform_users` — the platform's own **staff** (Super Admin, Support,
    Sales, Finance). They run shikshasync.me; they do not pay for it.
  • `users`           — institution-bound members (Teacher, Student,
    INSTITUTION_ADMIN …). They live inside one tenant.

An owner is none of those: they are the buyer. One owner → many tenants, via
`tenants.owner_id`.

Email verification gates login: an unverified owner cannot sign in, which
prevents a mistyped email from provisioning an institution nobody can reach.
"""

import uuid

from sqlalchemy import Boolean, Index, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class PlatformOwner(Base):
    __tablename__ = "platform_owners"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Email verification — blocks login until the address is confirmed.
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # SHA-256 hash of the one-time verification token (never the raw token).
    email_verification_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    email_verification_expires: Mapped[TIMESTAMP | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Self-service password reset (mirrors `users`).
    password_reset_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    password_reset_expires: Mapped[TIMESTAMP | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[TIMESTAMP | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_platform_owners_email", "email"),
    )

    def __repr__(self) -> str:
        verified = "verified" if self.is_email_verified else "unverified"
        return f"<PlatformOwner {self.email} [{verified}]>"
