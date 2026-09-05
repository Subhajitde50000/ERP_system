"""
ERP Backend — Settings

All configuration is loaded from environment variables (or a .env file).
Validated at startup — a missing required variable crashes immediately,
not at the first request.
"""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the .env path relative to this file so it is found regardless of
# the working directory uvicorn (or its --reload subprocess) was launched from.
_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    # WebRTC relay for the live classroom (see doc/deploy-coturn.md).
    # TURN_URL e.g. "turn:turn.example.com:3478" or "turns:...:5349" (TLS);
    # with static shared-secret auth set username/credential accordingly.
    TURN_URL: str = ""
    TURN_USERNAME: str = ""
    TURN_CREDENTIAL: str = ""
    # SFU (Selective Forwarding Unit) configuration (LiveKit / mediasoup / Janus)
    SFU_ENABLED: bool = False
    SFU_URL: str = ""
    SFU_API_KEY: str = ""
    SFU_API_SECRET: str = ""
    # Set to false on API-only workers; run one scheduler-enabled worker
    # (or a dedicated worker process) to own the background jobs.
    SCHEDULER_ENABLED: bool = True

    def ice_servers(self) -> list[dict]:
        """ICE server list for the live-classroom WebRTC peers.

        STUN is enough on open networks; TURN (relay) is what gets calls
        through symmetric NATs and strict firewalls. TURN is only offered
        when fully configured — a half-configured relay would just produce
        failing candidates. Supports comma-separated URLs (e.g. turn: and turns:).
        """
        servers = [{"urls": "stun:stun.l.google.com:19302"}]
        if self.TURN_URL and self.TURN_USERNAME and self.TURN_CREDENTIAL:
            urls = [u.strip() for u in self.TURN_URL.split(",") if u.strip()]
            servers.append(
                {
                    "urls": urls if len(urls) > 1 else (urls[0] if urls else self.TURN_URL),
                    "username": self.TURN_USERNAME,
                    "credential": self.TURN_CREDENTIAL,
                }
            )
        return servers

    # ── Online Class ──────────────────────────────────────────────────────────
    # Max concurrent WebSocket connections per live room (per worker).
    # With Redis pub/sub this is per-worker; total capacity = workers × limit.
    WS_MAX_ROOM_PARTICIPANTS: int = 500
    # Maximum file upload size for class materials / recordings (MB).
    ONLINE_CLASS_UPLOAD_MAX_MB: int = 25
    # ── File storage (B6): private, tenant-prefixed, signed-URL access ──────
    # "local" = private disk under UPLOAD_FILE_ROOT (single instance);
    # "s3"    = object storage (S3/R2/MinIO, multi-instance + durable).
    STORAGE_BACKEND: str = "local"
    UPLOAD_FILE_ROOT: str = "uploads"
    # How long vended file links stay valid (S3 presigned URLs share this).
    UPLOAD_SIGNED_URL_TTL_SECONDS: int = 900
    # S3 backend settings. S3_BUCKET is required when STORAGE_BACKEND=s3;
    # credentials may be omitted when the workload runs on an IAM role.
    S3_BUCKET: str = ""
    S3_REGION: str = ""
    S3_ENDPOINT_URL: str = ""      # e.g. MinIO https://minio.internal:9000
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_KEY_PREFIX: str = ""        # optional bucket-internal prefix
    # Use path-style URLs (required for MinIO / self-hosted stores).
    # Set to false for AWS S3 / Cloudflare R2 (virtual-hosted-style).
    S3_FORCE_PATH_STYLE: bool = False
    # Comma-separated MIME-type allowlist for shared class files.
    ONLINE_CLASS_ALLOWED_MIME_TYPES: str = (
        "application/pdf,"
        "application/msword,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.ms-excel,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.ms-powerpoint,"
        "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
        "image/jpeg,image/png,image/gif,image/webp,image/svg+xml,"
        "video/mp4,video/webm,video/ogg,"
        "audio/mpeg,audio/ogg,audio/wav,"
        "text/plain,text/csv"
    )

    @property
    def allowed_mime_set(self) -> set[str]:
        return {m.strip() for m in self.ONLINE_CLASS_ALLOWED_MIME_TYPES.split(",") if m.strip()}

    # ── Firebase Cloud Messaging (Android / iOS / web push) ──────────────────
    # Remote push is sent through the FCM v1 HTTP API. Two ways to provide the
    # Firebase service-account credentials (a Google Cloud service account with
    # the "Firebase Cloud Messaging API" enabled):
    #   1. FCM_SERVICE_ACCOUNT_JSON    – path to the downloaded JSON file
    #   2. FCM_SERVICE_ACCOUNT_B64     – base64 of the same JSON (useful on
    #                                    platforms where secrets live in env)
    # When neither is set, remote push is disabled and only the in-app DB
    # inbox is written (safe default for development / tests).
    FCM_SERVICE_ACCOUNT_JSON: str = ""
    FCM_SERVICE_ACCOUNT_B64: str = ""
    # Optional project id override; usually read from the service-account file.
    FCM_PROJECT_ID: str = ""
    # Default time-to-live applied to FCM messages.
    FCM_TTL_SECONDS: int = 86400
    # How many outbox rows the background delivery worker claims per run.
    NOTIFICATION_PUSH_BATCH_SIZE: int = 100

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    # ── Signup / provisioning ─────────────────────────────────────────────────
    # Root domain used to build login URLs and subdomain checks, e.g.
    # https://green.xyz.com/login — defaults to xyz.com.
    PUBLIC_ROOT_DOMAIN: str = "xyz.com"
    TRIAL_DAYS: int = 14
    TENANT_DEFAULT_TIMEZONE: str = "Asia/Kolkata"

    # ── Email ─────────────────────────────────────────────────────────────────
    # Which transport actually sends mail:
    #   google  → Gmail / Workspace SMTP   (app/services/mailer/providers/google.py)
    #   klaviyo → Klaviyo Events API       (app/services/mailer/providers/klaviyo.py)
    #   console → log only, never delivers (safe default for dev/tests)
    # A provider that is commented out in mailer/registry.py is ignored here.
    EMAIL_PROVIDER: str = "console"
    # Envelope identity — shared by both providers.
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = "xyz.com ERP"
    EMAIL_REPLY_TO: str = ""
    EMAIL_TIMEOUT_SECONDS: int = 20

    # -- Google (SMTP) --
    # GOOGLE_SMTP_PASSWORD must be a 16-char App Password, not the account
    # password: https://myaccount.google.com/apppasswords
    GOOGLE_SMTP_HOST: str = "smtp.gmail.com"
    GOOGLE_SMTP_PORT: int = 587          # 587 = STARTTLS, 465 = implicit TLS
    GOOGLE_SMTP_USER: str = ""
    GOOGLE_SMTP_PASSWORD: str = ""

    # -- Klaviyo (Events API) --
    # Private key (pk_...) with Events:write + Profiles:write scopes.
    KLAVIYO_API_KEY: str = ""
    KLAVIYO_API_REVISION: str = "2024-10-15"
    # Metric name prefix — the flow trigger becomes e.g. "ERP owner.verify_email"
    KLAVIYO_METRIC_PREFIX: str = "ERP"


@lru_cache
def get_settings() -> Settings:
    """
    Cached singleton — settings are read once and reused everywhere.
    Use FastAPI's Depends(get_settings) to inject into route handlers.
    """
    # pydantic BaseSettings may require environment values at type-check time;
    # ignore static type checking here because values are provided via env/.env at runtime.
    return Settings()  # type: ignore[arg-type]
