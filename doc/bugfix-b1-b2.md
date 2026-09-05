# Bug Fix Report — B1 (close → reopen → resubmit) & B2 (question review context)

**Date:** 2026-09-05 · **Scope:** Teacher/Student assignment workflow + exam grading view ·
**Branch:** `arena/01a06da5-erp-system`

---

## 1. What was reported vs. what was actually broken

Both reports were re-verified **end-to-end on a running system** (real PostgreSQL 16 with the
canonical `database/database.sql` schema + the repo's migration files, real FastAPI app over the
ASGI transport — no DB mocks) before a single line was changed.

### B1 — Assignment close → reopen → resubmission

The report's own re-verification was **confirmed**: the resubmission feature *is* fully built —
teacher reopen endpoint (`POST /teacher/assignments/{id}/reopen`), review decision
`CHANGES_REQUESTED → SubmissionStatus.RESUBMIT_REQUESTED`, versioned student resubmission, and
the web/mobile resubmit UI all exist and work.

The **real, narrower gap** was also confirmed exactly as described:

| Step | Observed behaviour (before the fix) |
|---|---|
| Teacher reopens a closed assignment | `transition_assignment` only flipped the assignment `CLOSED → PUBLISHED` |
| Student's already-submitted (un-reviewed) work | Stayed `SUBMITTED` / `UNDER_REVIEW` |
| Student dashboard "pending" list | `_pending_assignments` excludes anything with a `SUBMITTED`/`UNDER_REVIEW`/`APPROVED` submission → the reopened assignment **never came back as actionable** |
| Result | Student who submitted but was never graded could not see the assignment again; "Resubmit" only appeared if a reviewer explicitly requested changes |

### B2 — Teacher question review shows "only squares"

Confirmed the question types are exactly `MCQ, TRUE_FALSE, SHORT_ANSWER, LONG_ANSWER, FILL_BLANK,
MATCH` (there is no IMAGE question type). Confirmed the manual grading panel rendered only
*question text + one line of student answer* — **no option list, no correct-answer key for the
descriptive items that had options authored, no MATCH pairings**. `selected_option_text` was
populated for MCQ/TRUE_FALSE, but the reviewer had no way to see the full key, so objective
questions collapsed into an unreadable summary ("squares") and MATCH answers showed nothing at
all (their data lives in `answers.matched_pairs`, which the payload never included).

### Found during verification — a blocking defect nobody had reported

The very first E2E run **crashed** creating an assignment:

```
DatatypeMismatchError: column "type" is of type assignment_type but expression is of type character varying
```

The ORM mapped **9 columns as `String` that the canonical schema declares as PostgreSQL enums**
(or `inet`): `assignments.type`, `exams.exam_type`, `exams.mode`, `subjects.subject_type`,
`student_enrollments.status`, `leave_requests.status`, `timetable_slots.slot_type`,
`staff_profiles.employment_type`, `scholarships.type`, plus `exam_attempts.ip_address` (`inet`).
Every write through those models fails against the real database (the console test-suite passes
only because it mocks the DB). This was fixed as a prerequisite — see §4.

---

## 2. How the fixes work (what / why / how)

### B1 — reopen now hands un-reviewed work back to students

