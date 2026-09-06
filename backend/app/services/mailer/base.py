"""
Mailer — Shared contracts (provider-agnostic)

Everything in this file is written ONCE and reused by every provider.
A provider implements exactly one method: `deliver()`.

Deliberately NOT in a provider:
  - configuration validation      → `is_configured()` uses a declared key list
  - exception trapping / wrapping → `send()` wraps `deliver()`
  - recipient/subject validation  → `send()`
  - result shape & logging        → `SendResult` + `send()`

So "add a provider" means "write one async function", and a bug fixed in the
shared path is fixed for every transport at the same time.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("app.mailer")


# ── Message ───────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class MailMessage:
    """
    One outbound email, already rendered and provider-neutral.

    `text` and `html` are both carried so all clients have a usable fallback.
    """

    to: str
    subject: str
    text: str
    html: str = ""
    event: str = "generic"
    tenant_id: Any | None = None
    # Structured values behind the rendered copy (name, urls, plan, …).
    context: dict[str, Any] = field(default_factory=dict)
    # Stable id used for provider-side de-duplication on retry.
    idempotency_key: str | None = None

    def recipient_name(self) -> str | None:
        value = self.context.get("name")
        return str(value) if value else None


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class SendResult:
    """Uniform outcome so the outbox never branches on provider type."""

    ok: bool
    provider: str
    detail: str = ""
    error: str = ""
    remote_id: str | None = None
    # True when the failure is permanent (bad address, rejected payload) and
    # retrying would only burn attempts. The outbox fails these immediately.
    permanent: bool = False

    @classmethod
    def success(
        cls, provider: str, detail: str = "sent", remote_id: str | None = None
    ) -> SendResult:
        return cls(ok=True, provider=provider, detail=detail, remote_id=remote_id)

    @classmethod
    def failure(
        cls, provider: str, error: str, detail: str = "", permanent: bool = False
    ) -> SendResult:
        return cls(
            ok=False,
            provider=provider,
            error=error,
            detail=detail or error,
            permanent=permanent,
        )


class PermanentSendError(Exception):
    """Raised by a provider when a retry cannot possibly succeed."""


# ── Provider contract ─────────────────────────────────────────────────────────

class MailProvider(ABC):
    """
    Base class for every transport.

    Subclass responsibilities (the whole list):
      1. set `name`
      2. set `required_settings` — names of Settings fields that must be truthy
      3. implement `async deliver(msg) -> SendResult`
    """

    name: str = "base"
    # Settings attributes that must be non-empty for this provider to run.
    required_settings: tuple[str, ...] = ()

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    # -- configuration (shared) ------------------------------------------------

    def missing_settings(self) -> list[str]:
        """Which required env vars are still blank."""
        missing: list[str] = []
        for key in self.required_settings:
            value = getattr(self.settings, key, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(key)
        return missing

    def is_configured(self) -> bool:
        return not self.missing_settings()

    def describe(self) -> dict[str, Any]:
        """Health-check payload — same shape for every provider."""
        return {
            "provider": self.name,
            "configured": self.is_configured(),
            "missing_settings": self.missing_settings(),
        }

    # -- sending ---------------------------------------------------------------

    async def send(self, msg: MailMessage) -> SendResult:
        """
        Shared entry point. Validates, calls `deliver()`, and converts any
        exception into a SendResult so callers never need try/except.
        """
        if not msg.to or "@" not in msg.to:
            return SendResult.failure(
                self.name, "INVALID_RECIPIENT", f"bad address: {msg.to!r}", permanent=True
            )
        if not msg.subject.strip():
            return SendResult.failure(
                self.name, "EMPTY_SUBJECT", "subject is required", permanent=True
            )

        missing = self.missing_settings()
        if missing:
            return SendResult.failure(
                self.name,
                "NOT_CONFIGURED",
                f"missing settings: {', '.join(missing)}",
                permanent=True,
            )

        try:
            result = await self.deliver(msg)
        except PermanentSendError as exc:
            logger.warning("[mailer:%s] permanent failure: %s", self.name, exc)
            return SendResult.failure(
                self.name, "PERMANENT", str(exc), permanent=True
            )
        except Exception as exc:  # noqa: BLE001 — transport errors are expected
            logger.warning(
                "[mailer:%s] send failed for %s (%s): %s",
                self.name,
                msg.to,
                msg.event,
                exc,
            )
            return SendResult.failure(self.name, type(exc).__name__, str(exc))

        if result.ok:
            logger.info(
                "[mailer:%s] sent %s → %s", self.name, msg.event, msg.to
            )
        return result

    @abstractmethod
    async def deliver(self, msg: MailMessage) -> SendResult:
        """Transport-specific delivery. The ONLY thing a provider implements."""
        raise NotImplementedError
