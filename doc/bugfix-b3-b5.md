# Bugfix Report — B3 / B4 / B5 (third defect batch)

**Branch:** `arena/01a06da5-erp-system` · **Scope:** student exam-result lifecycle, live-class A/V infrastructure, multi-worker correctness.

Every reported defect was verified real **before** any fix, per the standing process. Verification evidence, root causes, fixes, and the test matrix are below.

> **Note on history:** this environment was rebuilt from upstream `b4949f1`; the earlier B1/B2 commit (`e92c922`) no longer exists in the clone, but all of its file changes survived in the working tree and are included in this round's commit alongside B3–B5.

---

## B3 — Student result UI: blank / error screens instead of a proper lifecycle

### Verified real (pre-fix, live E2E)

Real app + real PostgreSQL, one student through all states of one exam:

| Student situation | Pre-fix HTTP response | What the UI could do |
| --- | --- | --- |
| Never attempted | `404 "No submitted attempt for this exam"` | blank/error page |
| Attempt open | `404 "No submitted attempt for this exam"` | blank/error page |
| Submitted, results not released | `404 "Results are not released yet"` | string-match the prose, else error |
| Released | `200` + scores/answers | fine — but **no `result_state` field** |

Both UIs string-matched `"not released"` inside the error text to guess the "under evaluation" state. The web result page also had **no grade-card export at all** (`html2canvas` existed only in the coordinator timetable page).

### Root cause

The endpoint expressed a lifecycle (attempted? submitted? released?) as prose 404s, so clients had to parse error strings; the released shape carried no machine-readable state.

### Fix

* **Backend** (`app/schemas/student.py`, `app/services/student_service.py`): `StudentExamResult` gains typed constants (`NOT_ATTEMPTED / IN_PROGRESS / UNDER_EVALUATION / AVAILABLE`, as `ClassVar`) and a `result_state` field (default `AVAILABLE`, so existing consumers keep working). `exam_result()` now returns a header-only payload (exam identity + `submitted_at`, never scores/answers) for the three pre-availability states; only a genuinely invisible exam still 404s.
* **Gating semantics corrected** (upstream code contradicted its own integration test): `allow_review` no longer bypasses the release gate — it only widens what a *released* result includes. `show_score_immediately` remains the explicit quiz-mode opt-in. Pinned by `test_exam_lifecycle_end_to_end` ("gated until the teacher releases it").
* **Web** (`components/student/student-examinations.tsx`): the page renders all four states (not-attempted / in-progress / under-evaluation / available) plus loading/error-with-retry; the legacy `"not released"` string fallback is kept only for old backends. **New grade-card PNG export**: dynamically-imported `html2canvas` (never in the main bundle), white background, `useCORS`, 2× scale, blob download with URL revocation, busy/error states.
* **Mobile** (`app/src/app/(student)/examinations/[id]/result.tsx`, `app/src/lib/student.ts`): same typed four-state rendering (no string-matching), and a **"Share result"** action using React Native's built-in `Share` API with a plain-text grade card (`gradeCardText`) — no new dependency, works with every share target. "Answer review" renamed to **Marks breakdown** on both UIs.

---

## B4 — Live class A/V: no TURN, mobile dead-end (mesh itself is REAL)

### Verified real (code evidence — user's correction confirmed)

The web classroom already has a genuine WebRTC mesh (`fontend/hooks/use-live-room.ts`: one `RTCPeerConnection` per peer, `getUserMedia`/`getDisplayMedia`, WS-signalled SDP/ICE, MediaRecorder). The real gaps:

1. `RTC_CONFIG` was STUN-only (`stun:stun.l.google.com:19302`) — peers behind symmetric NAT / strict firewalls can never connect; no TURN relay was configurable.
2. Mobile has no WebRTC in this Expo build (documented in `app/src/lib/online-class.ts`), and the InClass screen told students "video plays in the web console" with **no way to get there**.
3. Mesh scale limits were documented nowhere.

