# Bugfix Report — B6 / B7 (fourth defect batch)

**Branch:** `arena/01a06da5-erp-system` · **Scope:** upload storage security, mobile release readiness.

Both defects were verified real end-to-end before any fix, per the standing process.

---

## B6 — Uploads: public static mount, string-MIME validation, local-disk only

### Verified real (pre-fix, live E2E — `/tmp` probe against the real app + PostgreSQL)

| Probe | Result before the fix |
| --- | --- |
| Teacher uploads `malicious.png` containing `<?php system(…); ?>` declaring `Content-Type: image/png` | **201 accepted** — validation trusted the client-declared string |
| `GET /uploads/online-classes/{id}/{file}` with **no authentication at all** | **200 + full file content** — the mount `app.mount("/uploads", StaticFiles(…))` was public, unlimited-lived, no tenant check |
| Same for notice attachments (`/uploads/notices/…`) | **200 + full content** |
| Multi-worker / container redeploy survival | Files on container-local disk; any redeploy or second instance loses/splits them (code-evident: writes went to `backend/uploads/…`) |

### Fix

**One storage service instead of three scattered write-paths** — `app/services/storage_service.py` is now the single place files are written, validated and served from; `OnlineClassService.add_file`/`delete_file`/`save_recording` and `PrincipalService._save_notice_attachments` (used by principal, coordinator and teacher notice flows) all delegate to it, and their duplicated path-building/unlink/size-cap code was removed.

