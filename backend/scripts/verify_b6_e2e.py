"""B6 post-fix E2E: private, validated, expiring file storage.

Runs the real app (ASGI, real database) and proves the three pre-fix leaks
are closed:

  before: webshell claiming image/png → 201; stored URL readable by anyone,
          forever, via the public /uploads mount.

  after:  content mismatch → 415; URLs are tenant-prefixed keys behind
          /api/v1/files/{key}?exp=…&sig=…; links expire; the public mount is
          gone; notice attachments and class recordings use the same scheme.

Run:
  DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST/DBNAME" \
  JWT_SECRET_KEY=dev-secret PYTHONPATH=backend \
  .venv/bin/python scripts/verify_b6_e2e.py
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("EMAIL_PROVIDER", "console")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from scripts.verify_b1_b2_e2e import login, seed  # noqa: E402
from app.services.storage_service import storage  # noqa: E402

API = "/api/v1"
RESULTS: dict[str, bool] = {}

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(24))
EVIL = b"<?php system($_GET['cmd']); ?>" + b"\x00" * 8


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS[name] = ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))


def url_parts(url: str) -> tuple[str, int, str]:
    parsed = urlparse(url)
    key = parsed.path.split("/api/v1/files/", 1)[1]
    qs = parse_qs(parsed.query)
    return key, int(qs["exp"][0]), qs["sig"][0]


async def main() -> int:
    async with AsyncSessionLocal() as db:
        ids = await seed(db)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=20) as client:
        teacher = await login(client, ids.slug, ids.teacher_email, ids.teacher_pw)
        student = await login(client, ids.slug, ids.student_email, ids.student_pw)

        instant = await client.post(f"{API}/online-classes/instant", headers=teacher, json={
            "class_id": str(ids.class_id), "subject_id": str(ids.subject_id),
            "topic": "B6 post-fix storage", "duration_minutes": 30,
        })
        assert instant.status_code == 201, instant.text
        class_id = instant.json()["data"]["id"]

        print("\n== content validation ==")
        r = await client.post(f"{API}/online-classes/{class_id}/files", headers=teacher,
                              files={"file": ("malicious.png", EVIL, "image/png")})
        check("webshell claiming image/png rejected (415)", r.status_code == 415, r.text[:160])

        r = await client.post(f"{API}/online-classes/{class_id}/files", headers=teacher,
                              files={"file": ("malicious.png", EVIL, "application/octet-stream")})
        check("webshell with octet-stream also rejected", r.status_code == 415, r.text[:160])

        r = await client.post(f"{API}/online-classes/{class_id}/files", headers=teacher,
                              files={"file": ("notes.png", PNG, "image/png")})
        check("genuine PNG accepted", r.status_code == 201, r.text[:200])
        url = r.json()["data"]["url"]
        check("URL is a signed /api/v1/files link", url.startswith("/api/v1/files/") and "sig=" in url and "exp=" in url, url)

        png_file_id = r.json()["data"]["id"]
        key, exp, sig = url_parts(url)
        tenant_prefix = key.split("/")[0]
        check("key is tenant-prefixed", re.fullmatch(r"[0-9a-f-]{36}", tenant_prefix) is not None, key)

        print("\n== access control ==")
        anon = await client.get(url)  # NO Authorization header at all
        check("anonymous fetch via signed link works (no auth header needed)", anon.status_code == 200 and anon.content == PNG, str(anon.status_code))
        check("nosniff + CSP hardening present",
              anon.headers.get("x-content-type-options") == "nosniff" and "sandbox" in anon.headers.get("content-security-policy", ""),
              str(dict(anon.headers)))

        tampered = url.replace(sig, "f" * 64)
        check("tampered signature → 403", (await client.get(tampered)).status_code == 403)

        other_key = f"00000000-0000-0000-0000-000000000000/{key.split('/', 1)[1]}"
        check("signature is key-bound (cross-tenant swap → 403)",
              (await client.get(f"/api/v1/files/{other_key}?exp={exp}&sig={sig}")).status_code == 403)

        expired_exp = int(time.time()) - 10
        expired_sig = storage._sign(key, expired_exp)
        check("expired link → 403",
              (await client.get(f"/api/v1/files/{key}?exp={expired_exp}&sig={expired_sig}")).status_code == 403)

        check("old public /uploads mount is gone (404)",
              (await client.get(f"/uploads/online-classes/{class_id}/{key.split('/')[-1]}")).status_code == 404)

        print("\n== recordings & student uploads ==")
        webm = b"\x1a\x45\xdf\xa3" + bytes(range(32))
        r = await client.post(f"{API}/online-classes/{class_id}/recording", headers=teacher,
                              files={"file": ("lesson.webm", webm, "video/webm")})
        if r.status_code == 404:  # route name may differ; try the files route with recording role
            check("recording upload endpoint reachable", False, r.text[:120])
        else:
            detail = r.json().get("data", {})
            rec_url = detail.get("recording_url", "")
            check("recording URL is signed at read time", rec_url.startswith("/api/v1/files/"), rec_url[:80])
            anon_rec = await client.get(rec_url)
            check("recording fetches anonymously via signature", anon_rec.status_code == 200 and anon_rec.content == webm)

        await client.post(f"{API}/online-classes/{class_id}/join", headers=student)
        r = await client.post(f"{API}/online-classes/{class_id}/files/student", headers=student,
                              files={"file": ("answer.txt", b"my homework", "text/plain")})
        check("student upload validated + signed", r.status_code == 201 and r.json()["data"]["url"].startswith("/api/v1/files/"), r.text[:160])

        print("\n== notice attachments ==")
        from sqlalchemy import select
        from app.models.principal import Notice
        from app.models.user import User
        from app.services.principal_service import PrincipalService
        async with AsyncSessionLocal() as db:
            author = (await db.execute(select(User).where(User.email == ids.teacher_email))).scalar_one()
            notice_id = __import__("uuid").uuid4()
            db.add(Notice(
                id=notice_id, tenant_id=ids.tenant_id, author_id=author.id,
                title="B6 post-fix notice", body="attachment check",
                target_scope="INSTITUTION", priority="NORMAL", is_pinned=False,
                published_at=datetime.now(timezone.utc),
            ))
            await db.flush()
            item = SimpleNamespace(
                external_url=None, mime_type="image/png", file_name="proof.png",
                data_url="data:image/png;base64," + base64.b64encode(PNG).decode(),
            )
            saved = await PrincipalService._save_notice_attachments(db, ids.tenant_id, notice_id, [item])
            await db.commit()
            att_url = saved[0].url
        check("notice attachment stored under tenant-prefixed key", att_url.startswith("/api/v1/files/"), att_url[:90])
        anon_att = await client.get(att_url)
        check("notice attachment fetchable via signature only", anon_att.status_code == 200 and anon_att.content == PNG)

        print("\n== deletion ==")
        # The teacher's PNG from the upload step: delete it and prove the
        # previously-signed link stops resolving.
        deleted = await client.delete(f"{API}/online-classes/{class_id}/files/{png_file_id}", headers=teacher)
        check("delete removes the stored object",
              deleted.status_code == 200 and (await client.get(url)).status_code == 404,
              deleted.text[:160])

    ok = all(RESULTS.values())
    print(f"\n{'ALL B6 CHECKS PASSED' if ok else 'B6 FAILURES PRESENT'} ({sum(RESULTS.values())}/{len(RESULTS)})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
