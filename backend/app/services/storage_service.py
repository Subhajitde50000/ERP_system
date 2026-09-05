"""File storage: one facade for every upload in the platform.

Why this exists (B6): uploads used to be written straight to ``backend/uploads``
and served by a *public* StaticFiles mount, so any file URL — student
submissions, notices, class recordings — was readable by anyone, forever, with
no tenant check. MIME "validation" trusted the client-declared Content-Type,
so a PHP webshell could be stored by claiming ``image/png``. And local disk
cannot survive container redeploys or serve multiple instances.

Design:

* **Two backends behind one interface** — ``local`` (private disk, default,
  fine for single-instance deployments) and ``s3`` (object storage for
  multi-instance/durable production). Chosen by ``STORAGE_BACKEND``.
* **Private by default** — files are only reachable through ``GET
  /api/v1/files/{key}?exp=…&sig=…``: an HMAC-signed, short-lived URL
  (same shape as an S3 presigned URL, so the local backend behaves like the
  cloud one). URLs are vended *by authenticated API responses* to users who
  are allowed to see the row; leaked links stop working when they expire.
* **Per-tenant prefixes** — every key starts with the tenant id
  (``{tenant}/{namespace}/{uuid}_{name}``), giving cheap isolation, per-tenant
  lifecycle/backup policies, and unambiguous ownership audits.
* **Content validation** — uploads are checked by *magic bytes*, not the
  client-declared MIME string; declared type and sniffed signature must agree
  (``application/octet-stream`` means "trust the sniff result"). Extensions
  are cross-checked against the sniffed type.
* **Legacy keys keep working** — rows written before this change reference
  ``/uploads/online-classes/…`` / ``/uploads/notices/…``; the storage layer
  strips the prefix and serves/signs them exactly like new keys, so no data
  migration is forced on day one.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, status

from app.config import get_settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# How long vended file URLs stay valid (seconds). Short enough that a leaked
# link is a bounded risk, long enough for a student to open a notice attachment
# or re-play a recording segment without a refetch.
DEFAULT_SIGNED_URL_TTL = 15 * 60


# ── Content sniffing (magic bytes) ────────────────────────────────────────────


# Magic-byte prefixes that pin the type on their own (everything else needs
# a structured check — see sniff_mime below).
_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"\x1a\x45\xdf\xa3", "video/webm"),  # EBML header (webm/matroska)
)

# Extension → canonical MIME for the cross-check. Deliberately mirrors the
# classroom + notice allowlists (see config.ONLINE_CLASS_ALLOWED_MIME_TYPES).
_EXT_MIME: dict[str, tuple[str, ...]] = {
    ".pdf": ("application/pdf",),
    ".png": ("image/png", "image/apng"),
    ".jpg": ("image/jpeg",), ".jpeg": ("image/jpeg",),
    ".gif": ("image/gif",),
    ".webp": ("image/webp",),
    ".webm": ("video/webm",),
    ".mp4": ("video/mp4",),
    ".ogg": ("audio/ogg", "video/ogg"),
    ".ogv": ("video/ogg",),
    ".mp3": ("audio/mpeg",),
    ".wav": ("audio/wav",),
    ".doc": ("application/msword",),
    ".xls": ("application/vnd.ms-excel",),
    ".ppt": ("application/vnd.ms-powerpoint",),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation",),
    ".zip": ("application/zip", "application/x-zip-compressed"),
    ".txt": ("text/plain",),
    ".csv": ("text/plain", "text/csv"),
    ".svg": ("image/svg+xml",),
}

# MIMEs the OLE2 / zip signatures may stand for (family-level proof: the exact
# office flavour cannot be told apart without parsing the container, which is
# fine — the container itself is the safety-relevant fact).
_OLE2_MIMES = ("application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint")
_ZIP_MIMES = (
    "application/zip", "application/x-zip-compressed",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
)

_SNIFF_HEAD = 64  # enough for every signature above


def _looks_like_text(head: bytes) -> bool:
    """Text-ish payloads have no binary signature; require printable content."""
    if not head:
        return False
    printable = sum(1 for b in head if 32 <= b < 127 or b in (9, 10, 13))
    return printable / len(head) > 0.95


def sniff_mime(head: bytes) -> str | None:
    """Best-effort content type from magic bytes.

    Returns ``None`` when the bytes match *no* known signature — callers treat
    that as "unrecognized content" and reject, which is the safe default for
    an upload pipeline (plain text is the one exception, see the tail check).
    """
    if not head:
        return None
    for prefix, mime in _PREFIXES:
        if head.startswith(prefix):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[4:8] == b"ftyp":
        return "video/mp4"
    if head[:4] == b"OggS":
        return "audio/ogg"
    if head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "application/x-cfb"
    if head[:2] == b"PK":
        return "application/zip"
    # SVG is the one text format in the allowlist — sniff by root element.
    if head.lstrip()[:5].lower() == b"<svg " or head.lstrip()[:4].lower() == b"<svg":
        return "image/svg+xml"
    if _looks_like_text(head):
        return "text/plain"
    return None


def validate_upload(declared: str, filename: str, head: bytes, allow_text: bool = True) -> str:
    """Agree on a content type or raise 415. Returns the effective MIME.

    Rules:
    * the sniffed signature must be one we recognise;
    * the declared MIME (when specific, not ``application/octet-stream``) must
      be consistent with the sniff result — this is what stops webshell bytes
      being stored as an image;
    * the file extension (when it maps to a known type) must agree with the
      bytes too — ``report.pdf`` containing a ZIP payload is rejected.
    """
    sniffed = sniff_mime(head)
    if sniffed is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content is not a recognised, allowed type",
        )
    if sniffed == "text/plain" and not allow_text:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Text uploads are not allowed here",
        )
    clean_declared = (declared or "").lower().split(";")[0].strip()
    if clean_declared and clean_declared != "application/octet-stream":
        if not _declared_matches(clean_declared, sniffed):
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File content does not match its declared type ({clean_declared})",
            )
    suffix = Path(filename or "").suffix.lower()
    if suffix in _EXT_MIME and sniffed not in _EXT_MIME[suffix]:
        # The extension maps to known types; accept only when the sniffed
        # signature is a valid container for one of them.
        if not any(_declared_matches(allowed, sniffed) for allowed in _EXT_MIME[suffix]):
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File content does not match its .{suffix.lstrip('.')} extension",
            )
    # Resolve a family-level sniff to the specific declared office type so
    # stored metadata and Content-Type headers stay precise.
    if sniffed == "application/x-cfb" and clean_declared in _OLE2_MIMES:
        return clean_declared
    if sniffed == "application/zip" and clean_declared in _ZIP_MIMES:
        return clean_declared
    if sniffed == "audio/ogg" and clean_declared == "video/ogg":
        return clean_declared
    if sniffed == "text/plain" and clean_declared in ("text/plain", "text/csv"):
        return clean_declared
    return sniffed


def _declared_matches(declared: str, sniffed: str | None) -> bool:
    if sniffed is None:
        return True
    if declared == sniffed:
        return True
    if sniffed == "application/x-cfb" and declared in _OLE2_MIMES:
        return True
    if sniffed == "application/zip" and declared in _ZIP_MIMES:
        return True
    if sniffed == "audio/ogg" and declared in ("audio/ogg", "video/ogg"):
        return True
    if sniffed == "image/png" and declared == "image/apng":
        return True
    if sniffed == "text/plain" and declared in ("text/plain", "text/csv"):
        return True
    # A sniffed container may back a declared text-ish csv… only for text.
    return False


# ── Stored-file contract ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    mime: str


def normalize_key(key_or_url: str) -> str:
    """Accept raw keys, legacy ``/uploads/…`` paths, and absolute URLs of ours."""
    key = (key_or_url or "").strip()
    if key.startswith("/uploads/"):
        key = key[len("/uploads/"):]
    elif key.startswith("uploads/"):
        key = key[len("uploads/"):]
    return key.lstrip("/")


def safe_filename(filename: str) -> str:
    """Filesystem-safe, length-capped name preserving the extension."""
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "")[:200]
    return clean or "file"


class Storage:
    """Local-disk or S3 backend with identical semantics."""

    def __init__(self) -> None:
        self._s3 = None  # lazy boto3 client (only when STORAGE_BACKEND=s3)

    # ── Configuration ─────────────────────────────────────────────────────

    @property
    def backend(self) -> str:
        return get_settings().STORAGE_BACKEND.lower()

    @property
    def root(self) -> Path:
        return PROJECT_ROOT / get_settings().UPLOAD_FILE_ROOT

    def _client(self):
        """boto3 client, created on first use. Import errors surface loudly —
        a deployment that asks for S3 without the dependency must not silently
        fall back to disk."""
        if self._s3 is None:
            try:
                import boto3  # noqa: PLC0415 - deliberately lazy
                from botocore.config import Config as BotocoreConfig  # noqa: PLC0415
            except ImportError as exc:  # pragma: no cover - depends on deploy
                raise RuntimeError(
                    "STORAGE_BACKEND=s3 requires the boto3 package (pip install boto3)"
                ) from exc
            settings = get_settings()
            # MinIO (and other self-hosted stores) require path-style URLs:
            # http://minio:9000/{bucket}/key  instead of  http://{bucket}.minio:9000/key
            addressing = "path" if settings.S3_FORCE_PATH_STYLE else "auto"
            self._s3 = boto3.client(
                "s3",
                region_name=settings.S3_REGION or None,
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
                aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
                config=BotocoreConfig(s3={"addressing_style": addressing}),
            )
        return self._s3

    # ── Writes ────────────────────────────────────────────────────────────

    async def save(
        self,
        tenant_id: uuid.UUID | str,
        namespace: str,
        filename: str,
        content: BinaryIO | bytes,
        declared_mime: str,
        *,
        max_bytes: int,
        sniff_bytes: int = _SNIFF_HEAD,
    ) -> StoredFile:
        """Validate and store one upload under a tenant-prefixed key.

        ``namespace`` is a slash-separated area, e.g. ``online-classes/{id}``
        or ``notices/{id}`` — it keeps related files groupable under the
        tenant without flattening everything into one directory.
        """
        # Sniff the head without consuming the stream: starlette's UploadFile
        # exposes async read/seek, byte payloads are sliced directly.
        if isinstance(content, (bytes, bytearray)):
            head = bytes(content[:sniff_bytes])
        else:
            head = (await content.read(sniff_bytes)) or b""
            await content.seek(0)
        mime = validate_upload(declared_mime, filename, head)

        key = f"{tenant_id}/{namespace}/{uuid.uuid4().hex}_{safe_filename(filename)}"
        size = await self._write(key, content, max_bytes)
        logger.info(
            "stored upload key=%s bytes=%d mime=%s backend=%s", key, size, mime, self.backend
        )
        return StoredFile(key=key, size=size, mime=mime)

    async def _write(self, key: str, content: BinaryIO | bytes, max_bytes: int) -> int:
        if self.backend == "s3":
            data = self._as_bytes(content, max_bytes)
            settings = get_settings()
            bucket = settings.S3_BUCKET
            s3_key = f"{self.s3_prefix}{key}"
            client = self._client()
            # boto3 is synchronous — run in a thread-pool executor so we never
            # block the event loop during upload (critical for large recordings).
            import asyncio  # noqa: PLC0415 - stdlib, always available
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: client.put_object(
                    Bucket=bucket,
                    Key=s3_key,
                    Body=data,
                    ContentType="application/octet-stream",
                ),
            )
            return len(data)

        target = self._local_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (bytes, bytearray)):
            if len(content) > max_bytes:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB limit",
                )
            target.write_bytes(bytes(content))
            return len(content)
        total = 0
        import anyio  # noqa: PLC0415 - stdlib-adjacent, always present with FastAPI

        async with await anyio.open_file(target, "wb") as out:
            while chunk := await content.read(64 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    await out.aclose()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB limit",
                    )
                await out.write(chunk)
        return total

    @staticmethod
    def _as_bytes(content: BinaryIO | bytes, max_bytes: int) -> bytes:
        if isinstance(content, (bytes, bytearray)):
            data = bytes(content)
        else:
            data = content.read()
        if len(data) > max_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB limit",
            )
        return data

    # ── Reads ─────────────────────────────────────────────────────────────

    @property
    def s3_prefix(self) -> str:
        """Optional key prefix inside the bucket (multi-tenant bucket layouts)."""
        return get_settings().S3_KEY_PREFIX or ""

    def _local_path(self, key: str) -> Path:
        """Resolve a key under the local root, refusing traversal attempts."""
        root = self.root.resolve()
        target = (root / normalize_key(key)).resolve()
        if not target.is_relative_to(root):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
        return target

    def signed_url(self, key_or_url: str, ttl: int | None = None) -> str:
        """Short-lived GET URL for a stored object.

        local → ``/api/v1/files/{key}?exp=…&sig=HMAC(key|exp)`` served by the
        authenticated-files router; s3 → a presigned GET (same expiry shape).
        """
        key = normalize_key(key_or_url)
        if not key:
            return ""
        expires_in = ttl if ttl is not None else get_settings().UPLOAD_SIGNED_URL_TTL_SECONDS
        if self.backend == "s3":
            return self._client().generate_presigned_url(
                "get_object",
                Params={"Bucket": get_settings().S3_BUCKET, "Key": f"{self.s3_prefix}{key}"},
                ExpiresIn=expires_in,
            )
        exp = int(time.time()) + expires_in
        sig = self._sign(key, exp)
        return f"/api/v1/files/{key}?exp={exp}&sig={sig}"

    def _sign(self, key: str, exp: int) -> str:
        secret = get_settings().JWT_SECRET_KEY.encode()
        digest = hmac.new(secret, f"{key}|{exp}".encode(), hashlib.sha256).hexdigest()
        return digest

    def verify(self, key: str, exp: int, sig: str) -> None:
        """Raise 403 unless the signature is valid and unexpired."""
        if exp < time.time():
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This file link has expired")
        expected = self._sign(normalize_key(key), exp)
        if not hmac.compare_digest(expected, (sig or "").lower()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid file link signature")

    def open_local(self, key: str) -> Path:
        """Path for FileResponse — only valid on the local backend."""
        path = self._local_path(key)
        if not path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
        return path

    def presign(self, key: str, ttl: int | None = None) -> str:
        """S3 presigned URL regardless of backend configuration (used by the
        files router to redirect on the s3 backend)."""
        return self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": get_settings().S3_BUCKET, "Key": f"{self.s3_prefix}{normalize_key(key)}"},
            ExpiresIn=ttl if ttl is not None else get_settings().UPLOAD_SIGNED_URL_TTL_SECONDS,
        )

    # ── Deletes ───────────────────────────────────────────────────────────

    def delete(self, key_or_url: str) -> None:
        key = normalize_key(key_or_url)
        if not key:
            return
        try:
            if self.backend == "s3":
                self._client().delete_object(
                    Bucket=get_settings().S3_BUCKET, Key=f"{self.s3_prefix}{key}"
                )
            else:
                self._local_path(key).unlink(missing_ok=True)
        except HTTPException:
            raise  # traversal attempts stay 404, not 500
        except Exception as exc:  # noqa: BLE001 - cleanup must not break deletes
            logger.warning("could not delete stored file key=%s: %s", key, exc)


#: The single instance every upload site shares — one policy, one code path.
storage = Storage()


def validate_storage_config() -> None:
    """Crash loudly at startup if the storage backend is misconfigured.

    Called from app.main on_startup so a missing S3_BUCKET is surfaced
    immediately — not silently at the first upload request hours later.
    """
    settings = get_settings()
    backend = settings.STORAGE_BACKEND.lower()
    if backend not in ("local", "s3"):
        raise RuntimeError(
            f"STORAGE_BACKEND={settings.STORAGE_BACKEND!r} is not recognised. "
            "Valid values are 'local' and 's3'."
        )
    if backend == "s3":
        if not settings.S3_BUCKET:
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires S3_BUCKET to be set. "
                "Add it to your .env file or Docker Compose environment variables. "
                "See backend/.env.example for the full S3/MinIO configuration block."
            )
        logger.info(
            "storage: s3 backend bucket=%s endpoint=%s prefix=%s path_style=%s",
            settings.S3_BUCKET,
            settings.S3_ENDPOINT_URL or "(AWS default)",
            settings.S3_KEY_PREFIX or "(none)",
            settings.S3_FORCE_PATH_STYLE,
        )
    else:
        logger.info(
            "storage: local backend root=%s signed_url_ttl=%ds",
            settings.UPLOAD_FILE_ROOT,
            settings.UPLOAD_SIGNED_URL_TTL_SECONDS,
        )
