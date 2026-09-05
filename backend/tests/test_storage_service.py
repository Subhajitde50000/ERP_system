"""B6 regression tests: private storage, magic-byte validation, signed URLs.

The pre-fix evidence (live E2E): a file claiming ``image/png`` while
containing PHP webshell bytes was accepted (201), and the stored URL was
readable by anyone, forever, through the public ``/uploads`` static mount.
These tests pin the storage contract that closes both holes.
"""

from __future__ import annotations

import io
import time
import uuid

import pytest
from fastapi import HTTPException

from app.services.storage_service import (
    Storage,
    normalize_key,
    safe_filename,
    sniff_mime,
    storage,
    validate_upload,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 24
PDF = b"%PDF-1.7\n%" + b" " * 24
ZIP = b"PK\x03\x04" + b"\x00" * 24
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 24
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 24
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 16
WEBSHELL = b"<?php system($_GET['cmd']); ?>"


# ── Magic-byte sniffing ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (PNG, "image/png"),
        (JPG, "image/jpeg"),
        (PDF, "application/pdf"),
        (ZIP, "application/zip"),
        (OLE2, "application/x-cfb"),
        (WEBM, "video/webm"),
        (MP4, "video/mp4"),
        (b"GIF89a" + b"\x00" * 10, "image/gif"),
        (b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 8, "image/webp"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 8, "audio/wav"),
        (b"OggS" + b"\x00" * 20, "audio/ogg"),
        (b"ID3\x04\x00" + b"\x00" * 26, "audio/mpeg"),
        (b"<svg xmlns=\"http://www.w3.org/2000/svg\">" + b" " * 10, "image/svg+xml"),
        (b"hello, plain text file", "text/plain"),
    ],
)
def test_sniff_recognises_signatures(head, expected):
    assert sniff_mime(head) == expected


def test_sniff_rejects_unknown_binary():
    assert sniff_mime(WEBSHELL + b"\x00\xff\xfe garbage") is None
    assert sniff_mime(b"") is None


# ── Upload validation: the webshell scenario ─────────────────────────────────


def test_webshell_claiming_png_is_rejected():
    with pytest.raises(HTTPException) as raised:
        validate_upload("image/png", "malicious.png", WEBSHELL + b"\x00" * 8)
    assert raised.value.status_code == 415


def test_declared_type_must_match_content():
    with pytest.raises(HTTPException):
        validate_upload("image/png", "photo.png", PDF)
    # octet-stream means "trust the sniff" — content is still validated
    assert validate_upload("application/octet-stream", "photo.png", PNG) == "image/png"


def test_extension_must_match_content():
    with pytest.raises(HTTPException) as raised:
        validate_upload("application/pdf", "archive.pdf", ZIP)  # zip is not pdf
    assert raised.value.status_code == 415
    # …but the OOXML family is allowed to ride the zip container
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert validate_upload(docx, "doc.docx", ZIP) == docx
    assert validate_upload("application/msword", "old.doc", OLE2) == "application/msword"


def test_unrecognised_content_rejected():
    with pytest.raises(HTTPException):
        validate_upload("application/octet-stream", "blob.bin", b"\xde\xad\xbe\xef" * 8)


# ── Keys, names, legacy paths ─────────────────────────────────────────────────


def test_normalize_key_strips_legacy_prefixes():
    assert normalize_key("/uploads/online-classes/x/y.png") == "online-classes/x/y.png"
    assert normalize_key("uploads/notices/a/b.pdf") == "notices/a/b.pdf"
    assert normalize_key("t/ns/f.png") == "t/ns/f.png"


def test_safe_filename_neutralises_paths():
    # slashes disappear entirely; dot-dots without slashes cannot traverse
    assert "/" not in safe_filename("../../etc/passwd")
    assert safe_filename("") == "file"


# ── Local backend: tenant-prefixed writes and reads ───────────────────────────


async def test_save_writes_under_tenant_prefix(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_FILE_ROOT", str(tmp_path / "u"))
    s = Storage()
    tenant = uuid.uuid4()
    stored = await s.save(tenant, "online-classes/x", "notes.png", PNG, "image/png", max_bytes=1024)
    assert stored.key.startswith(f"{tenant}/online-classes/x/")
    assert stored.mime == "image/png"
    assert stored.size == len(PNG)
    assert (tmp_path / "u" / str(tenant) / "online-classes" / "x").is_dir()


async def test_save_enforces_size_cap(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_FILE_ROOT", str(tmp_path / "u"))
    s = Storage()
    with pytest.raises(HTTPException) as raised:
        await s.save(uuid.uuid4(), "ns", "big.png", PNG, "image/png", max_bytes=4)
    assert raised.value.status_code == 413
    # nothing half-written may remain
    assert not list((tmp_path / "u").rglob("*.png"))


async def test_save_streams_upload_file_objects(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_FILE_ROOT", str(tmp_path / "u"))
    s = Storage()

    class FakeFile(io.BytesIO):
        async def read(self, n=-1):  # noqa: A003 - mimics UploadFile.read
            return super().read(n)

        async def seek(self, pos, whence=0):  # noqa: A003 - mimics UploadFile.seek
            return super().seek(pos, whence)

    upload = FakeFile(PNG)
    stored = await s.save(uuid.uuid4(), "ns", "x.png", upload, "image/png", max_bytes=1024)
    assert stored.size == len(PNG)
    assert s.open_local(stored.key).read_bytes() == PNG


def test_open_local_refuses_traversal(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_FILE_ROOT", str(tmp_path / "u"))
    s = Storage()
    (tmp_path / "u" / "t" / "ns").mkdir(parents=True)
    (tmp_path / "secret.txt").write_text("outside")
    with pytest.raises(HTTPException) as raised:
        s.open_local("t/../../secret.txt")
    assert raised.value.status_code == 404


# ── Signed URLs (local HMAC scheme) ───────────────────────────────────────────


async def test_signed_url_round_trip(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_FILE_ROOT", str(tmp_path / "u"))
    s = Storage()
    stored = await s.save(uuid.uuid4(), "ns", "a.png", PNG, "image/png", max_bytes=1024)

    url = s.signed_url(stored.key)
    assert url.startswith("/api/v1/files/")
    assert "exp=" in url and "sig=" in url
    key_part = url.split("/api/v1/files/")[1].split("?")[0]
    exp = int(url.split("exp=")[1].split("&")[0])
    sig = url.split("sig=")[1]
    s.verify(key_part, exp, sig)  # no exception


def test_signature_tamper_and_expiry(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_FILE_ROOT", str(tmp_path / "u"))
    s = Storage()
    with pytest.raises(HTTPException) as raised:
        s.verify("t/ns/x.png", int(time.time()) + 60, "deadbeef")
    assert raised.value.status_code == 403

    with pytest.raises(HTTPException) as raised:
        s.verify("t/ns/x.png", int(time.time()) - 1, s._sign("t/ns/x.png", int(time.time()) - 1))
    assert raised.value.status_code == 403


def test_signature_is_key_bound(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_FILE_ROOT", str(tmp_path / "u"))
    s = Storage()
    exp = int(time.time()) + 60
    sig = s._sign("tenant-a/ns/x.png", exp)
    with pytest.raises(HTTPException):
        # swapping the key (another tenant's file) invalidates the signature
        s.verify("tenant-b/ns/x.png", exp, sig)


# ── Module singleton ──────────────────────────────────────────────────────────


def test_shared_singleton_uses_local_root():
    assert storage.backend in ("local", "s3")
    assert (storage.root.name if storage.backend == "local" else "uploads") == "uploads"
