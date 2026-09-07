# Functional-Defect Verification — PRE-LAUNCH-ISSUES-AND-FIXES.md §B

**Scope:** every item in section **“B. P1 — Functional defects (the bugs your team already reported + more)”** of `PRE-LAUNCH-ISSUES-AND-FIXES.md` (B1–B7), re-verified **solved properly** on branch `arena/01a06da5-erp-system` at HEAD. Sections A (security/credentials), C (operations) and D (ad-readiness) are separate work streams and are out of scope for this check.

**Verification date:** 2026-09-05 · **Commits carrying the fixes:** `e92c922` (B1–B2), `125a342` (B3–B5), `eb85f82` (B6–B7), plus this round's hardening commit.

---

## Verdict matrix

| # | Defect (as written in the file) | Status | Verified by (all re-run today on HEAD) |
| --- | --- | --- | --- |
| B1 | Assignment close → reopen → resubmission: un-reviewed submissions never returned to students | **SOLVED** | E2E `scripts/verify_b1_b2_e2e.py` — reopen marks un-reviewed work `RESUBMIT_REQUESTED` (default), assignment reappears in the student's pending list, resubmit **201**; reopen without nudge keeps `SUBMITTED`; unit `tests/test_assignment_reopen_and_grading.py`; web `tests/assignment-reopen-resubmit.test.tsx`; mobile `src/lib/teacher.test.ts` |
| B2 | Teacher question review shows “only squares”: no option list / correct key / MATCH pairs | **SOLVED** | E2E above (options in payload); unit test `test_attempt_detail_returns_the_full_answer_key_and_match_pairs` (MCQ + MATCH structured types); web `tests/teacher-exam-grading.test.tsx` (full option list, `CORRECT`/`STUDENT'S PICK` text badges — no symbol glyphs — MATCH pair list); mobile grading screen mirrors it |
| B3 | Student result UI: undefined states, blank/error instead of “under evaluation”, no grade-card export | **SOLVED** | E2E `scripts/verify_b3_b5_e2e.py` — typed `NOT_ATTEMPTED / IN_PROGRESS / UNDER_EVALUATION / AVAILABLE` lifecycle over HTTP with no score leak pre-availability, `show_score_immediately` quiz mode honoured; web `tests/student-exam-result.test.tsx` (5 states incl. legacy-404 fallback + PNG export click-through); mobile `src/lib/student.test.ts` (typed contract + grade-card text) |
| B4 | Live A/V: no TURN, no SFU path, cross-worker signalling, no mobile A/V | **SOLVED (minimum + documented path)** | E2E — WS `welcome` carries STUN + authenticated TURN from `TURN_*` env (verified live with env set); web hook uses server ICE for every peer connection; mobile “Join audio/video in browser” deep link (`EXPO_PUBLIC_WEB_URL`, tested); `doc/deploy-coturn.md` documents coturn deployment, mesh ceilings (~6–8 cameras) and the SFU migration path incl. server-side recording. SFU itself and RN-native WebRTC are **deliberately documented deferrals**, per the fix line “(or a documented ‘join A/V in browser’)” |
| B5 | `LiveRoomManager._redis` always None → same-worker-only broadcasts; scheduler duplicated per worker | **SOLVED** | E2E — **two real uvicorn workers + real Redis**: chat, hand-raise, WebRTC signalling DM and presence all cross processes; exactly one scheduler leader lease with TTL; unit `tests/test_live_room_and_scheduler.py` (13 tests: fan-out, presence sweep, outage fallback, leader election/hand-over) |
| B6 | Uploads: public `/uploads` mount, string-MIME validation, local disk only | **SOLVED** | Pre-fix live probe: webshell-as-PNG **201**, anonymous fetch **200**. Post-fix E2E `scripts/verify_b6_e2e.py` — **17/17**: webshell **415** (declared *and* octet-stream), tenant-prefixed keys, HMAC-signed expiring links, tamper/cross-tenant/expiry → **403**, public mount **404**, recording + student upload + notice attachments signed, delete removes object; unit `tests/test_storage_service.py` (29 tests); optional S3 backend (`STORAGE_BACKEND=s3`) for multi-instance durability |
| B7 | Mobile cannot reach a real backend (localhost default, no profiles/identifiers/cleartext policy/store assets) | **SOLVED** | `src/lib/auth.test.ts` — release build without a real HTTPS `EXPO_PUBLIC_API_URL` **fails fast** (and refuses localhost/127.0.0.1/10.0.2.2); `eas.json` dev/preview/production profiles; `app.json` package/bundle ids + versions + `expo-build-properties` HTTPS-only; `assets/store/*` generated; `app/README.md` release + store-submission guide |

