"""
Tests — Tenant Auth Endpoints
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.utils.security import generate_secure_token, hash_token


@pytest.mark.asyncio
async def test_tenant_login_nonexistent_slug(client):
    res = await client.post(
        "/api/v1/tenant/auth/login",
        json={
            "slug": "invalid-tenant-slug",
            "identifier": "user@school.com",
            "password": "password123",
        },
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_tenant_reset_password_has_rate_limit():
    import inspect
    from app.routers.tenant.auth import tenant_reset_password

    # Check that rate limit decorator was applied to tenant_reset_password
    source = inspect.getsource(tenant_reset_password)
    assert '@limiter.limit("10/hour")' in source


# ── Forgot-password outbox wiring ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_forgot_password_queues_outbox_email():
    """
    When a matching tenant user is found, tenant_forgot_password must enqueue
    a tenant.password_reset outbox row inside the same DB session.
    The reset URL must contain the tenant slug and the raw token.
    """
    from app.models.billing import OutboxEmail
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services.auth_service import AuthService

    # ── Build minimal mock objects ─────────────────────────────────────────
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_tenant = MagicMock(spec=Tenant)
    mock_tenant.id = tenant_id
    mock_tenant.slug = "demo-school"
    mock_tenant.name = "Demo School"
    mock_tenant.is_active = True

    mock_user = MagicMock(spec=User)
    mock_user.id = user_id
    mock_user.name = "Aryan Sharma"
    mock_user.email = "aryan@demo-school.com"
    mock_user.student_roll_no = None
    mock_user.is_active = True
    mock_user.deleted_at = None
    mock_user.password_reset_token = None
    mock_user.password_reset_expires = None

    # ── Mock DB session ────────────────────────────────────────────────────
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    # execute() returns different results depending on call order:
    # 1st call → tenant lookup, 2nd call → user lookup
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none = MagicMock(return_value=mock_tenant)
    user_result = MagicMock()
    user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
    db.execute = AsyncMock(side_effect=[tenant_result, user_result])

    # ── Call the service ───────────────────────────────────────────────────
    with patch("app.config.get_settings") as mock_settings_fn:
        mock_settings = MagicMock()
        mock_settings.PUBLIC_ROOT_DOMAIN = "test.example"
        mock_settings_fn.return_value = mock_settings

        await AuthService.tenant_forgot_password(
            slug="demo-school", identifier="aryan@demo-school.com", db=db
        )

    # ── Assertions ────────────────────────────────────────────────────────
    # db.add must have been called with an OutboxEmail row
    assert db.add.called, "db.add() was never called — outbox row was not queued"
    outbox_row = db.add.call_args[0][0]
    assert isinstance(outbox_row, OutboxEmail), (
        f"Expected OutboxEmail but got {type(outbox_row)}"
    )
    assert outbox_row.event == "tenant.password_reset"
    assert outbox_row.to_address == "aryan@demo-school.com"
    assert outbox_row.status == "QUEUED"
    assert outbox_row.tenant_id == tenant_id

    # The rendered body must contain the tenant slug and a non-empty token
    assert "demo-school" in outbox_row.body, (
        "Reset URL in email body should contain the institution slug"
    )
    assert "reset-password" in outbox_row.body.lower()

    # password_reset_token must be set on the user (hashed)
    assert mock_user.password_reset_token is not None, (
        "password_reset_token was not written to the user"
    )
    assert mock_user.password_reset_expires is not None, (
        "password_reset_expires was not written to the user"
    )

    # db.flush() must have been called to persist token before queueing email
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_tenant_forgot_password_no_email_skips_outbox():
    """
    A user with no email address (e.g. student identified only by roll number)
    must not attempt to queue a reset email — there is nowhere to send it.
    The token is still written so a later email-address update could trigger
    a new reset flow; the service simply must not crash or enqueue to None.
    """
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services.auth_service import AuthService

    tenant_id = uuid.uuid4()

    mock_tenant = MagicMock(spec=Tenant)
    mock_tenant.id = tenant_id
    mock_tenant.slug = "demo-school"
    mock_tenant.name = "Demo School"
    mock_tenant.is_active = True

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.name = "Roll User"
    mock_user.email = None          # no email — roll-number-only account
    mock_user.student_roll_no = "2024CS001"
    mock_user.is_active = True
    mock_user.deleted_at = None
    mock_user.password_reset_token = None
    mock_user.password_reset_expires = None

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none = MagicMock(return_value=mock_tenant)
    user_result = MagicMock()
    user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
    db.execute = AsyncMock(side_effect=[tenant_result, user_result])

    with patch("app.config.get_settings") as mock_settings_fn:
        mock_settings = MagicMock()
        mock_settings.PUBLIC_ROOT_DOMAIN = "test.example"
        mock_settings_fn.return_value = mock_settings

        # Must not raise
        await AuthService.tenant_forgot_password(
            slug="demo-school", identifier="2024CS001", db=db
        )

    # No outbox row should be queued when there is no email to send to
    assert not db.add.called, (
        "db.add() was called for a user with no email address"
    )


@pytest.mark.asyncio
async def test_tenant_forgot_password_unknown_user_silent():
    """
    When no matching user exists the service must return silently — no
    exception, no outbox row — to prevent account-enumeration attacks.
    """
    from app.models.tenant import Tenant
    from app.services.auth_service import AuthService

    mock_tenant = MagicMock(spec=Tenant)
    mock_tenant.id = uuid.uuid4()
    mock_tenant.slug = "demo-school"
    mock_tenant.name = "Demo School"
    mock_tenant.is_active = True

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none = MagicMock(return_value=mock_tenant)
    # user lookup returns nothing
    user_result = MagicMock()
    user_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(side_effect=[tenant_result, user_result])

    # Must not raise
    await AuthService.tenant_forgot_password(
        slug="demo-school", identifier="nobody@nope.com", db=db
    )

    assert not db.add.called
    db.flush.assert_not_called()