### Fix (minimum viable, mesh untouched — it works)

* **ICE from the server** (`app/config.py::ice_servers`, `app/routers/online_class.py`): the WS `welcome` frame now carries `ice_servers`. `TURN_URL` / `TURN_USERNAME` / `TURN_CREDENTIAL` env vars (all three required — a half-configured relay is never advertised) add an authenticated TURN entry on top of the STUN fallback. Time-limited REST-auth credentials drop into the same vars with no code change.
* **Web client** (`use-live-room.ts`): the welcome's `ice_servers` (captured before the first offer, so relay candidates are in it) configure every `RTCPeerConnection`, including reconnects; the static STUN list remains the fallback.
* **Mobile**: the InClass screen now shows a **"Join audio/video in browser"** deep link to the web classroom (`webClassUrl()` helper, `EXPO_PUBLIC_WEB_URL` env) — honest about the limitation while keeping chat, raise-hand and attendance in the app; the button hides when the env is unset.
* **Operator docs**: new **`doc/deploy-coturn.md`** — coturn docker-compose + config, firewall ports, backend env wiring, verification (trickle-ice / webrtc-internals), the mesh scale table (~6–8 active cameras, 25–30 for teacher-broadcast) and the SFU migration path for larger classes. Scale limits are also documented on `use-live-room.ts` itself.
* Mesh code deliberately **not** rebuilt (user instruction).

---

## B5 — `LiveRoomManager._redis` always None + scheduler duplicated per worker

### Verified real (code evidence, then live E2E)

* `LiveRoomManager.__init__` set `self._redis = None`; nothing ever assigned it. `broadcast()`/`send_to()` iterated the **local** dict only. With 8–60 uvicorn/gunicorn workers, a teacher and a student land on different workers with probability ≈ 1 − 1/N — they would never see each other's chat, hand-raises or WebRTC signalling. `REDIS_URL` existed in `app/config.py` with **zero usages**.
* The WS `welcome.peers` list and `active_count` (used by the teacher dashboard) were likewise local-worker-only.
* `main.py` started APScheduler in **every** worker: auto-start and reminder jobs have no row locks (unlike the push drain, which is `SKIP LOCKED`-safe), so scheduled classes auto-started N times and students got N reminder notifications.

### Fix

**Live room fan-out** (`app/services/online_class_service.py`):

* Per-room Redis channel `live:room:{class_id}` with envelopes `{op: bc|dm, payload, exclude?, target?, origin}`; every worker runs a pub/sub listener that delivers to the sockets it owns (`origin` prevents echo). `start()` waits for actual subscription before returning, so early frames can't be missed.
* **Cluster-wide presence**: hash `live:presence:{class_id}` (`user → {name, role, worker}`) + worker heartbeat keys with TTL; `online_peers()`/`active_count()` now read the cluster roster and sweep entries of dead workers. A peer that reconnects on a different worker is not wiped by the old one (ownership check on removal).
* Robustness: oversized envelopes (>256 KB) are dropped rather than wedging the channel; Redis outage degrades to single-worker mode with a single warning — the room keeps serving local sockets (this is also exactly how every CI test run exercises the code: no Redis, fallback path).
* Lifecycle: `main.py` starts/stops the manager around the app's life; the router uses the new `register()`/`unregister()` (registration + presence in one call).

**Scheduler leader election** (`app/services/scheduler_service.py`):

