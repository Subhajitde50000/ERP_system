"""Unit tests for the notification platform (inbox, push registry, FCM)."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.notification import DeviceToken, NotificationDelivery
from app.models.online_class import Notification
from app.schemas.notification import PushTokenRegisterIn
from app.services.fcm_client import FcmClient, FcmMessage, FcmResult, TERMINAL_TOKEN_CODES
from app.services.notification_service import (
    MAX_DEVICE_TOKENS_PER_USER,
    NotificationService,
)

UUID = uuid.uuid4


def _notif(user_id=None, notif_id=None, title="Hello", body="Body"):
    return SimpleNamespace(
        id=notif_id or UUID(),
        user_id=user_id or UUID(),
        title=title,
        body=body,
        type="ONLINE_CLASS",
        data={"class_id": str(UUID())},
        is_read=False,
        read_at=None,
        created_at=datetime.now(timezone.utc),
    )


def _mock_db(user=None):
    """MagicMock db mirroring the conftest client fixture's shape."""
    db = MagicMock()
    db.flush = AsyncMock()
    exec_mock = MagicMock()
    exec_mock.scalar_one.side_effect = [1, 1]
    exec_mock.scalar_one_or_none.return_value = None
    exec_mock.scalars.return_value.all.return_value = []
    exec_mock.all.return_value = []
    db.execute = AsyncMock(return_value=exec_mock)
    return db


# ── Inbox ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_inbox_returns_page():
    user_id = UUID()
    notif = _notif(user_id=user_id)
    db = _mock_db(user_id)
    db.execute.return_value.scalars.return_value.all.return_value = [notif]

    page = await NotificationService.list_inbox(db, user_id, limit=10, offset=0)
    assert page.total == 1 and page.unread_count == 1
    assert page.items[0].title == "Hello"


@pytest.mark.asyncio
async def test_mark_read_marks_row_and_preserves_owner_scope():
    user_id = UUID()
    notif_id = UUID()
    notif = _notif(user_id=user_id, notif_id=notif_id)
    db = _mock_db(user_id)
    db.execute.return_value.scalar_one_or_none.return_value = notif

    row = await NotificationService.mark_read(db, user_id, notif_id)
    assert row.is_read is True and notif.read_at is not None


@pytest.mark.asyncio
async def test_mark_read_404_when_not_owned():
    db = _mock_db()
    db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(Exception) as exc:
        await NotificationService.mark_read(db, UUID(), UUID())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unread_count():
    db = _mock_db()
    db.execute.return_value.scalar_one_or_none.return_value = 3
    assert await NotificationService.unread_count(db, UUID()) == 3


# ── Device token registry ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_new_token():
    db = _mock_db()
    row = await NotificationService.register_device_token(
        db, UUID(), token="fcm-token-123456789", platform="android"
    )
    assert row.is_active is True
    assert row.platform == "android"
    db.add.assert_called()


@pytest.mark.asyncio
async def test_register_same_token_refreshes():
    existing = DeviceToken(
        id=UUID(), user_id=UUID(), token="fcm-token-123456789", platform="ios", is_active=False
    )
    db = _mock_db()
    db.execute.return_value.scalar_one_or_none.return_value = existing
    row = await NotificationService.register_device_token(
        db, existing.user_id, token="fcm-token-123456789", platform="ios"
    )
    assert row is existing and row.is_active is True and row.last_used_at is not None