## Full-suite results on HEAD (this round)

| Suite | Result |
| --- | --- |
| Backend `pytest tests/` | **472 passed, 0 failed** — first fully green run (was 420 passed / 10 pre-existing reds when this branch started) |
| E2E B1/B2 | all checks passed |
| E2E B3–B5 (2 real workers + embedded Redis) | **16/16** |
| E2E B6 | **17/17** |
| Web vitest / tsc | **8 passed** / clean |
| Mobile vitest / tsc | **12 passed** / clean |

---

## Fixed during this verification round (the “+ more”)

While proving the section-B matrix, the four remaining pre-existing suite failures — none of them B-items, all documented as upstream drift in earlier reports — were root-caused and closed:

1. **VP/principal notice detail crashed in production (`TypeError: got multiple values for keyword argument 'attachments'`)** — the create-path occurrence of this bug was fixed in `eb85f82`'s predecessor round, but the **notice-detail read path** (`PrincipalService.notice_detail`) had a second, unfixed construction. Every GET of a notice detail (principal *and* VP consoles) returned 500. Caught by `test_vp_notice_detail_never_queries_or_serializes_readers`; both construction sites now exclude the base schema's default.
2. **Coordinator slot tests pinned a pre-validation query order** — `create_slot`/`update_slot` gained CLASS-slot subject+teacher validation, teaching-assignment checks and teacher/room double-booking guards after the tests were written. The three stale tests were rewritten against the current contract (valid fully-specified CLASS slots, correct ordered lookups); product code unchanged.
3. **VP role-scope error messages** — code said “**An VICE_PRINCIPAL** must be assigned a department” (ungrammatical) while the suite's contract requires the wording to name the **delegated department**. Messages corrected in `institution_service.py` (3 sites).
4. **Test-state leak froze “today” process-wide** — `test_online_class_production.py` assigned `PrincipalService._tenant_today = AsyncMock(...)` **without monkeypatch**, so it never reverted; every later test saw “today” = 2026-08-27 and the attendance integration test failed with “future date” in full-suite runs only (passed in isolation). Converted to `monkeypatch.setattr`.

Item 1 was a genuine user-facing production crash; items 2–4 were test-suite defects that masked real signal (a 500-throwing endpoint hidden behind a stale test).

## Deliberate deferrals (documented, not silently dropped)

* **B4 SFU** — mesh stays for class-sized rooms (documented ceiling table); SFU migration path (LiveKit/mediasoup) is written up in `doc/deploy-coturn.md` §5, including server-side recording replacing teacher-browser capture. This matches the file's own fix wording (“for classes beyond ~6–8 participants use an SFU”).
* **B4 RN-native WebRTC** — the file explicitly allows “a React Native WebRTC path **(or a documented ‘join A/V in browser’)**”; the documented browser-join deep link is implemented and tested.
* **B6 antivirus** — the file's fix line asks for magic-byte validation (done). Full ClamAV-style scanning is an ops item (section C territory); the storage service's single choke-point is where such a hook would land.

## Database changes

None in this round (and none were required for B1–B7: all fixes fit existing columns/contracts — see each round's report).