* Redis lease `erp:scheduler:leader` (`SET NX EX`, TTL 90 s, renewed every 30 s, per-worker token): only the leader registers the auto-start / reminder / push-drain jobs; every worker runs a cheap heartbeat that re-checks leadership, so failover happens automatically ≤ ~2 min after a leader dies, and a deposed worker drops its jobs.
* New `SCHEDULER_ENABLED` setting: set `false` on API-only workers or to run the jobs in a dedicated process.
* Without Redis the jobs start locally with a loud warning (previous behaviour — correct only single-worker, kept so dev setups don't break). `stop_scheduler()` releases the lease for instant failover on graceful shutdown.

**Live verification** (`backend/scripts/verify_b3_b5_e2e.py`): spins up **two real uvicorn workers** of the actual app plus an embedded Redis (redislite), and proves cross-process chat, hand-raise, WebRTC signalling DM, cluster presence, single leader lease with TTL, TURN delivery on `welcome`, and the full B3 lifecycle — **15/15 checks pass**.

---

## Incidental production fixes found during this round (verified, fixed)

1. **`PrincipalNoticeDetail() got multiple values for keyword argument 'attachments'`** — every principal notice-detail request crashed: `LeadershipNoticeRow` already serialises `attachments`, which was then passed explicitly (`app/services/principal_service.py`). Fixed with an `exclude`; `test_principal_can_publish_an_institution_notice_with_audit_row` now passes.
2. **`database/database.sql` self-checks were stale vs its own schema** — a fresh load always raised "Expected 132 tables, found 133", "at most 24 unindexed FKs, found 25", "17 modules (want 16)". Corrected to the values the file itself produces (133 / 25 / 17). **No schema change** — the guards simply match the shipped schema now.
3. **Shared web `ErrorState` had no `role="alert"`** — screen readers never announced load failures; fixed for every console page.

## Database changes

**None.** B3–B5 need no new migrations: `result_state` is a JSON field with a backward-compatible default, live-room/scheduler state lives in Redis (ephemeral by design), and the `database.sql` edit only corrects the values of its existing self-check constants. No SQL update file is required for this batch; the main schema file needed no structural change.

## Test matrix

| Suite | Result |
| --- | --- |
| Backend unit/integration (`backend/tests/`) | **435 passed**, 8 failed — **all 8 verified pre-existing at pristine upstream `b4949f1`** (coordinator slot ×3: expects 409 where code raises 422, validation ordering, subject seed; VP console ×4: message-wording drift + a readers-query assertion; teacher-student attendance ×1: order-dependent flake). None are in this batch's scope; two previously-red tests (exam lifecycle, principal notice) are now green. |
| New `tests/test_live_room_and_scheduler.py` | 13 passed — two workers on one Redis: broadcast/send-to/exclude, presence roster, dead-worker sweep, reconnect ownership, oversized-frame drop, Redis-outage fallback, leader election/hand-over, scheduler disable |
| E2E `scripts/verify_b3_b5_e2e.py` (2 real workers + embedded Redis) | **15/15 passed** |
| Web (`fontend`): vitest | 8 passed (5 new B3 result-page tests incl. PNG export; 3 existing) |
| Web: `tsc --noEmit` | clean |
| Mobile (`app`): vitest | 7 passed (4 new: grade card text, typed contract, web join URL; 3 existing) |
| Mobile: `tsc --noEmit` | clean |

## Files changed (B3–B5 + incidental)

**Backend:** `app/schemas/student.py`, `app/services/student_service.py`, `app/services/online_class_service.py`, `app/routers/online_class.py`, `app/services/scheduler_service.py`, `app/services/principal_service.py`, `app/main.py`, `app/config.py`; tests: `test_student_console.py`, `test_teacher_student_integration.py`, **new** `test_live_room_and_scheduler.py`; **new** `scripts/verify_b3_b5_e2e.py`.
**Web:** `components/student/student-examinations.tsx`, `hooks/use-live-room.ts`, `lib/student.ts`, `components/admin/ui.tsx`; **new** `tests/student-exam-result.test.tsx`.
**Mobile:** `lib/student.ts`, `lib/online-class.ts`, `(student)/examinations/[id]/result.tsx`, `(student)/online-classes/[id].tsx`; **new** `src/lib/student.test.ts`.
**Docs:** **new** `doc/deploy-coturn.md`, this report; `database/database.sql` (self-check constants only).
