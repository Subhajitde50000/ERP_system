"""
Firebase Cloud Messaging (FCM) v1 HTTP client.

Sends push messages to Android, iOS and web registration tokens using the
Firebase *v1* HTTP API without pulling in the whole ``firebase-admin`` SDK:

1. Build a signed JWT assertion from the Firebase service-account JSON,
2. exchange it at Google's OAuth2 token endpoint for an access token,
3. ``POST`` each message to ``https://fcm.googleapis.com/v1/projects/…/messages:send``.

The access token is cached and refreshed (with an ``asyncio.Lock`` so many
concurrent sends never stampede the token endpoint). The caller
(``notification_service.deliver_pending``) owns retries/backoff; this module
only classifies errors so the caller can decide whether a token is dead
(``UNREGISTERED`` / ``INVALID_ARGUMENT`` / ``SENDER_ID_MISMATCH``) or the
failure is transient (HTTP 429 / 5xx).

Usage is deliberately dependency-light: ``httpx`` and ``python-jose`` were
already backend dependencies (mailer + JWT auth).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from jose import jwt

from app.config import get_settings

logger = logging.getLogger(__name__)

_FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_OAUTH_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# FCM v1 error codes that mean "this registration token will never work again".
# The device token should be deactivated instead of retried.
TERMINAL_TOKEN_CODES = frozenset({"UNREGISTERED", "INVALID_ARGUMENT", "SENDER_ID_MISMATCH"})


class FcmDisabledError(RuntimeError):
    """Raised when Firebase credentials have not been configured."""


@dataclass(slots=True)
class FcmMessage:
    """A push message ready for Firebase (title/body + string data payload)."""

    title: str
    body: str
    data: dict[str, str] | None = None
    badge: int | None = None


@dataclass(slots=True)
class FcmResult:
    """Outcome of one send. ``kind`` is one of:

    * ``sent``          – Firebase accepted the message
    * ``invalid_token`` – terminal token error; caller should deactivate it
    * ``retryable``     – transient failure (quota/5xx); caller should retry
    * ``failed``        – permanent non-token error
    """

    kind: str
    error_code: str | None = None
    detail: str | None = None


class FcmClient:
    """Stateless-over-time client; access tokens are cached in the instance."""

    def __init__(self, settings=None, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._http = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http_client is None
        self._token_cache: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._credentials: dict[str, Any] | None = None

    # ── Configuration / credentials ──────────────────────────────────────────

    def _load_service_account(self) -> dict[str, Any] | None:
        """Read the service-account JSON (path or base64) exactly once."""
        if self._credentials is None:
            raw: str | None = None
            if self._settings.FCM_SERVICE_ACCOUNT_JSON:
                try:
                    raw = Path(self._settings.FCM_SERVICE_ACCOUNT_JSON).read_text(encoding="utf-8")
                except OSError as exc:  # pragma: no cover - environment dependent
                    logger.error("FCM: cannot read service-account file: %s", exc)
            elif self._settings.FCM_SERVICE_ACCOUNT_B64:
                try:
                    raw = base64.b64decode(self._settings.FCM_SERVICE_ACCOUNT_B64).decode("utf-8")
                except (ValueError, UnicodeDecodeError) as exc:  # pragma: no cover
                    logger.error("FCM: FCM_SERVICE_ACCOUNT_B64 is not valid base64 JSON: %s", exc)
            if raw:
                try:
                    self._credentials = json.loads(raw)
                except ValueError as exc:  # pragma: no cover
                    logger.error("FCM: service-account payload is not valid JSON: %s", exc)
                    self._credentials = None
        return self._credentials

    @property
    def project_id(self) -> str | None:
        return (
            self._settings.FCM_PROJECT_ID
            or (self._load_service_account() or {}).get("project_id")
            or None
        )

    @property
    def enabled(self) -> bool:
        return bool(self._load_service_account() and self.project_id)

    # ── OAuth2 access token ──────────────────────────────────────────────────

    async def _fetch_access_token(self, credentials: dict[str, Any]) -> str | None:
        """Exchange a signed JWT assertion for a short-lived access token."""
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": credentials["client_email"],
                "sub": credentials["client_email"],
                "aud": credentials["token_uri"],
                "iat": now,
                "exp": now + 3600,
                "scope": _OAUTH_SCOPE,
            },
            credentials["private_key"],
            algorithm="RS256",
        )
        resp = await self._http.post(
            _OAUTH_TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        if resp.status_code != 200:
            logger.error("FCM: OAuth token request failed: HTTP %s %s", resp.status_code, resp.text[:300])
            return None
        payload = resp.json()
        return payload.get("access_token")

    async def access_token(self) -> str | None:
        """Return a cached (or freshly minted) OAuth access token."""
        credentials = self._load_service_account()
        if not credentials:
            raise FcmDisabledError("Firebase Cloud Messaging is not configured")

        cached = self._token_cache.get("token")
        if cached and self._token_cache.get("expires_at", 0) > time.time() + 60:
            return cached

        async with self._lock:  # single-flight token refresh
            cached = self._token_cache.get("token")
            if cached and self._token_cache.get("expires_at", 0) > time.time() + 60:
                return cached
            token = await self._fetch_access_token(credentials)
            if token:
                self._token_cache = {
                    "token": token,
                    "expires_at": time.time() + 3600,  # tokens are valid ~1h
                }
            return token

    # ── Send ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_message(message: FcmMessage, token: str, platform: str) -> dict[str, Any]:
        """Translate our payload into the FCM v1 ``message`` body."""
        fcm: dict[str, Any] = {"token": token}

        # Visible title/body. FCM derives the tray notification from this for
        # Android; for web it must be duplicated in WebpushConfig (service
        # workers cannot read the top-level `notification` object reliably).
        fcm["notification"] = {"title": message.title, "body": message.body}

        if message.data:
            fcm["data"] = {str(k): str(v) for k, v in message.data.items()}

        # Android: high priority + TTL so time-critical notices arrive fast.
        ttl = get_settings().FCM_TTL_SECONDS
        fcm["android"] = {
            "priority": "HIGH",
            "ttl": f"{ttl}s",
            "notification": {"sound": "default", "click_action": "FLUTTER_NOTIFICATION_CLICK"},
        }

        # iOS: alert with sound + optional unread badge.
        apns_payload: dict[str, Any] = {"aps": {"sound": "default"}}
        if message.badge is not None:
            apns_payload["aps"]["badge"] = message.badge
        fcm["apns"] = {
            "headers": {"apns-priority": "10", "apns-push-type": "alert"},
            "payload": apns_payload,
        }

        if platform == "web":
            fcm["webpush"] = {
                "notification": {"title": message.title, "body": message.body, "requireInteraction": False},
                "fcm_options": {"link": "/notifications"},
            }
        return fcm

    async def send(self, token: str, platform: str, message: FcmMessage) -> FcmResult:
        """Deliver one message to one registration token."""
        if not self.enabled:
            raise FcmDisabledError("Firebase Cloud Messaging is not configured")
        project_id = self.project_id or ""
        access_token = await self.access_token()
        if not access_token:
            return FcmResult(kind="retryable", error_code="AUTH", detail="Could not obtain OAuth token")

        body = {"message": self._build_message(message, token, platform)}
        resp = await self._http.post(
            _FCM_SEND_URL.format(project_id=project_id),
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
        return self._classify(resp)

    @staticmethod
    def _classify(resp: httpx.Response) -> FcmResult:
        if resp.status_code == 200:
            return FcmResult(kind="sent")

        code: str | None = None
        detail: str | None = None
        try:
            payload = resp.json()
            reason = payload.get("error", {})
            code = reason.get("status") or reason.get("code")
            detail = reason.get("message") or resp.text[:300]
        except ValueError:  # non-JSON error body
            detail = resp.text[:300]

        if code in TERMINAL_TOKEN_CODES:
            return FcmResult(kind="invalid_token", error_code=code, detail=detail)
        if resp.status_code in (429, 500, 502, 503, 504) or code in ("UNAVAILABLE", "INTERNAL", "QUOTA_EXCEEDED"):
            return FcmResult(kind="retryable", error_code=code or str(resp.status_code), detail=detail)
        return FcmResult(kind="failed", error_code=code or str(resp.status_code), detail=detail)

    async def aclose(self) -> None:
        """Release the HTTP client (used by tests / graceful shutdown)."""
        if self._owns_http:
            await self._http.aclose()


# Module-level singleton so the whole process shares one token cache & client.
_client: FcmClient | None = None


def get_fcm_client(settings=None, http_client: httpx.AsyncClient | None = None) -> FcmClient:
    """Return the shared FCM client (overridable for tests)."""
    global _client
    if _client is None:
        _client = FcmClient(settings=settings, http_client=http_client)
    elif http_client is not None or settings is not None:
        # Tests inject their own transport/settings — give them a private client.
        return FcmClient(settings=settings, http_client=http_client)
    return _client


def fcm_enabled() -> bool:
    """Cheap global check used to skip outbox rows when push is off."""
    return get_fcm_client().enabled
