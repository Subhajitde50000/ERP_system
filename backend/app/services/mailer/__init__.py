"""
Mailer package — Google SMTP for test deployments and ZeptoMail for production.

    app/services/mailer/
    ├── base.py                 shared contract: validation, errors, results
    ├── templates.py            all email copy, written once
    ├── registry.py             provider selection
    ├── service.py              queue_email / send_email / deliver_outbox
    └── providers/
        ├── google.py           Google SMTP — deliver() only
        ├── zeptomail.py        ZeptoMail HTTPS API — deliver() only
        └── console.py          dev fallback — deliver() only

Callers import from this package and never from a provider module.
"""

from app.services.mailer.base import (
    MailMessage,
    MailProvider,
    PermanentSendError,
    SendResult,
)
from app.services.mailer.registry import PROVIDERS, available, resolve
from app.services.mailer.service import (
    MAX_ATTEMPTS,
    build_message,
    deliver_outbox,
    deliver_row,
    get_provider,
    provider_status,
    queue_email,
    send_email,
)
from app.services.mailer.templates import known_events, render

__all__ = [
    "MailMessage",
    "MailProvider",
    "PermanentSendError",
    "SendResult",
    "PROVIDERS",
    "available",
    "resolve",
    "MAX_ATTEMPTS",
    "build_message",
    "deliver_outbox",
    "deliver_row",
    "get_provider",
    "provider_status",
    "queue_email",
    "send_email",
    "known_events",
    "render",
]
