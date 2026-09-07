"""ZeptoMail HTTPS API provider for transactional email."""

from __future__ import annotations

from typing import Any

import httpx

from app.services.mailer.base import MailMessage, MailProvider, PermanentSendError, SendResult


class ZeptoMailProvider(MailProvider):
    name = "zeptomail"
    required_settings = ("ZEPTO_MAIL_SEND_TOKEN", "EMAIL_FROM")

    async def deliver(self, msg: MailMessage) -> SendResult:
        s = self.settings
        recipient: dict[str, Any] = {"address": msg.to}
        if msg.recipient_name():
            recipient["name"] = msg.recipient_name()
        payload: dict[str, Any] = {
            "from": {"address": s.EMAIL_FROM, "name": s.EMAIL_FROM_NAME},
            "to": [{"email_address": recipient}],
            "subject": msg.subject,
            "textbody": msg.text,
        }
        if msg.html:
            payload["htmlbody"] = msg.html
        if msg.idempotency_key:
            payload["client_reference"] = msg.idempotency_key
        if s.EMAIL_REPLY_TO:
            payload["reply_to"] = [{"address": s.EMAIL_REPLY_TO}]

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Zoho-enczapikey {s.ZEPTO_MAIL_SEND_TOKEN}",
        }
        async with httpx.AsyncClient(timeout=s.EMAIL_TIMEOUT_SECONDS) as client:
            response = await client.post(s.ZEPTO_MAIL_API_URL, json=payload, headers=headers)

        if 200 <= response.status_code < 300:
            try:
                data = response.json()
            except ValueError:
                data = {}
            remote_id = data.get("request_id") or data.get("message_id")
            return SendResult.success(self.name, "accepted by ZeptoMail", remote_id=remote_id)

        body = response.text[:400]
        if 400 <= response.status_code < 500 and response.status_code != 429:
            raise PermanentSendError(f"HTTP {response.status_code}: {body}")
        return SendResult.failure(self.name, f"HTTP_{response.status_code}", body)