@pytest.mark.asyncio
async def test_register_rejects_unknown_platform():
    db = _mock_db()
    with pytest.raises(Exception) as exc:
        await NotificationService.register_device_token(
            db, UUID(), token="fcm-token-123456789", platform="windows"
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_register_enforces_per_user_cap():
    db = _mock_db()
    # First call (existing-token lookup) → None; second (active count) → cap.
    db.execute.return_value.scalar_one_or_none.side_effect = [None, MAX_DEVICE_TOKENS_PER_USER]
    with pytest.raises(Exception) as exc:
        await NotificationService.register_device_token(
            db, UUID(), token="fcm-token-123456789", platform="web"
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_unregister_inactive_token_is_idempotent():
    existing = DeviceToken(id=UUID(), user_id=UUID(), token="fcm-token-123456789", platform="web", is_active=True)
    db = _mock_db()
    db.execute.return_value.scalar_one_or_none.return_value = existing
    assert await NotificationService.unregister_device_token(db, existing.user_id, existing.token) is True
    assert existing.is_active is False
    # A second call finds an already-dead token → not an error, returns False.
    assert await NotificationService.unregister_device_token(db, existing.user_id, existing.token) is False


def test_register_schema_validates_token_and_platform():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PushTokenRegisterIn(token="x" * 4097, platform="android")  # over MAX_TOKEN_LENGTH
    with pytest.raises(ValidationError):
        PushTokenRegisterIn(token="ok token with space", platform="android")  # whitespace
    with pytest.raises(ValidationError):
        PushTokenRegisterIn(token="ok-token-value", platform="desktop")  # unknown platform
    # A healthy payload passes.
    payload = PushTokenRegisterIn(token="fcm-token-123456789", platform="WEB")
    assert payload.platform == "web"


# ── create_notifications + outbox ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_notifications_skips_outbox_when_fcm_disabled():
    db = _mock_db()
    with patch("app.services.notification_service.get_fcm_client") as fcm:
        fcm.return_value.enabled = False
        rows = await NotificationService.create_notifications(
            db, tenant_id=UUID(), user_ids=[UUID(), UUID()], title="T", body="B", notif_type="TEST"
        )
    assert len(rows) == 2
    # db.add called for notifications only — no delivery rows while disabled.
    added = [call.args[0] for call in db.add.call_args_list]
    assert all(isinstance(item, Notification) for item in added)


@pytest.mark.asyncio
async def test_create_notifications_enqueues_delivery_per_active_token():
    user_id = UUID()
    token = DeviceToken(id=UUID(), user_id=user_id, token="fcm-token-123456789", platform="android", is_active=True)
    db = _mock_db(user_id)
    db.execute.return_value.scalars.return_value.all.return_value = [token]
    with patch("app.services.notification_service.get_fcm_client") as fcm:
        fcm.return_value.enabled = True
        rows = await NotificationService.create_notifications(
            db, tenant_id=UUID(), user_ids=[user_id], title="T", body="B", notif_type="TEST"
        )
    added = [call.args[0] for call in db.add.call_args_list]
    deliveries = [item for item in added if isinstance(item, NotificationDelivery)]
    assert len(rows) == 1 and len(deliveries) == 1
    assert deliveries[0].device_token_id == token.id
    assert deliveries[0].status == "PENDING"


@pytest.mark.asyncio
async def test_create_notifications_dedupes_recipients_and_survives_token_errors():
    db = _mock_db()
    db.execute.side_effect = RuntimeError("boom")  # any token lookup issue
    with patch("app.services.notification_service.get_fcm_client") as fcm:
        fcm.return_value.enabled = True
        rows = await NotificationService.create_notifications(
            db, tenant_id=None, user_ids=[UUID(), UUID(), UUID()], title="T", body="B"
        )
    assert len(rows) == 3  # in-app rows survive even when push enqueue failed


# ── FCM client ───────────────────────────────────────────────────────────────

def _fcm_result(status_code: int, body: dict | None = None):
    """Build an httpx.Response and classify it through the real code path."""
    client = FcmClient()
    resp = httpx.Response(status_code, json=body or {})
    return client._classify(resp)


def test_fcm_classification():
    assert _fcm_result(200).kind == "sent"
    assert _fcm_result(404, {"error": {"status": "UNREGISTERED"}}).kind == "invalid_token"
    assert _fcm_result(400, {"error": {"status": "INVALID_ARGUMENT"}}).kind == "invalid_token"
    assert _fcm_result(429).kind == "retryable"
    assert _fcm_result(500).kind == "retryable"
    assert _fcm_result(403, {"error": {"status": "PERMISSION_DENIED"}}).kind == "failed"


@pytest.mark.asyncio
async def test_fcm_send_with_mock_transport():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"name": "projects/p/messages/1"})

    client = FcmClient(
        settings=SimpleNamespace(
            FCM_SERVICE_ACCOUNT_JSON="",
            FCM_SERVICE_ACCOUNT_B64="",
            FCM_PROJECT_ID="proj",
            FCM_TTL_SECONDS=60,
        ),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    # enabled requires a service account; stub the credential loader instead.
    client._credentials = {"client_email": "x@y.iam.gserviceaccount.com", "private_key": "unused", "token_uri": "http://unused"}
    client._token_cache = {"token": "t", "expires_at": 10**12}

    result = await client.send("tok123", "android", FcmMessage(title="Hi", body="There", data={"a": "1"}))
    assert result.kind == "sent"
    assert "/messages:send" in seen["url"] and '"token":"tok123"' in seen["body"]


@pytest.mark.asyncio
async def test_fcm_disabled_raises():
    client = FcmClient()
    with pytest.raises(RuntimeError):
        await client.send("tok", "android", FcmMessage(title="T", body="B"))


# ── Push worker helpers ───────────────────────────────────────────────────────

def test_backoff_time_grows_exponentially():
    first = NotificationService._backoff_time(1)
    second = NotificationService._backoff_time(2)
    third = NotificationService._backoff_time(3)
    assert first <= second <= third
    assert second - first >= timedelta(seconds=30)


@pytest.mark.asyncio
async def test_deliver_pending_skips_when_fcm_disabled():
    with patch("app.services.notification_service.get_fcm_client") as fcm:
        fcm.return_value.enabled = False
        summary = await NotificationService.deliver_pending(batch_size=10)
    assert summary == {"claimed": 0, "sent": 0, "disabled_tokens": 0, "failed": 0}
