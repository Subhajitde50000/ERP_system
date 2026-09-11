"""
Mailer provider — CONSOLE (development fallback)

Never talks to the network: it logs the email and reports success. Used when
no live provider is configured so local development and tests never
crash on a missing API key. Requires no settings, so it is always "configured".
"""

from __future__ import annotations

import logging

from app.services.mailer.base import MailMessage, MailProvider, SendResult

logger = logging.getLogger("app.mailer.console")


class ConsoleMailProvider(MailProvider):
    name = "console"
    required_settings = ()

    async def deliver(self, msg: MailMessage) -> SendResult:
        logger.info(
            "\n──────── EMAIL (console) ────────\n"
            "event   : %s\nto      : %s\nsubject : %s\n"
            "─────────────────────────────────\n%s\n"
            "─────────────────────────────────",
            msg.event,
            msg.to,
            msg.subject,
            msg.text,
        )
        return SendResult.success(self.name, "logged to console (not delivered)")
