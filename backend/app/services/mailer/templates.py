"""
Mailer — Email content, defined exactly once

Every transactional email in the product lives here, keyed by event name.
The provider does not own copy: each transport sends these rendered strings directly.
Change the wording here and every email changes.

The HTML shell (`_layout`) is also shared, so a branding tweak is a one-line
edit rather than an edit per template.

Add an email:
    @template("thing.happened")
    def _thing(ctx): return Rendered(subject=..., text=..., html=_layout(...))
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import Any

BRAND = "shikshasync.me ERP"


@dataclass(slots=True)
class Rendered:
    subject: str
    text: str
    html: str


TemplateFn = Callable[[dict[str, Any]], Rendered]
_REGISTRY: dict[str, TemplateFn] = {}


def template(event: str) -> Callable[[TemplateFn], TemplateFn]:
    """Register a renderer under an outbox event name."""

    def wrap(fn: TemplateFn) -> TemplateFn:
        _REGISTRY[event] = fn
        return fn

    return wrap


def known_events() -> list[str]:
    return sorted(_REGISTRY)


def render(event: str, context: dict[str, Any] | None = None) -> Rendered:
    """
    Render an event. Unknown events fall back to a generic body built from
    `subject` / `body` in the context, so ad-hoc mail still works.
    """
    ctx = dict(context or {})
    fn = _REGISTRY.get(event)
    if fn is None:
        return _generic(event, ctx)
    return fn(ctx)


# ── Shared building blocks (written once, used by every template) ─────────────

def _layout(title: str, intro: str, blocks: list[str], footer: str = "") -> str:
    """The one HTML shell every email uses."""
    body = "\n".join(blocks)
    tail = (
        f'<p style="margin:24px 0 0;color:#6b7280;font-size:13px;line-height:20px">'
        f"{footer}</p>"
        if footer
        else ""
    )
    return f"""\
<!doctype html>
<html><body style="margin:0;padding:24px;background:#f4f5f7;
 font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111827">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
   style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;
   border:1px solid #e5e7eb"><tr><td style="padding:32px">
    <p style="margin:0 0 4px;font-size:13px;letter-spacing:.08em;
     text-transform:uppercase;color:#6366f1;font-weight:600">{escape(BRAND)}</p>
    <h1 style="margin:0 0 16px;font-size:22px;line-height:30px">{escape(title)}</h1>
    <p style="margin:0 0 20px;font-size:15px;line-height:24px;color:#374151">{intro}</p>
    {body}
    {tail}
  </td></tr></table>
