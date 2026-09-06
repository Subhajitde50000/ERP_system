"""
Tests — the two-provider email system

Proves the property that matters: the SAME call produces a Google send or a
Klaviyo send depending only on configuration, with no duplicated logic and no
caller changes. Both transports are stubbed — no SMTP socket, no HTTP call.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import get_settings
from app.services.mailer import (
    MailMessage,
    SendResult,
    build_message,
    known_events,
    provider_status,
    render,
    resolve,
    send_email,
)
from app.services.mailer.base import MailProvider
from app.services.mailer.providers.console import ConsoleMailProvider
from app.services.mailer.providers.google import GoogleMailProvider
from app.services.mailer.providers.klaviyo import KlaviyoMailProvider


class Cfg:
    """Minimal stand-in for Settings."""

    EMAIL_PROVIDER = "console"
    EMAIL_FROM = "erp@example.com"
    EMAIL_FROM_NAME = "xyz.com ERP"
    EMAIL_REPLY_TO = ""
    EMAIL_TIMEOUT_SECONDS = 5
    GOOGLE_SMTP_HOST = "smtp.gmail.com"
    GOOGLE_SMTP_PORT = 587
    GOOGLE_SMTP_USER = "erp@example.com"
    GOOGLE_SMTP_PASSWORD = "app-password-16ch"
    KLAVIYO_API_KEY = "pk_test_123"
    KLAVIYO_API_REVISION = "2024-10-15"
    KLAVIYO_METRIC_PREFIX = "ERP"


def msg(event="owner.verify_email", to="dean@college.edu"):
    return build_message(
        event, to, {"name": "Rahul", "verify_url": "https://xyz.com/v?token=abc"}
    )


# ── Templates are shared, not duplicated ─────────────────────────────────────

def test_every_outbox_event_has_a_template():
    """Each event the services queue must render real copy, not the fallback."""
    used_by_services = {
        "owner.verify_email",
        "platform_owner.verify_email",
        "owner.password_reset",
        "tenant.password_reset",
        "tenant.provisioned",
        "staff.invited",
    }
    assert used_by_services.issubset(set(known_events()))


def test_template_renders_subject_text_and_html_once():
    r = render("owner.verify_email", {"name": "Rahul", "verify_url": "https://x.io/v"})
    assert "Verify" in r.subject
    assert "https://x.io/v" in r.text
    assert "https://x.io/v" in r.html
    assert r.html.lstrip().startswith("<!doctype html>")


def test_both_providers_consume_the_same_rendered_message():
    """The message object is provider-neutral — proof there is one content path."""
    m = msg()
    assert m.subject and m.text and m.html
    assert m.event == "owner.verify_email"
    assert m.context["verify_url"].startswith("https://")


def test_unknown_event_falls_back_without_crashing():
    r = render("something.new", {"subject": "Hi", "body": "Body text"})
    assert r.subject == "Hi"
    assert "Body text" in r.text


# ── Shared base logic runs for every provider ────────────────────────────────

@pytest.mark.parametrize(
    "provider_cls", [GoogleMailProvider, KlaviyoMailProvider, ConsoleMailProvider]
)
async def test_bad_recipient_rejected_by_shared_validation(provider_cls):
    """Validation lives in base.send(), so no provider re-implements it."""
    result = await provider_cls(Cfg()).send(msg(to="not-an-email"))
    assert result.ok is False
    assert result.error == "INVALID_RECIPIENT"
    assert result.permanent is True


@pytest.mark.parametrize("provider_cls", [GoogleMailProvider, KlaviyoMailProvider])
async def test_missing_credentials_reported_not_raised(provider_cls):
    class Empty(Cfg):
        GOOGLE_SMTP_USER = ""
        GOOGLE_SMTP_PASSWORD = ""
        KLAVIYO_API_KEY = ""

    provider = provider_cls(Empty())
    assert provider.is_configured() is False
    result = await provider.send(msg())
    assert result.ok is False
    assert result.error == "NOT_CONFIGURED"


async def test_transport_exception_becomes_result_not_crash():
    """A dead provider must never propagate an exception to a caller."""

    class Broken(MailProvider):
        name = "broken"

        async def deliver(self, m):
            raise ConnectionError("network down")

    result = await Broken(Cfg()).send(msg())
    assert result.ok is False
    assert result.error == "ConnectionError"
    assert result.permanent is False  # transient → outbox retries


# ── GOOGLE provider ──────────────────────────────────────────────────────────

async def test_google_sends_multipart_mime_over_smtp():
    with patch("app.services.mailer.providers.google.aiosmtplib.send", new=AsyncMock()) as smtp:
        result = await GoogleMailProvider(Cfg()).send(msg())

    assert result.ok is True
    assert result.provider == "google"
    smtp.assert_awaited_once()

    mime = smtp.await_args.args[0]
    kwargs = smtp.await_args.kwargs
    assert mime["To"] == "Rahul <dean@college.edu>"
    # formataddr quotes a display name containing a dot — RFC 5322 correct.
    assert mime["From"] == '"xyz.com ERP" <erp@example.com>'
    assert "Verify" in mime["Subject"]
    assert mime.is_multipart()  # text + html alternative
    assert kwargs["hostname"] == "smtp.gmail.com"
    assert kwargs["port"] == 587
    assert kwargs["start_tls"] is True
    assert kwargs["password"] == "app-password-16ch"


async def test_google_port_465_uses_implicit_tls():
    class TLS(Cfg):
        GOOGLE_SMTP_PORT = 465

    with patch("app.services.mailer.providers.google.aiosmtplib.send", new=AsyncMock()) as smtp:
        await GoogleMailProvider(TLS()).send(msg())

    assert smtp.await_args.kwargs["use_tls"] is True
    assert smtp.await_args.kwargs["start_tls"] is False


async def test_google_permanent_smtp_error_is_not_retried():
    import aiosmtplib

    err = aiosmtplib.SMTPResponseException(550, "No such user")
    with patch("app.services.mailer.providers.google.aiosmtplib.send", new=AsyncMock(side_effect=err)):
        result = await GoogleMailProvider(Cfg()).send(msg())

    assert result.ok is False
    assert result.permanent is True


# ── KLAVIYO provider ─────────────────────────────────────────────────────────

def _klaviyo_client(status_code=202, text=""):
    response = MagicMock(status_code=status_code, text=text)
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, client


async def test_klaviyo_posts_event_with_metric_profile_and_body():
    ctx, client = _klaviyo_client()
    with patch("app.services.mailer.providers.klaviyo.httpx.AsyncClient", return_value=ctx):
        result = await KlaviyoMailProvider(Cfg()).send(msg())

    assert result.ok is True
    assert result.provider == "klaviyo"

    url = client.post.await_args.args[0]
    body = client.post.await_args.kwargs["json"]
    headers = client.post.await_args.kwargs["headers"]

    assert url == "https://a.klaviyo.com/api/events"
    assert headers["Authorization"] == "Klaviyo-API-Key pk_test_123"
    assert headers["revision"] == "2024-10-15"

    attrs = body["data"]["attributes"]
    assert attrs["metric"]["data"]["attributes"]["name"] == "ERP owner.verify_email"
    assert attrs["profile"]["data"]["attributes"]["email"] == "dean@college.edu"
    # The same rendered copy the SMTP provider would have sent.
    assert "Verify" in attrs["properties"]["subject"]
    assert attrs["properties"]["html_body"].lstrip().startswith("<!doctype html>")
    assert attrs["properties"]["verify_url"].startswith("https://")


async def test_klaviyo_4xx_is_permanent_and_5xx_is_retryable():
    ctx, _ = _klaviyo_client(status_code=401, text="invalid key")
    with patch("app.services.mailer.providers.klaviyo.httpx.AsyncClient", return_value=ctx):
        bad_key = await KlaviyoMailProvider(Cfg()).send(msg())
    assert bad_key.ok is False and bad_key.permanent is True

    ctx, _ = _klaviyo_client(status_code=503, text="upstream")
    with patch("app.services.mailer.providers.klaviyo.httpx.AsyncClient", return_value=ctx):
        outage = await KlaviyoMailProvider(Cfg()).send(msg())
    assert outage.ok is False and outage.permanent is False


# ── The switch itself ────────────────────────────────────────────────────────

def test_env_selects_google():
    assert resolve("google", Cfg()).name == "google"


def test_env_selects_klaviyo():
    assert resolve("klaviyo", Cfg()).name == "klaviyo"


def test_commenting_out_google_routes_everything_to_klaviyo():
    """Commenting the GOOGLE block in registry.py leaves only Klaviyo."""
    only_klaviyo = {"klaviyo": KlaviyoMailProvider, "console": ConsoleMailProvider}
    with patch("app.services.mailer.registry.PROVIDERS", only_klaviyo), patch(
        "app.services.mailer.registry._REAL", ["klaviyo"]
    ):
        # Even with EMAIL_PROVIDER=google still in .env, Klaviyo takes over.
        assert resolve("google", Cfg()).name == "klaviyo"
        assert resolve("klaviyo", Cfg()).name == "klaviyo"


def test_commenting_out_klaviyo_routes_everything_to_google():
    """Commenting the KLAVIYO block in registry.py leaves only Google."""
    only_google = {"google": GoogleMailProvider, "console": ConsoleMailProvider}
    with patch("app.services.mailer.registry.PROVIDERS", only_google), patch(
        "app.services.mailer.registry._REAL", ["google"]
    ):
        # Even with EMAIL_PROVIDER=klaviyo still in .env, Google takes over.
        assert resolve("klaviyo", Cfg()).name == "google"
        assert resolve("google", Cfg()).name == "google"


def test_commenting_out_both_still_boots_on_console():
    """Worst case must degrade, not crash the app at import time."""
    with patch("app.services.mailer.registry.PROVIDERS", {"console": ConsoleMailProvider}), \
         patch("app.services.mailer.registry._REAL", []):
        assert resolve("google", Cfg()).name == "console"
        assert resolve("klaviyo", Cfg()).name == "console"


def test_unconfigured_provider_degrades_to_console_instead_of_crashing():
    class NoKeys(Cfg):
        GOOGLE_SMTP_USER = ""
        GOOGLE_SMTP_PASSWORD = ""

    assert resolve("google", NoKeys()).name == "console"


def test_unknown_provider_name_degrades_to_console():
    assert resolve("mailchimp", Cfg()).name == "console"


# ── Callers are provider-agnostic ────────────────────────────────────────────

async def test_send_email_uses_whichever_provider_is_active(monkeypatch):
    """One call site, two outcomes — the caller never names a provider."""
    settings = get_settings()
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "google", raising=False)
    monkeypatch.setattr(settings, "EMAIL_FROM", "erp@example.com", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_SMTP_USER", "erp@example.com", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_SMTP_PASSWORD", "pw", raising=False)

    with patch("app.services.mailer.providers.google.aiosmtplib.send", new=AsyncMock()):
        google_result = await send_email(
            "owner.verify_email", "a@b.com", {"verify_url": "https://x.io"}
        )
    assert google_result.provider == "google"

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "klaviyo", raising=False)
    monkeypatch.setattr(settings, "KLAVIYO_API_KEY", "pk_x", raising=False)
    ctx, _ = _klaviyo_client()
    with patch("app.services.mailer.providers.klaviyo.httpx.AsyncClient", return_value=ctx):
        klaviyo_result = await send_email(
            "owner.verify_email", "a@b.com", {"verify_url": "https://x.io"}
        )
    assert klaviyo_result.provider == "klaviyo"


def test_status_payload_never_leaks_secrets(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "GOOGLE_SMTP_PASSWORD", "super-secret-pw", raising=False)
    monkeypatch.setattr(settings, "KLAVIYO_API_KEY", "pk_live_should_never_leak", raising=False)

    payload = provider_status()
    # Ignore known_events, which legitimately contains "owner.password_reset".
    payload.pop("known_events", None)
    flat = repr(payload)

    assert "super-secret-pw" not in flat
    assert "pk_live_should_never_leak" not in flat
    assert payload["active_provider"] in {"google", "klaviyo", "console"}


# ── Outbox behaviour ─────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True

    async def execute(self, stmt):
        result = MagicMock()
        result.scalars.return_value = MagicMock(all=lambda: self.rows)
        return result


def test_queue_email_writes_row_without_committing():
    from app.models.billing import OutboxEmail
    from app.services.mailer import queue_email

    db = FakeDB()
    tenant = uuid.uuid4()
    row = queue_email(
        db, "staff.invited", "t@school.edu",
        {"name": "Asha", "tenant_name": "Green", "invite_url": "https://x.io/i"},
        tenant_id=tenant,
    )

    assert isinstance(row, OutboxEmail)
    assert db.added == [row]
    assert db.committed is False          # caller's transaction owns the commit
    assert row.status == "QUEUED"
    assert row.to_address == "t@school.edu"
    assert "Green" in row.subject
    assert "https://x.io/i" in row.body


async def test_failed_send_keeps_row_queued_until_max_attempts(monkeypatch):
    from app.models.billing import OutboxEmail
    from app.services.mailer import MAX_ATTEMPTS, deliver_row

    row = OutboxEmail(
        id=uuid.uuid4(), event="owner.verify_email", to_address="x@y.com",
        subject="Verify", body="link", status="QUEUED", attempts=0,
    )
    failing = SendResult.failure("google", "SMTPServerDisconnected")
    monkeypatch.setattr(
        "app.services.mailer.service.get_provider",
        lambda: MagicMock(send=AsyncMock(return_value=failing), name="google"),
    )

    db = FakeDB()
    await deliver_row(db, row)
    assert row.status == "QUEUED" and row.attempts == 1

    row.attempts = MAX_ATTEMPTS - 1
    await deliver_row(db, row)
    assert row.status == "FAILED"          # gives up instead of looping forever


async def test_permanent_failure_fails_immediately(monkeypatch):
    from app.models.billing import OutboxEmail
    from app.services.mailer import deliver_row

    row = OutboxEmail(
        id=uuid.uuid4(), event="owner.verify_email", to_address="x@y.com",
        subject="Verify", body="link", status="QUEUED", attempts=0,
    )
    permanent = SendResult.failure("klaviyo", "PERMANENT", permanent=True)
    monkeypatch.setattr(
        "app.services.mailer.service.get_provider",
        lambda: MagicMock(send=AsyncMock(return_value=permanent)),
    )

    await deliver_row(FakeDB(), row)
    assert row.status == "FAILED" and row.attempts == 1


async def test_drain_marks_sent_and_reports_summary(monkeypatch):
    from app.models.billing import OutboxEmail
    from app.services.mailer import deliver_outbox

    rows = [
        OutboxEmail(
            id=uuid.uuid4(), event="owner.verify_email", to_address=f"u{i}@x.com",
            subject="Verify", body="link", status="QUEUED", attempts=0,
        )
        for i in range(3)
    ]
    monkeypatch.setattr(
        "app.services.mailer.service.get_provider",
        lambda: ConsoleMailProvider(Cfg()),
    )

    db = FakeDB(rows)
    summary = await deliver_outbox(db)

    assert summary["sent"] == 3
    assert summary["failed"] == 0
    assert all(r.status == "SENT" for r in rows)
    assert db.committed is True
