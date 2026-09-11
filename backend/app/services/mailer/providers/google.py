"""Google / Google Workspace SMTP provider for deployment testing."""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import aiosmtplib

from app.services.mailer.base import MailMessage, MailProvider, PermanentSendError, SendResult


class GoogleMailProvider(MailProvider):
    name = "google"
    required_settings = ("GOOGLE_SMTP_USER", "GOOGLE_SMTP_PASSWORD", "EMAIL_FROM")

    async def deliver(self, msg: MailMessage) -> SendResult:
        s = self.settings
        mime = EmailMessage()
        mime["From"] = formataddr((s.EMAIL_FROM_NAME, s.EMAIL_FROM))
        mime["To"] = formataddr((msg.recipient_name(), msg.to)) if msg.recipient_name() else msg.to
        mime["Subject"] = msg.subject
        mime["Message-ID"] = make_msgid(domain=s.EMAIL_FROM.split("@")[-1])
        if s.EMAIL_REPLY_TO:
            mime["Reply-To"] = s.EMAIL_REPLY_TO
        mime.set_content(msg.text)
        if msg.html:
            mime.add_alternative(msg.html, subtype="html")

        port = int(s.GOOGLE_SMTP_PORT)
        try:
            await aiosmtplib.send(
                mime,
                hostname=s.GOOGLE_SMTP_HOST,
                port=port,
                username=s.GOOGLE_SMTP_USER,
                password=s.GOOGLE_SMTP_PASSWORD,
                start_tls=port == 587,
                use_tls=port == 465,
                timeout=s.EMAIL_TIMEOUT_SECONDS,
            )
        except aiosmtplib.errors.SMTPResponseException as exc:
            if 500 <= exc.code < 600:
                raise PermanentSendError(f"SMTP {exc.code}: {exc.message}") from exc
            return SendResult.failure(self.name, f"SMTP_{exc.code}", str(exc))

        return SendResult.success(
            self.name,
            f"smtp {s.GOOGLE_SMTP_HOST}:{port}",
            remote_id=mime["Message-ID"],
        )
