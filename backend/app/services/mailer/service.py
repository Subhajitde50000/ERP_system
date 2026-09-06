"""
Mailer — Public API

The rest of the application only ever calls:

    from app.services.mailer import queue_email, send_email

    queue_email(db, "owner.verify_email", to=email,
                context={"name": n, "verify_url": url})   # row in outbox
    await send_email("owner.verify_email", to=email, context={...})  # immediate

Neither call knows or cares which provider is active. Switching
providers changes nothing in any caller.

Why queue by default: provisioning runs in ONE transaction (SYSTEM-FLOW §2.1).
An SMTP round-trip inside that transaction would hold locks open and, worse, a
mail outage would roll back a paid signup. So callers write an `outbox_emails`
row in the same transaction, and `deliver_outbox()` sends it afterwards —
retried, never blocking the commit.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.billing import OutboxEmail
from app.services.mailer.base import MailMessage, SendResult
from app.services.mailer.registry import available, resolve
from app.services.mailer.templates import known_events, render

MAX_ATTEMPTS = 5


def get_provider():
    """The provider selected by EMAIL_PROVIDER / registry.py, resolved fresh."""
    return resolve(get_settings().EMAIL_PROVIDER, get_settings())


def build_message(
    event: str,
    to: str,
    context: dict[str, Any] | None = None,
    tenant_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> MailMessage:
    """Render an event into a provider-neutral message (shared by both paths)."""
    ctx = dict(context or {})
    content = render(event, ctx)
    return MailMessage(
        to=to,
        subject=content.subject,
        text=content.text,
        html=content.html,
        event=event,
        tenant_id=tenant_id,
        context=ctx,
        idempotency_key=idempotency_key,
    )


# ── Queue (transaction-safe) ──────────────────────────────────────────────────

def queue_email(
    db: AsyncSession,
    event: str,
    to: str,
    context: dict[str, Any] | None = None,
    tenant_id: uuid.UUID | None = None,
) -> OutboxEmail:
    """
    Render now, send later. Adds the row to the caller's session WITHOUT
    committing, so the email lives or dies with the surrounding transaction.
    The rendered context is stashed on the instance for the same-request
    delivery path; the DB row keeps subject/body for auditing and retries.
    """
    msg = build_message(event, to, context, tenant_id)
    row = OutboxEmail(
        id=uuid.uuid4(),
        event=event,
        to_address=to,
        subject=msg.subject,
        body=msg.text,
        status="QUEUED",
        tenant_id=tenant_id,
    )
    # Carried in memory only (no schema change) so deliver_now() can reuse the
    # rich context instead of re-deriving it from the flat body text.
    row._mail_context = msg.context  # type: ignore[attr-defined]
    db.add(row)
    return row


async def deliver_row(db: AsyncSession, row: OutboxEmail) -> SendResult:
    """Send one outbox row and record the outcome. Never raises."""
    context = getattr(row, "_mail_context", None) or {
        "subject": row.subject,
        "body": row.body,
    }
    msg = build_message(
        row.event,
        row.to_address,
        context,
        row.tenant_id,
        idempotency_key=str(row.id),
    )
    # A queued row stores the rendered subject/body; trust it over re-rendering
    # so an edited template never changes an email already shown to the user.
    msg.subject = row.subject or msg.subject
    if not getattr(row, "_mail_context", None):
        msg.text = row.body or msg.text

    result = await get_provider().send(msg)

    row.attempts = (row.attempts or 0) + 1
    if result.ok:
        row.status = "SENT"
    elif result.permanent or row.attempts >= MAX_ATTEMPTS:
        row.status = "FAILED"
    else:
        row.status = "QUEUED"  # picked up by the next drain
    await db.flush()
    return result


async def deliver_outbox(db: AsyncSession, limit: int = 50) -> dict[str, Any]:
    """
    Drain queued emails. Call from a worker, a cron job, or POST /email/outbox/drain.
    Rows that fail transiently stay QUEUED until MAX_ATTEMPTS.
    """
    res = await db.execute(
        select(OutboxEmail)
        .where(OutboxEmail.status == "QUEUED", OutboxEmail.attempts < MAX_ATTEMPTS)
        .order_by(OutboxEmail.created_at)
        .limit(limit)
    )
    rows = list(res.scalars().all())

    sent = failed = 0
    errors: list[str] = []
    for row in rows:
        result = await deliver_row(db, row)
        if result.ok:
            sent += 1
        else:
            failed += 1
            errors.append(f"{row.to_address}: {result.error}")

    await db.commit()
    return {
        "provider": get_provider().name,
        "picked": len(rows),
        "sent": sent,
        "failed": failed,
        "errors": errors[:10],
    }


# ── Immediate send (no DB) ────────────────────────────────────────────────────

async def send_email(
    event: str,
    to: str,
    context: dict[str, Any] | None = None,
    tenant_id: uuid.UUID | None = None,
) -> SendResult:
    """Fire-and-report send with no outbox row. Used by the test endpoint."""
    return await get_provider().send(build_message(event, to, context, tenant_id))


# ── Introspection ─────────────────────────────────────────────────────────────

def provider_status() -> dict[str, Any]:
    """Health payload for GET /email/status — safe to expose (no secrets)."""
    settings = get_settings()
    active = get_provider()
    return {
        "configured_provider": settings.EMAIL_PROVIDER,
        "active_provider": active.name,
        "registered_providers": available(),
        "from_address": settings.EMAIL_FROM or None,
        "sending_enabled": active.name != "console",
        "details": active.describe(),
        "known_events": known_events(),
    }
