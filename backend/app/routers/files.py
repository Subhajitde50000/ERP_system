"""Authenticated, expiring downloads for stored uploads (B6).

Every stored object is served from here — never from a public static mount.
Two access paths, mirroring how S3 works:

1. A **signed link** vended by an authenticated API response
   (``/api/v1/files/{key}?exp=…&sig=…``). The HMAC covers the key and the
   expiry, so links cannot be forged or reused forever; vended URLs only ever
   reach users who were allowed to see the owning row.
2. (s3 backend) the same route validates the signature and then **redirects**
   to a fresh, short-lived presigned object URL — downloads never proxy
   through the API, keeping workers stateless.

Responses are hardened for user-supplied content: ``nosniff`` everywhere, a
locked-down CSP (an SVG someone uploaded must not script the app's origin),
and ``Content-Disposition: attachment`` for anything non-media.
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse, RedirectResponse

from app.config import get_settings
from app.services.storage_service import normalize_key, storage

router = APIRouter(prefix="/files", tags=["Files"])

# Types safe to render inline in a browser tab. Everything else downloads.
_INLINE_MIME = {
    "application/pdf",
    "image/png", "image/apng", "image/jpeg", "image/gif", "image/webp",
    "image/svg+xml",
    "video/mp4", "video/webm", "video/ogg",
    "audio/mpeg", "audio/ogg", "audio/wav",
    "text/plain",
}

# Guess from the stored extension only to choose disposition headers — the
# authoritative type was fixed at upload time by magic-byte sniffing.
_EXT_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".webm": "video/webm", ".mp4": "video/mp4",
    ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".txt": "text/plain", ".csv": "text/plain",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _content_type(key: str) -> str:
    return _EXT_MIME.get(pathlib.Path(key).suffix.lower(), "application/octet-stream")


def _headers(key: str) -> dict[str, str]:
    ctype = _content_type(key)
    disposition = "inline" if ctype in _INLINE_MIME else "attachment"
    return {
        "Content-Type": ctype,
        "Content-Disposition": f'{disposition}; filename="{pathlib.Path(key).name}"',
        # Never let the browser reinterpret or execute stored content.
        "X-Content-Type-Options": "nosniff",
        # Uploaded SVGs/images must not run scripts or hit our origin.
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "Referrer-Policy": "no-referrer",
    }


@router.get("/{key:path}", response_class=Response)
@router.head("/{key:path}", response_class=Response)
async def download(
    key: str,
    exp: int = Query(..., description="Unix expiry embedded in the signed link"),
    sig: str = Query(..., description="HMAC(key|exp) signature from the signed link"),
) -> Response:
    key = normalize_key(key)
    storage.verify(key, exp, sig)  # 403 on expired/forged links

    if storage.backend == "s3":
        # Offload the bytes to object storage; workers stay stateless.
        return RedirectResponse(storage.presign(key), status_code=307)

    path = storage.open_local(key)  # 404 when unknown; traversal-safe
    return FileResponse(path, headers=_headers(key))