1. **Private by default; short-lived signed URLs.** The public `/uploads` mount is gone (`main.py`). Files are served only by `GET /api/v1/files/{key}?exp=…&sig=…` (`app/routers/files.py`), where `sig = HMAC-SHA256(key|exp, JWT_SECRET_KEY)`:
   * links **expire** (default 15 min, `UPLOAD_SIGNED_URL_TTL_SECONDS`);
   * the signature is **key-bound** — swapping the key (e.g. another tenant's prefix) invalidates it;
   * URLs are only ever *vended* by authenticated API responses, so users only receive links for rows they are allowed to see. No auth header is needed on the download itself (browsers, `<img>` tags, RN `Linking` all work) — the same trust model as S3 presigned URLs.
   * Responses are hardened: `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox` (uploaded SVGs cannot script the app origin), `Content-Disposition: attachment` for non-media, `Referrer-Policy: no-referrer`.
2. **Magic-byte validation, not MIME strings** (`sniff_mime` + `validate_upload`): PNG/JPEG/GIF/PDF/WebP/WebM/MP4/OGG/MP3/WAV/OLE2/ZIP families verified by content signature; the declared type and the file extension must agree with the bytes (the webshell-as-PNG probe now returns **415**). `application/octet-stream` means "trust the sniff", never "skip it". Unrecognised binary is rejected.
3. **Per-tenant key prefixes.** Every new object is stored as `{tenant_id}/{namespace}/{uuid}_{name}` (e.g. `{tenant}/online-classes/{class}/…`, `{tenant}/notices/{notice}/…`) — isolation and per-tenant lifecycle/backup policies in one convention. Path traversal is refused by containment-checked resolution.
4. **Object storage for multi-instance/durable deployments.** `STORAGE_BACKEND=s3` (with `S3_BUCKET`, `S3_REGION`, optional `S3_ENDPOINT_URL` for MinIO/R2, credentials or IAM role, optional `S3_KEY_PREFIX`) writes to a **private** bucket, vends real S3 presigned URLs, and makes the files route a 307 redirect so workers stay stateless. `boto3` was added to `requirements.txt` and imports lazily — local-disk deployments don't pay for it. With the default `local` backend the disk root is simply no longer public.
5. **No forced data migration.** Legacy rows reference `/uploads/…` paths; `normalize_key` strips the prefix and those files remain servable through the same signed-URL flow, so existing links-in-DB keep working on day one (new writes are tenant-prefixed). `online_classes.recording_url` now persists the **stable key**, and serialization signs it per response — signed URLs are never persisted.

### Database changes

**None.** No new columns, tables or constraints: keys fit the existing `file_path` / `file_key` / `recording_url` text columns, and the "update SQL file + main schema" rule therefore doesn't trigger for this batch. (The storage *backend* optionally changes to S3, which carries no schema either.)

### Tests

* `backend/tests/test_storage_service.py` — 29 tests: signature table, webshell rejection (declared *and* octet-stream), declared/extension/content agreement, OOXML-on-ZIP and OLE2 family handling, tenant-prefixed writes, size-cap cleanup (nothing half-written), streaming `UploadFile` round-trip, traversal refusal, signed-URL round trip, tamper/expiry/key-binding, singleton sanity.
* `backend/scripts/verify_b6_e2e.py` — **17/17 live checks**: webshell 415 (both declared PNG and octet-stream), genuine upload → signed tenant-prefixed URL, anonymous fetch 200 with nosniff+CSP, tampered sig 403, cross-tenant key swap 403, expired link 403, old `/uploads/…` 404, recording signed at read time, student upload validated, notice attachment signed, delete removes the object.
* Full backend suite: **464 passed**, 8 failed — the identical pre-existing upstream failures documented in `doc/bugfix-b3-b5.md` (coordinator slots ×3, VP console ×4, attendance flake). No regressions.

---

## B7 — Mobile app could not reach a real backend

### Verified real (code + config evidence)

* `src/lib/auth.ts`: `process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000"` — on a physical phone that is **the phone itself**; a store build without the env var ships dead, silently.
* No `eas.json` (no build profiles at all), no `.env.production`, `.env.example` pointed at localhost only.
* No `android.package` / `ios.bundleIdentifier` in `app.json` → store builds are impossible without edits.
* No cleartext/network-security policy: release Android builds default `usesCleartextTraffic=false`, so even a deliberate `http://` staging URL would fail with no diagnostics.
* No store-release documentation or store assets beyond the app icons.

### Fix

1. **Fail-fast release guard** (`src/lib/auth.ts::resolveApiBaseUrl`, exported and unit-tested): a `NODE_ENV=production` bundle **without** `EXPO_PUBLIC_API_URL`, or pointed at `localhost/127.0.0.1/10.0.2.2`, throws at startup with an actionable message instead of shipping a broken app. Development builds keep the localhost default (correct for emulators/Expo Go).
2. **`eas.json` build profiles**: `development` (dev client, localhost), `preview` (internal distribution, env-injected API), `production` (channel, `autoIncrement`, `appVersionSource: remote`, `EXPO_PUBLIC_API_URL`/`EXPO_PUBLIC_WEB_URL` injected from **EAS secrets** — never committed).
3. **Store-ready `app.json`**: `android.package`/`ios.bundleIdentifier` (`com.erpcampus.mobile`, documented as *replace with the institution's ID before first submission* — permanent once published), `versionCode`/`buildNumber`, and the `expo-build-properties` plugin locking release builds to HTTPS-only (`usesCleartextTraffic: false`, ATS `NSAllowsArbitraryLoads: false`). Dev builds keep OS defaults so local servers still work. (`expo-build-properties` added to dependencies.)
4. **Store assets**: `assets/store/feature-graphic.png` (1024×500) and `assets/store/icon-512.png`, generated deterministically from the app's brand colours (snippet below) rather than committing opaque binaries; the full icon/adaptive/splash set already existed and is complete.
5. **`app/README.md`** (new): env matrix (dev vs release), the complete EAS pipeline (`eas init` → `secret:create` → `build` → `submit`), and a store-submission checklist (identifiers, screenshots, listing limits, mandatory privacy policy citing FCM, HTTPS backend requirement).
6. `.env.example` rewritten: emulator vs LAN-IP vs HTTPS guidance, `EXPO_PUBLIC_WEB_URL` documented.

### Regenerating the store assets

```bash
python3 - <<'EOF'
from PIL import Image, ImageDraw, ImageFont
SLATE, ACCENT, WHITE = (15,23,42), (37,99,235), (255,255,255)
BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"; REG="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
fg=Image.new("RGB",(1024,500)); d=ImageDraw.Draw(fg)
for y in range(500):
    t=y/499; c=tuple(int(SLATE[i]+(ACCENT[i]-SLATE[i])*(t*.85)) for i in range(3)); d.line([(0,y),(1024,y)],fill=c)
d.text((64,150),"ERP Campus",font=ImageFont.truetype(BOLD,84),fill=WHITE)
d.text((68,262),"School  •  College  •  Institute management",font=ImageFont.truetype(REG,34),fill=(226,232,240))
d.rounded_rectangle((64,340,560,352),radius=6,fill=ACCENT); fg.save("assets/store/feature-graphic.png")
Image.open("assets/images/icon.png").convert("RGBA").resize((512,512),Image.LANCZOS).save("assets/store/icon-512.png")
EOF
```

### Tests

* `app/src/lib/auth.test.ts` — 5 new tests: dev localhost default, LAN URL + slash-stripping, release-without-env throws, release-with-localhost throws (all three host spellings), release HTTPS accepted.
* Mobile suite: **12 passed** (3 files), `tsc --noEmit` clean. Web suite re-run after the storage change: **8 passed**, `tsc` clean (signed URLs flow through the existing `fileHref`/`attachmentUrl` helpers unchanged).

---

## Files changed

**Backend:** new `app/services/storage_service.py`, new `app/routers/files.py`; `app/main.py` (mount removed, router added), `app/config.py` (storage settings), `app/services/online_class_service.py`, `app/services/principal_service.py`, `app/services/coordinator_service.py`, `app/services/teacher_service.py`, `app/routers/online_class.py` (storage plumbing, legacy params removed), `routers/__init__.py`; `requirements.txt` (+boto3); new `tests/test_storage_service.py`, new `scripts/verify_b6_e2e.py`.
**Mobile:** `src/lib/auth.ts` (release guard), new `src/lib/auth.test.ts`; new `eas.json`; `app.json` (identifiers, build properties, versions); `.env.example`; new `assets/store/*`, new `README.md`; `package.json` (+expo-build-properties).
**Root:** `.gitignore` (`backend/uploads/` runtime data never committed).
**Docs:** this report.