**Design decision (matching the report's option b with a):** reopening asks the teacher what to
do with un-reviewed work, and *by default* marks it `RESUBMIT_REQUESTED`. This reuses the
existing, already-tested student plumbing end-to-end: `RESUBMIT_REQUESTED` rows are **excluded**
from the "already done" set in `_pending_assignments`, so the assignment re-appears in the
student's pending list, the row shows *Resubmit Requested*, and the **Resubmit** entry point is
available — no new status, no new table, no duplicated workflow.

| Reopen mode | Un-reviewed submissions (latest version per student & milestone) | Approved / Rejected work | Students who never submitted |
|---|---|---|---|
| `request_resubmission: true` **(default)** | → `RESUBMIT_REQUESTED` + in-app nudge ("Assignment reopened… you may resubmit") | never touched | can now submit |
| `request_resubmission: false` | stay `SUBMITTED` / `UNDER_REVIEW` (teacher can still review normally) | never touched | can now submit |

Rules that make this safe:

- Only the **latest version per (student, milestone) scope** is moved — the same scope
  `submit_assignment` gates on; older versions and already-reviewed decisions are never altered.
- One `UPDATE … WHERE id IN (DISTINCT ON (student_id, milestone_id) … ORDER BY version DESC)`
  statement — a single round-trip regardless of class size, inside the request's transaction
  (rollback on failure), `synchronize_session=False` to avoid row-by-row ORM sync.
- `DISTINCT ON` treats `NULL` milestone ids as equal ("not distinct"), correctly grouping
  assignment-level submissions.
- Fully audited (`REOPEN_ASSIGNMENT` row now records `resubmission_requested: <count>`) and the
  student nudge is best-effort (a notification failure can never fail the reopen).
- Teachers keep the lighter option via an **optional** request body — `POST …/reopen` with no
  body behaves exactly as before plus the resubmission hand-back.

**Files (backend):**
- `app/services/teacher_service.py` — `transition_assignment` gained the keyword-only
  `request_resubmission` flag, the bulk reopen statement, audit enrichment and the nudge.
- `app/routers/teacher.py` — reopen endpoint accepts `TeacherAssignmentReopen | None` body.
- `app/schemas/teacher.py` — new `TeacherAssignmentReopen` schema.

**Files (web):** `lib/teacher.ts` (`reopenTeacherAssignment(id, requestResubmission = true)`) and
`components/teacher/teacher-assignments.tsx` — the *Reopen assignment* button now opens a small
choice dialog ("Reopen & ask students to resubmit" / "Reopen for new submissions only" /
Cancel) instead of firing a blind reopen.

**Files (mobile):** `src/lib/teacher.ts` (same signature) and the teacher assignment detail
screen — the same choice via native `Alert.alert` with three buttons.

### B2 — the grading view now renders the full answer key

**Backend** (`attempt_detail`): the option query now fetches **every option of every question**
(previously only the student's pick + correct options), ordered by `(question_id, sort_order)`,
and each answer row carries:

- `options: [{id, text, is_correct, sort_order}]` — the complete key,
- `matched_pairs` — pass-through of the MATCH answer's JSONB pairings (previously dropped).

The response is slightly larger on purpose (all options instead of 1–2) — bounded by the exam's
question set, one extra `ORDER BY`, no extra round-trips.

**Web** (`components/teacher/teacher-exam-results.tsx`):
- Manual cards show the student's answer with the right presentation per type: written text,
  "Student picked: X" for option picks, a two-column pair list for MATCH, and an explicit
  "(no answer written)" state.
- Every card (manual *and* auto-graded) renders the **full option list** with plain-text badges
  `CORRECT` and `STUDENT'S PICK` — no symbol glyphs (✓/✗/□), which is what made the old view
  read as "squares" in some fonts/encodings. Unicode in question/answer text is passed through
  untouched (JSX escapes it safely).
- The auto-graded summary lists each objective question with a verdict badge
  (`CORRECT` / `WRONG` / `NOT ANSWERED · score/marks`) plus the key.

**Mobile** (`app/src/app/(teacher)/examinations/[id]/attempts/[attemptId].tsx`): the same
treatment — per-option rows with `CORRECT` / `STUDENT'S PICK` badges, verdict line per
auto-graded question, MATCH pairs rendered as `left → right` lines, explicit "(no answer
written)" state.

### Prerequisite fix — ORM ↔ canonical schema type alignment

10 columns were remapped so every write compiles against the real database:

| Model | Column | Was | Now |
|---|---|---|---|
| `Assignment` (hod.py) | `type` | `String(20)` | `SAEnum(AssignmentType, name="assignment_type")` |
| `Exam` (principal.py) | `exam_type` / `mode` | `String(20)` | `SAEnum(ExamType / ExamMode, …)` |
| `Subject` (academic.py) | `subject_type` | `String(20)` | `SAEnum(SubjectType, name="subject_type")` |
| `Enrollment` (enrollment.py) | `status` | `String(20)` | `SAEnum(EnrollmentStatus, name="enrollment_status")` |
| `StaffLeaveRequest` (principal.py) | `status` | `String(20)` | `SAEnum(LeaveStatus, name="leave_status")` |
| `TimetableSlot` (principal.py) | `slot_type` | `String(20)` | `SAEnum(SlotType, name="slot_type")` |
| `StaffProfile` (principal.py) | `employment_type` | `String(20)` | `SAEnum(EmploymentType, …)` |
| `Scholarship` (lms.py) | `type` | `String(30)` | `SAEnum(ScholarshipType, name="scholarship_type")` |
| `ExamAttempt` (principal.py) | `ip_address` | `String(64)` | `INET` (matches every other session table) |

Every new enum class carries **exactly** the values of the matching `CREATE TYPE` in
`database.sql` §3 (verified live from `pg_enum`). Reads keep working unchanged because the
codebase already normalises both plain strings and enum members through the existing
`_value()` helper (`getattr(value, "value", value)`); literal writers
(`Enrollment.status = "ACTIVE"`, `TimetableSlot.slot_type == "CLASS"`, …) remain valid because
these are `str`-based enums and SQLAlchemy binds the literal for comparisons/updates. A live
metadata cross-check (`information_schema.columns` × SQLAlchemy metadata) now reports **zero**
enum mismatches. While touching these files, the third duplicate `LeaveStatus` definition
(hostel.py) was collapsed onto the shared one in `principal.py`.

### Dead / misleading code removed

- `student_service._SUBMITTABLE_STATUSES` — described a gate that does not exist anywhere (the
  real gate lives inline in `submit_assignment`, which blocks only `APPROVED`/`REJECTED`). It
  was exactly the kind of stale constant that misleads the next bug report; deleted (no
  references anywhere).

---

## 3. Database impact

**None — no schema change was needed.** Both fixes are service/UI wiring over statuses and
columns that already exist (`submission_status` already contains `RESUBMIT_REQUESTED`;
`question_options`, `answers.matched_pairs`, `notifications.type` are all existing columns), so
per the project rule *"a SQL file only for the update part"* there is intentionally **no new
migration file** and `database/database.sql` is untouched. The reopen hand-back is a data
transition executed at runtime, audited like every other teacher action.

---

## 4. Tests added

| Suite | File | Covers |
|---|---|---|
| Backend unit (service contracts) | `backend/tests/test_assignment_reopen_and_grading.py` | reopen flips un-reviewed work (update values, one nudge per student, `ASSIGNMENT_REOPENED`); `request_resubmission=false` performs **no** submission update; reopen refuses non-CLOSED (409); body schema defaults; `attempt_detail` returns full option key + MATCH pairs |
| Web component (vitest + jsdom + testing-library) | `fontend/tests/teacher-exam-grading.test.tsx` | grading panel renders both options with `CORRECT` / `STUDENT'S PICK` badges, verdict `WRONG · 0/2`, and MATCH pairings |
| Web component | `fontend/tests/assignment-reopen-resubmit.test.tsx` | reopen dialog sends `(id, true)` / `(id, false)`; after reopen the page correctly leaves CLOSED state; student list shows the `RESUBMIT_REQUESTED` row as actionable (*Submit*) while a plain `SUBMITTED` row shows only *Open* |
| Mobile unit (vitest, node) | `app/src/lib/teacher.test.ts` | reopen request URL/method/body for both modes; grading payload type carries `options` + `matched_pairs` |
| E2E (real PostgreSQL, real app) | `backend/scripts/verify_b1_b2_e2e.py` | the exact reported sequences: close → reopen → student dashboard/pending → resubmit v2 (HTTP 201); reopen-without-nudge leaves `SUBMITTED` untouched; all 6 question types answered → grading payload contains the full key. Self-seeding (random tenant slug), exits non-zero on failure |

Run them:

```bash
# backend (unit)
cd backend && pytest tests/test_assignment_reopen_and_grading.py -q

# backend (E2E — needs a Postgres with database.sql + migrations loaded)
cd backend && DATABASE_URL="postgresql+asyncpg://…" JWT_SECRET_KEY=… \
  python scripts/verify_b1_b2_e2e.py

# web
cd fontend && npm test          # vitest run (3 tests)

# mobile
cd app && npm test              # vitest run (3 tests)
```

## 5. Verification matrix (all green)

- **E2E script** (`backend/scripts/verify_b1_b2_e2e.py`): 6/6 checks PASS (see table in §4).
- **Backend suite**: `420 passed` (415 baseline + 5 new). The **10 failing tests fail identically
  on the untouched baseline commit** (`git stash` comparison run) — pre-existing mock-suite
  issues in coordinator/principal/VP/integration modules, untouched by this change.
- **Web**: `tsc --noEmit` clean, `eslint` reports nothing new on the changed files (the 7
  pre-existing errors/warnings in unrelated files are unchanged), `npm test` 3/3.
- **Mobile**: `tsc --noEmit` clean, `npm test` 3/3.
- **ORM ↔ schema cross-check**: zero enum/inet mismatches remain between the SQLAlchemy
  metadata and a live canonical database.

## 6. Files changed

**Backend** — `app/models/{principal,hod,academic,enrollment,lms,hostel}.py` (type alignment +
shared `LeaveStatus`), `app/services/teacher_service.py` (reopen hand-back + grading key),
`app/services/student_service.py` (dead constant removed), `app/routers/teacher.py` (optional
reopen body), `app/schemas/teacher.py` (`TeacherAssignmentReopen`, `TeacherAnswerOption`,
answer-row fields), `tests/test_assignment_reopen_and_grading.py` (new),
`scripts/verify_b1_b2_e2e.py` (new).

**Web** — `lib/teacher.ts`, `components/teacher/teacher-assignments.tsx`,
`components/teacher/teacher-exam-results.tsx`, `vitest.config.ts` + `tests/setup.ts` (new),
`tests/*.test.tsx` (new), `package.json` (test script + devDeps).

**Mobile** — `src/lib/teacher.ts`, `src/app/(teacher)/assignments/[id]/index.tsx`,
`src/app/(teacher)/examinations/[id]/attempts/[attemptId].tsx`, `vitest.config.ts` (new),
`src/lib/teacher.test.ts` (new), `package.json` (test script + vitest devDep).