</body></html>"""


def _button(url: str, label: str) -> str:
    return (
        f'<p style="margin:0 0 20px"><a href="{escape(url)}" '
        'style="display:inline-block;padding:12px 22px;background:#4f46e5;color:#fff;'
        'text-decoration:none;border-radius:8px;font-size:15px;font-weight:600">'
        f"{escape(label)}</a></p>"
        f'<p style="margin:0 0 20px;font-size:13px;line-height:20px;color:#6b7280;'
        f'word-break:break-all">Or paste this link: {escape(url)}</p>'
    )


def _facts(rows: list[tuple[str, str]]) -> str:
    """Key/value table used by provisioning-style emails."""
    cells = "".join(
        f'<tr><td style="padding:6px 0;font-size:14px;color:#6b7280">{escape(k)}</td>'
        f'<td style="padding:6px 0;font-size:14px;color:#111827;font-weight:600">'
        f"{escape(v)}</td></tr>"
        for k, v in rows
        if v
    )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"'
        ' style="margin:0 0 20px;border-top:1px solid #e5e7eb;'
        f'border-bottom:1px solid #e5e7eb">{cells}</table>'
    )


def _code(value: str) -> str:
    return (
        '<p style="margin:0 0 20px;padding:12px 16px;background:#f3f4f6;'
        'border-radius:8px;font-family:ui-monospace,Menlo,monospace;font-size:14px;'
        f'word-break:break-all">{escape(value)}</p>'
    )


def _greeting(ctx: dict[str, Any]) -> str:
    name = str(ctx.get("name") or "").strip()
    return f"Hi {name}," if name else "Hi,"


# ── Templates ─────────────────────────────────────────────────────────────────

@template("owner.verify_email")
def _owner_verify(ctx: dict[str, Any]) -> Rendered:
    url = str(ctx.get("verify_url", ""))
    hi = _greeting(ctx)
    return Rendered(
        subject=f"Verify your {BRAND} account",
        text=(
            f"{hi}\n\nVerify your email to activate your platform account:\n"
            f"{url}\n\nThis link expires in 24 hours.\n"
            "If you did not create this account, you can ignore this email."
        ),
        html=_layout(
            "Verify your email",
            f"{escape(hi)} confirm your address to activate your platform account.",
            [_button(url, "Verify email")],
            "This link expires in 24 hours. If you did not create this "
            "account, you can safely ignore this email.",
        ),
    )


@template("platform_owner.verify_email")
def _platform_owner_verify(ctx: dict[str, Any]) -> Rendered:
    token = str(ctx.get("token", ""))
    url = str(ctx.get("verify_url", ""))
    hi = _greeting(ctx)
    action = _button(url, "Verify account") if url else _code(token)
    return Rendered(
        subject=f"Verify your {BRAND} platform account",
        text=(
            f"{hi}\n\nWelcome to {BRAND}. Verify your platform account before "
            f"creating institutions.\n\n"
            + (f"{url}\n\n" if url else "")
            + (f"Verification token: {token}\n" if token else "")
        ),
        html=_layout(
            "Verify your platform account",
            f"{escape(hi)} verify your account before creating institutions.",
            [action],
            "If you did not request this, you can ignore this email.",
        ),
    )


@template("owner.password_reset")
def _owner_password_reset(ctx: dict[str, Any]) -> Rendered:
    url = str(ctx.get("reset_url", ""))
    minutes = str(ctx.get("expires_minutes", 30))
    hi = _greeting(ctx)
    return Rendered(
        subject=f"Reset your {BRAND} password",
        text=(
            f"{hi}\n\nWe received a request to reset your password:\n{url}\n\n"
            f"This link expires in {minutes} minutes.\n"
            "If you did not request a reset, no action is needed."
        ),
        html=_layout(
            "Reset your password",
            f"{escape(hi)} we received a request to reset your password.",
            [_button(url, "Choose a new password")],
            f"This link expires in {escape(minutes)} minutes. If you did not "
            "request a reset, no action is needed and your password stays the same.",
        ),
    )


@template("tenant.password_reset")
def _tenant_password_reset(ctx: dict[str, Any]) -> Rendered:
    """Password reset email for institution users (teachers, students, parents…).

    Context keys:
        name            str  — user display name (optional, falls back to "Hi,")
        reset_url       str  — full HTTPS reset link including raw token
        expires_minutes int  — token lifetime shown to the user (default 30)
        institution     str  — institution name (optional, adds context)
    """
    url = str(ctx.get("reset_url", ""))
    minutes = str(ctx.get("expires_minutes", 30))
    institution = str(ctx.get("institution", "")).strip()
    hi = _greeting(ctx)
    context_line = f" for your {escape(institution)} account" if institution else ""
    return Rendered(
        subject=f"Reset your password{' — ' + institution if institution else ''}",
        text=(
            f"{hi}\n\n"
            f"We received a password reset request{context_line}:\n"
            f"{url}\n\n"
            f"This link expires in {minutes} minutes.\n"
            "If you did not request a reset, no action is needed — "
            "your password has not changed."
        ),
        html=_layout(
            "Reset your password",
            (
                f"{escape(hi)} we received a password reset request"
                f"{context_line}."
            ),
            [_button(url, "Choose a new password")],
            (
                f"This link expires in {escape(minutes)} minutes. "
                "If you did not request a reset, no action is needed and "
                "your password stays the same."
            ),
        ),
    )


@template("tenant.provisioned")
def _tenant_provisioned(ctx: dict[str, Any]) -> Rendered:
    tenant = str(ctx.get("tenant_name", "your institution"))
    login_url = str(ctx.get("login_url", ""))
    dashboard = str(ctx.get("dashboard_url", ""))
    plan = str(ctx.get("plan_name", ""))
    modules = ctx.get("modules") or []
    module_line = ", ".join(str(m) for m in modules) or "core modules"
    return Rendered(
        subject=f"Welcome to {tenant} — your ERP is ready",
        text=(
            f"Your institution {tenant} has been created.\n\n"
            f"Platform dashboard: {dashboard}\n"
            f"Institution login URL: {login_url}\n"
            f"Plan: {plan}\n"
            f"Modules: {module_line}\n\n"
            "Set your password and complete the setup wizard to get started."
        ),
        html=_layout(
            f"{tenant} is ready",
            "Your institution has been provisioned and is ready to use.",
            [
                _facts(
                    [
                        ("Plan", plan),
                        ("Modules", module_line),
                        ("Admin", str(ctx.get("admin_email", ""))),
                    ]
                ),
                _button(login_url, "Open your institution"),
                (
                    f'<p style="margin:0;font-size:14px;color:#374151">Manage billing '
                    f'and invoices from your <a href="{escape(dashboard)}" '
                    f'style="color:#4f46e5">platform dashboard</a>.</p>'
                    if dashboard
                    else ""
                ),
            ],
            "Set your password and complete the setup wizard to get started.",
        ),
    )


@template("staff.invited")
def _staff_invited(ctx: dict[str, Any]) -> Rendered:
    tenant = str(ctx.get("tenant_name", "your institution"))
    url = str(ctx.get("invite_url", ""))
    hi = _greeting(ctx)
    return Rendered(
        subject=f"You are invited to {tenant}",
        text=(
            f"{hi}\n\nYou have been added to {tenant} on {BRAND}.\n"
            f"Set your password to activate your account:\n{url}\n\n"
            "This link expires in 7 days."
        ),
        html=_layout(
            f"You are invited to {tenant}",
            f"{escape(hi)} an account has been created for you on {escape(BRAND)}.",
            [_button(url, "Set your password")],
            "This invitation link expires in 7 days.",
        ),
    )


@template("parent.link_invited")
def _parent_link_invited(ctx: dict[str, Any]) -> Rendered:
    """The activation slip, in the inbox instead of on paper.

    The code is the capability, so it is shown once and only in an email that
    goes to the address the school recorded for this exact guardian. Claiming
    clears it, which is why a re-send issues a new one rather than repeating this.
    """
    tenant = str(ctx.get("tenant_name", "your child's school"))
    student = str(ctx.get("student_name", "your child"))
    code = str(ctx.get("code", ""))
    url = str(ctx.get("claim_url", ""))
    days = ctx.get("days")
    return Rendered(
        subject=f"{tenant} — activate your parent access for {student}",
        text=(
            f"{tenant} has linked you to {student}.\n\n"
            f"Activation code: {code}\n"
            f"Enter it here to open the parent portal: {url}\n\n"
            + (f"This code expires in {days} days.\n" if days else "")
            + "If you did not expect this, no action is needed — nothing is shared until the code is used."
        ),
        html=_layout(
            f"Activate your parent access for {student}",
            f"{escape(tenant)} has linked you to {escape(student)} so you can follow "
            f"attendance, exams, results and fees.",
            [
                _code(code),
                _button(url, "Claim my access"),
                _facts([("Expiry", f"{days} days" if days else "")]),
            ],
            "The code works once. If you did not expect this email, no action is "
            "needed — nothing is shared until it is used.",
        ),
    )


@template("parent.account_created")
def _parent_account_created(ctx: dict[str, Any]) -> Rendered:
    """Receipt for self-service activation, so a surprise login is visible."""
    tenant = str(ctx.get("tenant_name", "your child's school"))
    student = str(ctx.get("student_name", "your child"))
    url = str(ctx.get("login_url", ""))
    hi = _greeting(ctx)
    return Rendered(
        subject=f"Your {tenant} parent account is ready",
        text=(
            f"{hi}\n\nYour parent account for {student} at {tenant} is active.\n"
            f"Sign in here: {url}\n\n"
            "If you did not just create this account, contact the school office "
            "and change your password."
        ),
        html=_layout(
            f"Your parent account at {tenant} is ready",
            f"{escape(hi)} your access to {escape(student)}'s record is now active.",
            [_button(url, "Open the parent portal")],
            "Did not just sign up? Contact the school office — the account was created "
            "with the invitation code, so a stranger would need your slip.",
        ),
    )


@template("mailer.test")
def _mailer_test(ctx: dict[str, Any]) -> Rendered:
    note = str(ctx.get("note", "Your email configuration works."))
    provider = str(ctx.get("provider", "unknown"))
    return Rendered(
        subject=f"{BRAND} — test email ({provider})",
        text=f"{note}\n\nProvider: {provider}\n",
        html=_layout(
            "Test email",
            escape(note),
            [_facts([("Provider", provider)])],
            "Sent from the /email/test endpoint.",
        ),
    )


def _generic(event: str, ctx: dict[str, Any]) -> Rendered:
    """Fallback for events with no registered template."""
    subject = str(ctx.get("subject") or f"{BRAND} notification")
    text = str(ctx.get("body") or "")
    return Rendered(
        subject=subject,
        text=text,
        html=_layout(
            subject,
            escape(text).replace("\n", "<br>"),
            [],
            f"Event: {escape(event)}",
        ),
    )
