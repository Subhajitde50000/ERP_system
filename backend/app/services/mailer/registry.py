"""Mailer provider registry: Google SMTP for testing, ZeptoMail for production."""

from __future__ import annotations

import logging

from app.services.mailer.base import MailProvider
from app.services.mailer.providers.console import ConsoleMailProvider
from app.services.mailer.providers.google import GoogleMailProvider
from app.services.mailer.providers.zeptomail import ZeptoMailProvider

logger = logging.getLogger("app.mailer")

_ENABLED: list[type[MailProvider]] = [GoogleMailProvider, ZeptoMailProvider]
PROVIDERS: dict[str, type[MailProvider]] = {
    cls.name: cls for cls in (*_ENABLED, ConsoleMailProvider)
}
_REAL: list[str] = [cls.name for cls in _ENABLED]


def available() -> list[str]:
    return list(PROVIDERS)


def resolve(requested: str, settings: object) -> MailProvider:
    """Resolve the explicitly configured transport, with console as safe fallback."""
    key = (requested or "").strip().lower()
    cls = PROVIDERS.get(key)
    if cls is None:
        logger.warning("[mailer] EMAIL_PROVIDER=%r is unknown; using console.", requested)
        cls = ConsoleMailProvider

    provider = cls(settings)
    if not provider.is_configured():
        logger.warning(
            "[mailer] provider %r is missing settings: %s; using console.",
            provider.name,
            ", ".join(provider.missing_settings()),
        )
        return ConsoleMailProvider(settings)
    return provider
