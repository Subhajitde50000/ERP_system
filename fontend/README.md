# shikshasync.me — ERP + LMS Web App

Login experience for the multi-tenant ERP + LMS platform, built to
`login_page_design.md` (v1.0).

**Stack:** Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS 3 · lucide-react

> The design doc targeted Next.js 14. Every 14.x release — including the final
> 14.2.35 — ships with ~20 unpatched security advisories and the line no longer
> receives fixes, so this uses the current Next.js. Nothing in the doc's markup
> needed to change: App Router, `"use client"` and `next/navigation` are the same.

---

## Getting started

```bash
npm install
npm run dev          # http://localhost:3000
```

| Script | Purpose |
|---|---|
| `npm run dev` | Dev server |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | ESLint (flat config) |

---

## Previewing tenants locally

The tenant is resolved **server-side** from the `Host` header, so the right
institution is in the first paint. On localhost there is no subdomain, so use
the `?tenant=` query override:

| URL | Renders |
|---|---|
| `/login` | Platform console (`app.shikshasync.me` roles) |
| `/login?tenant=abc-college` | ABC College · Google Workspace SSO |
| `/login?tenant=dps-school` | DPS School · admission-number placeholder |
| `/login?tenant=nova-university` | Nova University · Entra ID SSO |
| `/login?tenant=xyz-college` | **Tenant-not-found** state (§7) |

Subdomains work too — `abc-college.localhost:3000` resolves the same way.

---

## Routes

| Route | Notes |
|---|---|
| `/` | Redirects to `/login` |
| `/login` | Split-screen login |
| `/forgot-password` | Reset request, same palette |
| `/support` | Placeholder for the "Contact Institution Admin" link |
| `/dashboard` | Single entry — forwards to the caller's role dashboard |
| `/[role]/dashboard` | All 18 institution role dashboards |
| `/notices` | Notice Board feed — one URL, 18 role behaviours |
| `/notices/new` | Composer (role-scoped targets; 403 for view-only roles) |
| `/notices/:id` | Notice detail — attachments, read receipts |
| `/discussion` | Discussion Forum — one URL, role-scoped threads |
| `/discussion/:id` | Thread detail — replies, voting, accepted answer |
| `/profile` | Profile — role-scoped fields and edit rights |
| `/attendance` | Attendance — a distinct layout per role |
| `/examination` | Examination — author / control / monitor / attempt |
| `/examination/:id` | Exam detail — editor · monitor · full-screen attempt · result |
| `/assignments` | Assignments — create / review / submit per role |
| `/content` | Study Material — upload vs. browse per role |
| `/results` | Results — compile / approve / publish / view per role |
| `/timetable` | Timetable — builder vs. read-only per role |
| `/fees` | Fee account — collection desk · structure · statement |
| `/settings` | Settings — sections shown/hidden per role |
| `/settings/modules` | **C-IA-14** — the module toggle |
| `/search` | Global search — results scoped by role |
| `/notifications` | Notification inbox — role-filtered event types |
| `/calendar` | Calendar — role-filtered event sources |
| `/assignments/:id` | Assignment detail — review table · upload · stepper |
| `/hostel/rooms/:id` | Hostel room — warden console · resident view |
| `/library/books/:id` | Library book — circulation console · catalogue entry |
| `/students/:id` | Student detail — role-specific tab sets |
| `/staff/:id` | Staff detail — role-specific tab sets, HR-only payroll |

---

## Dashboards

Built to `Institution_dashboard_design.md`. **All 18 institution role dashboards
are one route.** Each design in §5 is a config object in `lib/dashboards.tsx`, rendered
by shared components — so there is a single layout implementation, not 22
near-identical pages.

Adding or changing a dashboard means editing one config entry:

```ts
TEACHER: {
  roleChip: "Teacher",
  summary: "Today's classes: 4 · Pending reviews: 12",
  stats: [{ label: "Today's Classes", value: "4", icon: CalendarDays }, …],
  panels: [{ kind: "timeline", title: "My Today's Schedule", span: 7, items: […] }, …],
}
```

Panel `kind`s available (add a new one in `components/dashboard/panel.tsx`):
`list · timeline · bars · grid · checklist · funnel · kanban · table · actions · trend`

### Previewing roles

`/dashboard` forwards by role priority. To view any dashboard directly:

| URL | Shows |
|---|---|
| `/teacher/dashboard` | Teacher (§5.5) |
| `/student/dashboard` | Student — low-attendance banner, progress ring |
| `/admin/dashboard` | Institution Admin — setup checklist, audit log |
| `/accountant/dashboard` | Accountant — defaulters table, collection trend |
| `/placement-officer/dashboard` | Placement — pipeline kanban |
| `/admission-officer/dashboard` | Admissions — funnel |

Slugs (18): `admin · principal · vp · hod · teacher · mentor ·
exam-controller · coordinator · accountant · student · parent · librarian ·
hostel-warden · transport-manager · placement-officer · hr-manager ·
admission-officer · store-manager`

### Multi-role users

A user may hold several roles. `?roles=TEACHER,MENTOR` renders the role
switcher pill from §1 — permissions stay the union, the switcher only changes
which dashboard is shown. Single-role users see no pill.

### Testing module gating

`?modules=` overrides the enabled module list (§6):

| URL | Result |
|---|---|
| `/librarian/dashboard?modules=attendance` | "Library module disabled" card (§4.3) |
| `/teacher/dashboard?modules=none` | Sidebar shows core items only |
| `/teacher/dashboard?modules=hostel,library` | Only those two optional items appear |

---

## Where to plug in the API

Everything the backend touches is isolated in **`lib/auth.ts`**. It currently
resolves after a short delay and then throws, so no screen pretends to be
authenticated.

```ts
// lib/auth.ts — replace the stub body
export async function login(c: LoginCredentials): Promise<LoginResponse> {
  return api.post<LoginResponse>("/api/v1/auth/login", c);
}
```

The commented-out real implementation is already in the file. The UI renders
each state in §7 off `AuthError.code`, so **no component changes are needed**
once this talks to the real endpoint:

| `AuthErrorCode` | UI result |
|---|---|
| `INVALID_CREDENTIALS` | "Invalid email or password" |
| `TENANT_NOT_FOUND` | "Institution not found. Check subdomain." |
| `MODULE_DISABLED` | "Contact your institution admin" |
| `ACCOUNT_LOCKED` | Lockout notice |
| `NETWORK_ERROR` | Connection failure |

Other integration points, each marked `TODO(Dev-A)`:

- `lib/tenant.ts` → swap `KNOWN_TENANTS` for `GET /api/v1/tenants/by-slug/:slug`
  (A-11 `TenantMiddleware`)
- `lib/auth.ts` → `requestPasswordReset()`
- `components/auth/login-form.tsx` → SSO button handler
- `lib/session.ts` → replace `getSession()` with the JWT/Zustand auth store
- `lib/dashboards.tsx` → replace the static configs with
  `GET /api/v1/dashboard/stats?role=…` (§8); the response maps 1:1 onto
  `DashboardConfig`

Environment variables (see `.env.example`):

```
NEXT_PUBLIC_API_URL=http://localhost:4000
NEXT_PUBLIC_ROOT_DOMAIN=shikshasync.me
```

---

## Notice Board

Built to `Notice_Board_design.md`. **One URL, 18 role behaviours** — the whole
permission matrix (§3) lives in `lib/notices.ts` as data, so the feed and
composer read from `noticePermissions(roles)` rather than branching on role.

| Can post | Roles |
|---|---|
| Full scope | Institution Admin, Principal |
| No institution-wide | Vice Principal (option disabled with reason) |
| Own dept + its classes | HOD (dept locked) |
| Own classes only | Teacher |
| Institution / class | Exam Controller (auto `EXAM` tag, defaults to IMPORTANT) |
| Classes | Academic Coordinator (title prefixed `(Academic)`) |
| Hostel only | Hostel Warden |
| Placement / institution | Placement Officer |
| Staff / institution | HR Manager (staff-only toggle) |
| **View only** | Accountant · Student · Parent · Librarian · Mentor · Transport Manager · Admission Officer · Store Manager |

Multi-role users get the **union** of post scopes and visibility (§10) — try
`/notices/new?roles=TEACHER,HOSTEL_WARDEN`.

Priority styling: URGENT = 4px red left border + red badge, IMPORTANT = amber,
PINNED = 2px indigo top border + chip. Read receipts and pin/edit/delete appear
only for the author or an admin.

---

## Discussion Forum

Built to `role_based_shared_pages.md` PAGE 3 (C-RB-03). Same data-driven
pattern as the notice board — the matrix lives in `lib/discussion.ts`.

| Role | Scope visible | Post | Moderate |
|---|---|---|---|
| Principal / VP / Institution Admin | All threads | Yes | All |
| HOD | All dept threads | Yes | Whole department |
| Teacher | Own subject/class | Yes | Own subject only |
| Mentor | Mentee group | Yes | Own group |
| Exam Controller | Exam-tagged only | Yes | Exam threads |
| Academic Coordinator | Academic threads | Yes | None (limited) |
| Student | Own class + subjects | Yes | None |
| No forum access | Accountant · Librarian · Parent · Hostel Warden · Transport · Placement · HR · Admission · Store |

Moderation is **per-thread, not global**: `canModerateThread()` checks reach
against the thread's scope, so a Teacher moderates CS301 but not CS307. The
Accept Answer button follows the same rule. Multi-role users take the highest
reach — `?roles=TEACHER,HOD` moderates the whole department.

---

## Profile

Built to `role_based_shared_pages.md` PAGE 4 (C-RB-04). Field permissions live
in `lib/profile.ts` as an **allow-list** (`EditableField` set), which the
backend must mirror on `PATCH /users/me`.

| Role | Extra sections | Can edit |
|---|---|---|
| All staff | Employment (code, designation, dept) | name · phone · avatar |
| Student | Academic (roll no, class, enrolment) | name · phone · avatar |
| Parent | Linked children | name · phone · avatar |
| Institution Admin | Role assignments | all fields + role assignments |
| HR Manager | HR record (payroll, bank, PF) | name · phone · avatar + HR |

Read-only fields render with a lock icon rather than being hidden, so the rule
is visible to the user. **Sensitive HR values (PAN, bank account, PF) are
masked server-side** in `redactHr()` — the raw values never reach the browser;
unmasking must be a separate audited request.

---

## Attendance

Built to `role_based_shared_pages.md` PAGE 5 (C-RB-05). Unlike the other shared
pages, PAGE 5 gives each role a **genuinely different layout**, so
`attendancePermissions()` resolves a `view` kind server-side and the page
dispatches on it.

| Role | View | Actions |
|---|---|---|
| Teacher · Mentor | Session selector → student list → P/A/L/E | mark · lock |
| HOD | Department heatmap (classes × dates) | export |
| Principal · VP · Institution Admin | Institution summary (dept × %) | export |
| Exam Controller | Exam hall, seat-ordered | mark · lock · export |
| Student | Own subject-wise table + % rings | apply for leave |
| Parent | Child's data + child switcher | view only |
| Academic Coordinator | Class-wise, unmarked-session count | export |
| No access | Accountant · Librarian · Hostel · Transport · Placement · HR · Admission · Store |

Statuses follow the DB enum (PRESENT / ABSENT / LATE / EXCUSED). A locked
session is read-only, matching `attendance_sessions.is_locked`. The 75%
threshold from dev doc §9.1 drives the at-risk flags and the red/amber/green
bands, which reuse the dashboard colour scale.

---

## Examination

Built to `role_based_shared_pages.md` PAGE 6 (C-RB-06). Like attendance, each
role gets a different job, so `examPermissions()` resolves a `view` kind
server-side and the page dispatches on it.

| Role | View | Actions |
|---|---|---|
| Teacher · Mentor | Own exams with status badges | create · edit · publish · release |
| Exam Controller | All exams institution-wide | schedule · halls · compile · export |
| HOD | Own department | view · export |
| Principal · VP · Admin | Institution-wide | view · export |
| Academic Coordinator | Timetable (dates × classes) | view · export |
| Student | Upcoming + past for own class | attempt · view results |
| Parent | Child's exams + child switcher | view only |
| No access | Accountant · Librarian · Hostel · Transport · Placement · HR · Admission · Store |

The status lifecycle (DRAFT → PUBLISHED → ONGOING → COMPLETED →
RESULTS_RELEASED) follows dev doc §9.2, and `nextAction()` derives the single
available transition. `/examination/:id` is documented separately below.

---

## Exam Detail

Built to `role_based_shared_pages.md` PAGE 21 (C-RB-21) — *"one URL, three
completely different experiences"*. Originally stubbed from PAGE 6's one-line
note; PAGE 21 specifies far more, so each role now gets its full surface.

| Role | Panels | Actions |
|---|---|---|
| Teacher · Mentor | submission stats · result summary · grading queue · question editor · exam settings | edit **while DRAFT**, publish, grade descriptive, release |
| Exam Controller | hall allocation · live monitor · malpractice flags | allocate halls, resolve flags, compile, publish |
| Student | full-screen timed attempt **or** result view | start, answer, submit |
| HOD · Principal · VP · Admin · Coordinator | submission summary · result summary · question paper | view only |
| *8 other roles* | — | 403 (§6 gives them no examination access) |

**The attempt interface** is a fixed overlay that replaces the app shell for
the duration. Server-authoritative deadline from `expiresAt` (Redis TTL,
§9.2) recomputed each tick so a throttled background tab can't drift;
auto-submit on expiry; tab-switch detection via `visibilitychange`; question
palette showing answered state; MCQ radios or a textarea by question type;
and a confirm step that states how many questions would be marked zero.

**Answer-key handling.** `revealAnswers={false}` only stops the key being
*drawn* — the flags would still sit in the RSC payload, readable from page
source during a live exam. The key is therefore stripped **server-side** in
`paperFor()`:

- Teacher / Mentor (the author) — full paper with the key
- HOD / Principal / VP / Admin / Coordinator — paper with `isCorrect` and
  explanations stripped
- **Exam Controller — no paper at all.** PAGE 21 gives them metadata, halls,
  submissions and flags; not a question list. That also keeps the key away
  from the one role sitting outside the subject during a live exam.
- Student — questions arrive only with the attempt session, keyless; the
  correct option is released afterwards, and only when `allow_review` is set.

**Deviation:** `canGrade` is Teacher-only. §4.6 makes the Exam Controller
*"compile and publish results"*; marking papers stays with the subject
teacher, matching PAGE 21 listing "grade descriptive" under Teacher alone.

Derived, not hand-written: submission stats and the grade histogram are
counted from the attempt rows, the paper's marks sum to the exam's
`total_marks`, and the student's answer-review breakdown is scaled so the
per-question scores add up **exactly** to the recorded result (23/30).

---

## Assignments

Built to `role_based_shared_pages.md` PAGE 7 (C-RB-07). Same view-kind pattern
as attendance and examination.

| Role | View | Actions |
|---|---|---|
| Teacher · Mentor | Own assignments + submission counts | create · edit · close · review |
| HOD | Dept assignments + **pending review per teacher** | view · export |
| Student | Pending / Submitted / Approved tabs | submit · resubmit · read feedback |
| Parent | Child's status + child switcher | view only |
| Principal · VP · Admin | Institution-wide summary | view · export |
| No access | Exam Controller · Coordinator · Accountant · Librarian · Hostel · Transport · Placement · HR · Admission · Store |

**Milestone assignments** follow dev doc §9.3: each stage stays `LOCKED` until
the previous one is approved, so the unlock chain is visible to the student.
Resubmission uses the DB's `version` counter, and late submissions surface the
penalty percentage before the student commits.

---

## Assignment Detail

Built to `role_based_shared_pages.md` PAGE 22 (C-RB-22) — *"one URL, two
experiences"*, plus the HOD's read-only overview.

| Role | Panels | Actions |
|---|---|---|
| Teacher · Mentor | progress · milestone list · per-student submission table | edit milestones, review, approve / reject / ask-to-resubmit |
| Student | instructions · milestone stepper · feedback · file upload | submit, resubmit, read feedback |
| HOD · Principal · VP · Admin | submissions overview + completion rate · brief · milestone list | view only |
| Parent | instructions + own status, read-only | — |
| *10 other roles* | — | 403 (§6 gives them no assignment access) |

**Milestone edits are gated twice.** PAGE 22 grants the Teacher "edit
milestones", but §9.3 makes approving a stage unlock the next — re-ordering
the chain after students have started would invalidate approved work. So
`canEditMilestoneChain()` allows structural edits only while the assignment is
open **and** nothing has been submitted; a submitted stage stays reviewable,
and the lock states its reason rather than hiding the controls.

**Entitlement is decided in the data layer**, as on PAGE 20/21: the permission
object is passed into `getAssignmentDetail()`, so a student's payload contains
no `submissions` array at all. Verified by grepping the raw server HTML for
classmates' names and teacher feedback across all 8 roles with access.

**Two deviations, flagged.** PAGE 22 names only Teacher / Student / HOD;
§6 gives the Principal `● view` on assignments, so Principal / VP / Admin get
the same read-only overview as the HOD rather than a 403. And the Parent gets
the student layout without the upload panel, matching PAGE 7's "child's
assignment status, view only".

Derived, not hand-written: the submission table's status mix comes from the
assignment's own `reviewedCount` / `pendingReview` counters, **scaled to the
roster size** — used absolutely, a `reviewedCount` of 16 over a 10-student
sample put every row in the reviewed band and left the teacher's approve/reject
queue empty. Class-level percentages still come from the real counters; only
the approved/needs-changes *split* is taken from the sample. The roster itself
is now `getClassRoster()` in `lib/attendance-data.ts`, shared with attendance
marking and exam halls so a student can't be named differently per page.

---

## Content / Study Material

Built to `role_based_shared_pages.md` PAGE 8 (C-RB-08). Same view-kind pattern.

| Role | View | Actions |
|---|---|---|
| Teacher · Mentor | Own uploads by subject → chapter | upload · edit · hide/unhide · delete |
| HOD | All dept content across teachers | view · **flag inappropriate** |
| Student | Own subjects: chapter → type | view · stream · read · download |
| Parent | Child's subject content + switcher | view only |
| Principal · VP · Admin | All content institution-wide | view only |
| No access | Exam Controller · Coordinator · Accountant · Librarian · Hostel · Transport · Placement · HR · Admission · Store |

Material is grouped **subject → chapter** for every role — the browse tree
students need also works as the teacher's own list, so one library component
serves all five. `is_visible` is enforced in the data layer: hidden drafts stay
listed for the uploader and oversight roles but never reach students or
parents. Files follow dev doc §11: private S3, presigned PUT to upload, signed
GET (15 min) to read — the client never sees a raw S3 URL.

---

## Results

Built to `role_based_shared_pages.md` PAGE 9 (C-RB-09).

| Role | View | Actions |
|---|---|---|
| Teacher · Mentor | Own subject across classes | release subject results |
| Exam Controller | All publications | compile · publish · export |
| HOD | Class summary — pass %, toppers | view · export |
| Principal · Admin | Institution summary + approval queue | **approve** · export |
| Vice Principal | Institution summary | view · export |
| Student | Own breakdown, grade, rank | download grade card |
| Parent | Child's results + switcher | download grade card |

**Publication is a two-person control.** The lifecycle is
`DRAFT → COMPILED → APPROVED → PUBLISHED`, and no single role can walk it end
to end: the Exam Controller compiles and publishes, the Principal approves in
between. Whichever stage a viewer can't advance shows *"Waiting on …"* instead
of a button, so the separation is visible rather than implied.

Two doc conflicts were resolved against the more specific source:
`role_based_shared_pages.md` PAGE 9 lists "approve" under Exam Controller and
groups VP with Principal, but `role_based_system_design.md` §4.6 gives the
controller "compile and publish" only, §4.3 gives the Principal "view and
approve", and the §6 matrix marks VP as `● view`. The code follows §4/§6.

---

## Timetable

Built to `role_based_shared_pages.md` PAGE 10 (C-RB-10).

| Role | View | Actions |
|---|---|---|
| Academic Coordinator | Full builder grid, all classes | create slots · bulk upload · conflicts · substitutions |
| Teacher · Mentor | Own weekly teaching schedule | view only |
| HOD | Department timetable, all its classes | view · export |
| Principal · VP · Admin | All timetables | view · export |
| Student | Own class weekly timetable | view only |
| Parent | Child's class timetable + switcher | view only |
| No access | Exam Controller · Accountant · Librarian · Hostel · Transport · Placement · HR · Admission · Store |

One `TimetableGrid` serves every role — days across, periods down. The teacher's
personal view swaps the teacher label for the class, and empty cells only
become `+` targets for the builder. **Clash detection is computed from the
slot set**, not hardcoded, so the count always matches what the grid contains;
substitutions render amber in-cell and as a summary band.

---

## Notifications

Built to `role_based_shared_pages.md` PAGE 15 (C-RB-15). **Structurally
different from the other role-based pages:** the doc says *"same layout,
different notification types per role"*, so this is a **content filter**, not a
view dispatch. There is no view-kind switch and no permission-denied state —
every user has an inbox (DB §10.1).

Two data tables drive it, with no role logic in any component:

- `EVENT_META` — icon, colour, category and deep-link per event. This is the
  doc's `<NotificationItem type={...}>` contract made concrete.
- `ROLE_EVENTS` — the PAGE 15 matrix: which of the 36 events each role receives.

`eventsForRoles()` unions the sets for multi-role users. Verified event counts
per role match the table exactly (Teacher 4, Student 6, HR 2, …) with **no
cross-role leakage** — an Accountant never sees a submission notice.

The topbar bell now links here and its badge is the **real** unread count from
`getUnreadCount()`, replacing the previous hardcoded `3`.

---

## Calendar

Built to `role_based_shared_pages.md` PAGE 18 (C-RB-18). Like notifications,
this is a **content filter** — same month grid for every role, only the event
sources differ (`ROLE_SOURCES` is the PAGE 18 matrix as data).

| Role | Sources |
|---|---|
| Teacher · Mentor | Classes · Exams · Assignments · Holidays |
| Student | Classes · Exams · Assignments · Holidays · Leave |
| Parent | Exams · Holidays · Fees |
| Exam Controller | Exams · Results |
| Academic Coordinator | Classes · Exams · Events · Holidays |
| HOD | Exams · Events · Leave |
| HR Manager | Leave · HR |
| Placement Officer | Placement |

**The calendar has no table of its own** — it aggregates records that already
exist (`timetable_slots`, `exams`, `assignments`, `result_publications`) plus
holidays/events/HR/placement dates. It reads the *same fixtures* the other
pages use, so the calendar can never disagree with the module it came from.
Weekly timetable slots are expanded across the visible month.

Month cells show two entries plus an overflow count, prioritising exams and
deadlines over routine classes; the day agenda beside the grid carries full
detail and deep links. Times render in **Asia/Kolkata**, not raw UTC.

---

## Student Detail

Built to `role_based_shared_pages.md` PAGE 19 (C-RB-19). Each role gets a
different **tab set** over one shared header and tab strip.

| Role | Tabs | Action |
|---|---|---|
| Institution Admin | Profile · Attendance · Results · Assignments · Fee · Enrollment | full edit |
| Principal · VP | Profile · Attendance · Results | view |
| HOD | Profile · Attendance · Results *(department)* | view |
| Teacher | Attendance *(own subject)* · Assignment submissions | view |
| Mentor | Profile · Attendance · Results · Notes *(private)* | add notes |
| Exam Controller | Results · Exam attempts + malpractice | view |
| Accountant | Fee account | record payment |
| Placement Officer | Profile · Academic records · Applications | shortlist |
| Librarian | Library | issue / return |
| Hostel Warden | Hostel | manage allotment |
| Transport Manager | Transport | update route |
| Admission Officer | Application & documents | enroll |
| **HR Manager** | — | *"HR manages staff, not students"* |

Where PAGE 19 narrows a tab, the scope is stated in the UI ("Showing
attendance for **your subject**") rather than silently showing partial data.
The four academic tabs **reuse the Attendance / Results / Assignments
components and fixtures**, so this page can't disagree with those modules —
only the eleven sections with no existing home are new.

Guarded actions reflect real state: Shortlist is disabled for a student with
an active backlog; Enroll is disabled while documents are unverified.

---

## Staff Detail

Built to `role_based_shared_pages.md` PAGE 20 (C-RB-20), backed by the HR
tables in `database_design_complete.md` §8.5. Same pattern as PAGE 19 — the
two pages share `components/shared/detail-layout.tsx`, so the header, tab
strip and panel wiring exist once.

| Role | Tabs | Action |
|---|---|---|
| Institution Admin | Profile · Roles · Subjects taught · Leave history | edit profile, manage roles |
| Principal · VP | Profile · Attendance · Leave history | view |
| HOD | Profile · Subjects · Attendance *(own dept)* | view |
| HR Manager | HR profile *(incl. banking)* · Salary · Leave balance · Payslips · Documents · Appraisals | full HR edit |
| *the other 13 roles* | — | 403 with a reason |

**Deviations, flagged for review**

1. §6 grants Institution Admin `● full` on HR, but PAGE 20 gives banking,
   salary and payslips to the **HR Manager alone**. Code follows PAGE 20 —
   separation of duties, the same reasoning as two-person result publication.
   One-line change: `canViewBanking` in `lib/staff-detail.ts`.
2. HR's row says *"Leave balance"* where Admin/Principal get *"Leave
   history"*. §5.4 also makes HR the approver, so the HR leave tab carries the
   balance cards **and** the history with approve/reject, rather than adding a
   tab the doc doesn't list.
3. The 13 roles outside the matrix are resolved from §6 — none has staff-record
   access, so each gets a 403 with a role-specific reason rather than a blank
   page. The Accountant's says payroll runs live under Finance (§4.7 grants
   payroll *processing*, not the staff record).

**Two server-side guards run before any data is fetched**

- **Entitlement** — the permission object is passed *into* `getStaffDetail()`,
  so a section the caller doesn't own is absent from the RSC payload, not
  hidden by CSS. PAN, bank account and PF are masked server-side; unmasking is
  a separate audited request (§11). Verified by grepping the raw HTML for the
  raw values across all seven roles with access.
- **Department fence** — §4.4 scopes a HOD to their own department, so the
  fence covers the whole record, not just the Attendance tab. `/staff/s3`
  (ECE) is refused for a CSE HOD. A user holding HOD **and** Principal loses
  the fence, since permissions are the union.

Every figure is **derived, not hand-written**: leave balances come from the
approved requests, payslips from the salary structure and the attendance
months (April's 1 LOP day visibly reduces that month's net), and subjects
taught from `getTeacherSlots()` — so the weekly period count can't drift from
the timetable grid. Four staff records exist so links resolve to real people;
`s4` is non-teaching, which exercises the Subjects empty state.

---

## Hostel Room Detail

Built to `role_based_shared_pages.md` PAGE 23 (C-RB-23), backed by the hostel
tables in `database_design_complete.md` §8.2.

| Role | Panels | Actions |
|---|---|---|
| Hostel Warden | room · occupants · tonight's roll-call · attendance history · leave · complaints · warden | allot bed, mark attendance, approve leave, resolve complaints |
| Principal · VP · Admin | the same record | view only |
| Student | own room · roommates *(names only)* · warden contact | — |
| Parent | child's allotment · block · warden contact | — |
| *12 other roles* | — | 403 |

**"Names only" is a payload rule, not a CSS rule.** PAGE 23 limits the Student
to roommate *names*, so `canSeeOccupantDetail` decides what the data layer
attaches — a roommate's roll number, class, attendance and tonight's status
are simply absent from a student's RSC payload, as are the room's complaints
and leave log. The student's *own* row stays complete, because it is their
record. Verified by grepping raw server HTML across all six roles with access.

**Three server-side guards** run before any section is built: the hostel is an
optional module (§3) so it can be switched off entirely; 12 roles get a 403;
and Student/Parent are fenced to the room they are allotted to — `/hostel/rooms/C-012`
is refused for a resident of A-104, with a link to their own room rather than
a dead end. A user holding STUDENT **and** HOSTEL_WARDEN loses the fence.

**Deviation:** §6 gives Principal / VP / Institution Admin `● view` on optional
modules, so they get the warden's record read-only rather than a 403.

**Doc conflict flagged:** `hostel_attendance.status` is typed
`attendance_status ENUM` and documented as `PRESENT / ABSENT / ON_LEAVE`, but
§12 defines that enum as `('PRESENT','ABSENT','LATE','EXCUSED')` — `ON_LEAVE`
is not a member, and `LATE`/`EXCUSED` are meaningless for a nightly roll-call.
The code follows the column's documented semantics (`HostelAttendanceStatus`
in `types/hostel.ts`); Dev-A should either extend the enum or give the hostel
its own.

Every figure is derived from one `nightStatus()` function: the room's 13-night
average, each occupant's term-to-date percentage, the "nights with an absence"
count and tonight's pre-filled roll-call all come from it, so the grid and the
numbers beside it cannot disagree. The student-detail hostel tab (PAGE 19) now
reads its room, bed and percentage from this module too, and links through.

---

## Library Book Detail

Built to `role_based_shared_pages.md` PAGE 24 (C-RB-24), backed by `books`,
`book_copies` and `book_issues` in `database_design_complete.md` §8.1. This
completes all 24 role-based shared pages.

| Role | Panels | Actions |
|---|---|---|
| Librarian | circulation stats · availability · every copy + accession number · full issue history · catalogue record | issue, return, mark GOOD/FAIR/DAMAGED/LOST, record fine payment, edit book |
| *all 17 other roles* | availability · shelf location · own loan · catalogue record | view only |

**Borrower identity is a payload rule.** PAGE 24 gives "current borrowers" and
"full issue history" to the Librarian alone — circulation records say who read
what. `canSeeBorrowers` therefore controls what the data layer attaches: a
reader's payload contains no accession numbers, no borrower names and no
history at all. Their *own* loan is returned, because it is their own record.
Verified by grepping raw server HTML across all 10 reader roles tested.

**Two deviations, flagged.** PAGE 24's second row reads "Student / Staff",
which taken literally excludes Parents — but §6 gives Parent `● child` on
optional modules and a catalogue entry carries nothing personal, so Parents
read it too; a 403 on a shelf listing would be surprising. And the doc's
*"no issue from here — goes through librarian"* is honoured for **every**
reader including the Institution Admin, with the page saying so rather than
silently omitting a button.

Every number is derived from `book_copies`: `books.available_copies` is a
denormalised counter in the DB, but here availability, on-loan and withdrawn
counts are computed from the copy list so the header cannot contradict the
rows beneath it — a DAMAGED or LOST copy is unavailable even though nobody
holds it, which is why `available + on loan ≠ total`. Fines come from one
`FINE_PER_DAY` constant applied to the overdue days, and historic fines are
measured at the moment of return rather than against today. The student-detail
library tab (PAGE 19) now reads its loans, due dates and outstanding fine from
this module and links each title through.

---

## Global Search

Built to `role_based_shared_pages.md` PAGE 17 (C-RB-17) — *"one URL, results
scoped by role"*. Third **content-filter** page, alongside notifications
(PAGE 15) and the calendar (PAGE 18): one layout for everybody, only the
entity kinds differ. Like the calendar it owns no table — it queries the
modules that already exist.

All 10 documented roles map exactly to the doc:

| Role | Kinds |
|---|---|
| Institution Admin | users · departments · classes · subjects · notices · audit logs |
| Teacher · Mentor | students *(your classes)* · assignments *(yours)* · content *(yours)* · notices |
| Student | study material · notices · discussions · exams |
| HOD | staff · classes · assignments · results *(your department)* |
| Exam Controller | exams · students *(roll no)* · results |
| Accountant | students · fee accounts · receipts |
| Librarian | books *(title / author / ISBN)* · borrowers |
| Placement Officer | students · companies · drives |
| HR Manager | staff *(name / employee code)* · leave records |
| Admission Officer | applications *(name / email / application no)* |

**Search is a shortcut, never a privilege escalation.** Only the caller's own
kinds are queried — nothing is fetched and then filtered in the browser, which
is what makes the fan-out safe to mirror on the backend. Notices and
discussion threads are read through **their own permission-scoped data
layers**, so a hit can't surface a record the owning page would hide. Verified
with a 17-assertion scoping suite: a Student finds no staff, fees or other
students; only the Admin reaches audit logs.

**Deviation:** PAGE 17 names 10 roles but says the bar is *"available to all
roles"*, so the other 8 are resolved from §6 — Mentor mirrors Teacher (§2.2
teacher-level), VP mirrors Principal, and the rest get the kinds their own
dashboards already surface. Nobody gets an empty box.

Matching normalises case, accents and punctuation, so `9780262046305` finds an
ISBN stored as `978-0262046305`. When the match wasn't on the title the row
says why (*"matched Thomas H. Cormen"*), results are grouped by kind in
permission order and capped per kind with a `+ n more` note, and the empty
state offers a one-click example per kind drawn from the same fixtures.

The topbar search box — previously an inert input on every page — now submits
here, and ⌘K focuses it as its hint always promised.

---

## Settings

Built to `role_based_shared_pages.md` PAGE 16 (C-RB-16), plus
`role_based_system_design.md` §3/§7 for the module toggle.

| Role | Sections |
|---|---|
| Institution Admin | General · Modules · Academic year · Fee structure · Notification rules · Branding |
| Principal | Academic year *(view only)* |
| HR Manager | Leave policies · Salary defaults |
| **Every role** | Profile · Password · Notification preferences |

**The "All roles" row is a floor, not a row.** Read strictly, PAGE 16's
Institution Admin entry omits "Change password" — which can't be intended, so
the last row is appended to *every* role. That also means there is no 403 on
`/settings`: everyone can at least change their own password.

### Settings → Modules (C-IA-14)

The assignment doc calls this "THE module toggle page" and both the sidebar
and the admin dashboard deep-link to it, so it has its own route. The toggle
list is one component with two entry points — inline in `/settings`, and
standalone at `/settings/modules` (admin-only).

§3 and §7 define what a toggle actually *does*, and the UI reflects all of it:

- **8 core modules** are locked on and have no switch at all.
- **8 optional modules** each name the role they activate, so the admin can
  see that turning off Hostel is what removes the Hostel Warden.
- **Enabling is one click. Disabling asks first** — it revokes a role
  immediately, so the dialog names the role, counts the users cut off
  ("3 Hostel Warden users lose access immediately") and states the volume of
  data parked ("18,400 records are kept, not deleted"). §3 promises retention;
  the UI says so rather than leaving the admin to hope.
- The toggle reads `session.enabledModules`, the same source the sidebar and
  every module guard use, so `?modules=library,hostel` drives this page too.

**Doc conflict flagged:** §3's checklist lists **7** optional modules and omits
`finance`, and the dashboard doc says "11/15". But `packages/shared-types/
modules.ts` and §6's matrix both treat finance as a real module with the
Accountant attached, and the sidebar already gates `/fees` on it. The code
keeps **8 core + 8 optional = 16**. TODO(Dev-A): reconcile §3.

Other notes: the Principal's academic-year section renders read-only rather
than hidden, matching "Academic Year (view)". The notification section is two
distinct things — the admin's institution-wide *rules* (C-IA-16, the channel
matrix from dev doc §12.1) and everyone's personal *preferences*; a channel
the institution doesn't use can't be opted into, and In-app is always on
because it is the inbox. Profile links to PAGE 4 rather than duplicating the
field allow-list.

The sidebar's Settings entry now points at `/settings` and is no longer
admin-only, since every role has something there.

---

## Fee Account

Built to `role_based_shared_pages.md` PAGE 11 (C-RB-11), backed by the finance
tables in `database_design_complete.md` §9.

| Role | View | Actions |
|---|---|---|
| Accountant | every account · search · filter · defaulters | record payment, issue receipt, apply scholarship |
| Institution Admin | fee structure + overall collection | set up fee heads, installment schedule |
| Principal · VP | high-level collection summary | view only |
| Student | own account, installments, receipts | download receipt |
| Parent | child's account | download receipt |
| *12 other roles* | — | 403 |

**Scope is a payload rule.** A student receives exactly one account — their
own. The class ledger, the collection roll-up, the structure editor and the
scholarship schemes are absent from their payload, not hidden by CSS. Even
the Principal, who sees institution totals, never receives the row-level
ledger; §4.3 says they cannot manage fees, so the summary carries no levers.

**Every figure is derived.** `net_payable`, `balance_due`, installment status
and the whole collection summary are computed from the structure and the
payment rows, so the ledger cannot contradict itself: the installments always
sum to the net payable (the last one absorbs rounding), an installment goes
`OVERDUE` from its due date rather than a stored flag, and class subtotals sum
to the institution total. Verified against an independent recomputation —
₹5,59,000 collected of ₹9,59,000 demanded, 58%, 2 defaulters.

**One owner per fixture.** The fee module owns the money, and the two pages
that previously invented their own now read from it: student detail's Fee tab
(PAGE 19) quotes `getOwnFeeAccount()` and links to `/fees` for collection
rather than duplicating the payment form, and global search's receipt and
fee-account hits come from `getAllReceipts()` / `getFeeAccountFor()`. All
three pages now say ₹96,000 payable with ₹48,000 paid for the same student.

**Deviations, flagged.** PAGE 11 names five roles; §6 gives the VP the
Principal's scope minus final approval and the VP shares that read-only view
everywhere else in this app, so the VP gets the same summary. The other 12
roles get a 403 — fee data is financial and personal.

Late fines are one constant (`LATE_FINE_PER_DAY`, capped) rather than being
scattered through fixtures; no doc states a rate, so `tenant_settings` should
own it once Dev-A adds it.

---

## User Directory

Built to `role_based_shared_pages.md` PAGE 12 (C-RB-12) — the shared-page form
of the admin's `/users` (C-IA-08) — backed by `users` (§5.5),
`role_assignments` (§5.6), `staff_profiles` (§8.5) and `student_enrollments`
(§6.6).

| Role | Who they see | Actions |
|---|---|---|
| Institution Admin | all 25 users | create, edit, deactivate, assign roles, reset password |
| HOD | 6 CSE teachers | view profiles |
| Principal · VP | all staff + students (25) | view profiles |
| HR Manager | all 15 staff | view + edit HR profile |
| Placement Officer | 10 students | view profiles, check eligibility |
| Admission Officer | 3 newly enrolled | view post-enrolment profiles |
| *11 other roles* | — | 403 |

**Not a view-kind dispatch.** Every role gets the same searchable list; what
differs is the *population*, the *column set* and the *row actions*. That
makes it a content filter (like notices and search), so it is one data table
in `lib/user-directory.ts` and one component that never names a role.

**Scope is a `WHERE` clause, not a filter.** `getDirectoryData(perms)` builds
only the rows and only the columns the caller owns. A HOD's RSC payload
contains four names and no student, no employment type for anyone outside
CSE, and no `last_login_at` at all. Verified by grepping raw server HTML:
35 leak checks across 9 role/value pairs, 0 leaks, with a positive control
proving the grep sees row data.

**Eligibility is derived, and says why.** The Placement Officer's verdict is
computed from `ELIGIBILITY_RULES` (CGPA 6.5+, 0 backlogs, 75% attendance)
against the modules that own each input — a stored boolean beside a CGPA
eventually disagrees with it. Every failed rule is named on the row, since
"not eligible" alone isn't actionable. Independently recomputed: 6 of 10
eligible.

**Deviations, flagged.**
1. PAGE 12 names 6 role groups; the other 11 get a 403 with a pointer to
   where those people *are* reachable (a Librarian looks a borrower up in the
   library, a Warden in the hostel roll-call). §6 gives none of them a
   user-management grant.
2. HR's "edit HR profile" deep-links to PAGE 20's HR tabs rather than adding
   a second HR editor here. That surface already implements masking and the
   audited unmask; a list row is not the place to re-implement it, and no
   confidential field is in this payload at all.
3. "Newly enrolled" is undefined in the docs. It is read as
   `enrollment_date` inside a 90-day window (`NEW_ENROLMENT_WINDOW_DAYS`),
   stated in the UI, and belongs in `tenant_settings` — intake cadence
   differs by institution.
4. "ALL users" is staff + students here because §6.7 makes
   `parent_student_links` school-only and this tenant is a college. The same
   audience picks up parent accounts on a school tenant with no code change.

**Multi-role widens, never narrows.** A user holding HOD *and* Principal sees
all 25 rather than staying fenced to CSE; the department fence survives only
when every granted role carries the same one.

**Fixture consolidation done as part of this page.** Three files each kept
their own copy of "which class is student *s3* in" (`attendance-data`,
`fee-data`, `hostel-data`), with a `?? "FY-BSc-A"` fallback in two of them.
The roster now owns it (`RosterStudent.className`) and the other two read it,
so a roster change can't silently re-seat a student on one page only. The
staff roster also grew from 4 to 15 — the people already named across
notices, timetable, audit logs and leave reviews (Kavita Menon, Anita Desai,
Meera Krishnan, Ganesh Bhat…) had no `users` row, so a directory would have
had to invent a parallel list of people to show anybody.

---

## Leave Management

Built to `role_based_shared_pages.md` PAGE 13 (C-RB-13), across the three
leave tables the docs define.

| Role | Sections | Actions |
|---|---|---|
| Student | own class leave | apply, upload document |
| Parent | child's class leave | view only *(deviation 3)* |
| Teacher | students (own classes) + own HR leave | approve / reject, apply |
| HOD | students (own dept) + own HR leave | approve / reject, apply |
| HR Manager | all staff + own HR leave | approve / reject, edit balances |
| Hostel Warden | residents + own HR leave | approve / reject, apply |
| Admin · Principal · VP | students (+ staff, for Admin) + own | *(deviation 2)* |
| *9 other staff roles* | own HR leave only | apply *(deviation 4)* |

**Three tables, not one.** `attendance_leaves` (§7.1, auto-marks EXCUSED),
`leave_requests` (§8.5, debits a policy balance) and `hostel_leave_requests`
(§8.2, has a destination and emergency contact) share only from/to/reason/
status. `LeaveKind` discriminates and each keeps its own fields; flattening
them would lose the medical certificate, the balance and the contact number.

**Apply and approve are sections, not opposite roles.** PAGE 13's fourth row —
"Staff (Teacher, HOD, etc.)" — overlaps rows two and three, so a Teacher gets
*both* their students' queue and their own HR leave. Modelled as a view-kind
dispatch one of them would have to lose, so this is a section list per role
like settings and the detail pages.

**Nothing is duplicated.** Staff rows and the policy table come from the HR
module (`getStaffLeave`, `LEAVE_POLICIES`), hostel rows from the hostel module
(`getAllHostelLeave`), students from the shared roster. Only the student
attendance-leave rows are defined here, because `attendance-data` models them
for one student and this page needs the class-wide queue. Removing the
third copy of the policy table also fixed PAGE 14, which had its own.

**Scope is applied before a row is built.** A Teacher's payload holds their
own classes' 6 requests; the other 3 never leave the data layer. Verified by
grepping raw server HTML — 43 checks, 0 leaks, positive control passing.
Leave reasons are the most sensitive free text on the site (they are often
medical), so this matters more here than on most pages.

**Deviations, flagged.**
1. "Staff (Teacher, HOD, etc.)" is read as *every employee* — §8.5 gives all
   staff a leave balance, so withholding the apply form from the Librarian
   would leave them no way to use it. 16 of 18 roles get the section.
2. Admin / Principal / VP also get the student queue: §4.2 grants "● full" on
   attendance and §4.3 makes the Principal the academic authority, so a leave
   escalated past the HOD has somewhere to land. Mentor is deliberately *not*
   an approver — §2.2's grant is pastoral, not decisional.
3. Parent gets a read-only view of their child's leaves; they already see the
   same rows on `/attendance`.
4. Nine staff roles get only the own-leave section — no doc grants them
   anyone else's queue.

**Separation of duties.** The HR Manager's own request is excluded from her
own approval queue and appears under "My leave" instead, matching the rule
the appraisal cycle already applies (§8.5: a head can't be their own
reviewer). `TODO(Dev-A)` notes the real rule escalates to the Principal.

---

## Reports

Built to `role_based_shared_pages.md` PAGE 14 (C-RB-14), aggregating the
modules that own each figure.

| Role | Reports | Source |
|---|---|---|
| Institution Admin | enrolment · fee collection · attendance · results | attendance + fee + result |
| Principal · VP | dept attendance · result trends · exam pass % | attendance + result |
| HOD | teacher-wise marking · subject-wise results | timetable + staff + result |
| Teacher | class attendance · assignment completion | attendance + assignment |
| Exam Controller | pass % · toppers · subject analysis · malpractice | result + examination |
| Accountant | collection · defaulters · scholarships | fee |
| Placement Officer | placed % · recruiters · dept-wise | placement |
| HR Manager | headcount · leave utilisation · payroll | staff directory |
| Transport Manager | route utilisation | transport |
| Librarian | circulation · overdue · most borrowed | library |
| Store Manager | stock movement · low stock · vendor POs | inventory |
| *Hostel Warden · Admission Officer · Coordinator* | see deviation 1 | hostel · admission · timetable |
| Mentor · Student · Parent | — | 403 |

**No new renderer.** PAGE 14 asks for `<ReportSection>` components that render
per role; taken literally that is eleven near-identical components. A section
is instead a *config object* of `Stat`s and `Panel`s, drawn by `StatsCard` and
`DashboardPanel` — the same two renderers the 18 dashboards use. This page
adds no chart code and names no role; a new report is a data change.

**Nothing is invented.** Every figure aggregates from the module that owns the
rows, so a report cannot contradict the page you click through to. Verified
against an independent recomputation: 910 students, 83% weighted attendance,
81% weighted pass rate, ₹5,59,000 collected of ₹9,59,000 (58%, 2 defaulters —
identical to `/fees`), 63 offers at ₹6.9 LPA weighted, 152/227 seats, 11
library issues, 45% admission conversion.

**Weighted, not averaged.** Institution attendance, pass rate and average
package are weighted by cohort size / offer count. A plain mean of the four
placement companies reads ₹7.4 LPA against a true ₹6.9 — a 7% overstatement
from treating a 9-offer recruiter the same as a 24-offer one.

**Scope is applied before aggregation.** `getReportData(perms, modules)`
builds only the requested sections, so an unentitled aggregate is never
computed. That matters more here than elsewhere: an aggregate still discloses
rows the caller cannot read individually. Verified by grepping raw server
HTML — 54 checks, 0 leaks, positive control passing.

**Deviations, flagged.**
1. PAGE 14 lists 11 role groups, but `role_based_system_design.md` §4/§5 grant
   a Reports row to three more — Hostel Warden (§5.1 "Occupancy and attendance
   reports"), Admission Officer (§5.5 "Admission funnel and conversion") and
   Academic Coordinator (§4.5 "Academic calendar reports"). Every other module
   owner in the table got theirs, so the omission reads as an oversight. They
   are granted their §4/§5 row; flip them to `denied()` if PAGE 14 is meant to
   be exhaustive.
2. Mentor, Student and Parent 403 — no Reports row anywhere in the docs, and
   their own records are already on their dashboard.
3. Read-only for everyone. No role's Reports row grants a mutation, and §4.3
   bars the Principal from fees outright, so the only action is export.
4. Transport, inventory, placement and admission have no module page yet, so
   their aggregates live in `report-data.ts` with a `TODO(Dev-B)` to move each
   into its module's data layer. Their figures match the dashboards that
   already show them (route load 94/81/67/52/38%).

---

## Platform console (Super Admin)

The eight Super Admin pages, C-SA-01…08. They live under `app/(platform)/`
and are served at `/platform/*` locally; in production the assignment doc §2
puts them on **`app.shikshasync.me`**, a different origin from the institution
subdomains. `lib/tenant.ts` already treats `app` as a reserved slug, so the
split is real, not cosmetic.

| Task | Page | Route |
|---|---|---|
| C-SA-01 | Dashboard | `/platform/dashboard` |
| C-SA-02 | Institution List | `/platform/institutions` |
| C-SA-03 | Institution Detail | `/platform/institutions/:id` |
| C-SA-04 | Create Institution | `/platform/institutions/new` |
| C-SA-05 | Plans | `/platform/plans` |
| C-SA-06 | Platform Users | `/platform/platform-users` |
| C-SA-07 | Audit Logs | `/platform/audit-logs` |
| C-SA-08 | Settings | `/platform/settings` |

**"Audit-only, no edit" shapes the UI.** `role_based_system_design.md` §4.1
grants the Super Admin "access all institution data (audit-only, no edit)".
So plan, modules and tenant lifecycle *are* editable — those are platform
concerns — while the tenant's own records are read-only, which the detail
page states rather than implies.

**ABC College is the tenant this app runs as.** Its headcount on the platform
is summed from the institution's own department table and staff directory
(910 students, 14 active teachers), so the two consoles can't disagree.

**Deviations, flagged.**
1. The DB enum is `platform_role AS ENUM ('SUPER_ADMIN','SUPPORT','SALES',
   'FINANCE')` (§12) but `types/auth.ts` — from `role_based_system_design.md`
   §2.1, and depended on by 40+ files — uses `SUPPORT_STAFF /
   SALES_EXECUTIVE / FINANCE_MANAGER`. The app's names win; `PLATFORM_ROLE_DB`
   maps to the DB spelling at the boundary.
2. `is_active` (§4.2) and `subscriptions.status` (§4.4) are independent
   columns. A suspended tenant can still hold an ACTIVE subscription, so
   `tenantState()` lets suspension win — that is what actually blocks sign-in.
3. Finance Manager gets a "not built yet" page rather than a 404 — a real
   role with a real section (C-FM), just not this milestone. Support (C-SP)
   and Sales (C-SL) are now built.

**Guard worth noting:** the last active Super Admin cannot be deactivated —
locking the only one out of the console is unrecoverable without a DB edit.

---

## Submission detail (Teacher)

C-TC-16 — "View one submission, files, add feedback, set score".

| Task | Page | Route |
|---|---|---|
| C-TC-16 | Submission Detail | `/teacher/submissions/:id` |

**Not a duplicate of C-TC-15.** The review table already expands a row into a
compact grading form, and that stays — it is faster for a run of quick
approvals. This page is the same decision with room to make it properly: the
full text response instead of a clipped preview, every file with its size,
and the **earlier attempts** that explain why the work is on its second
version. It exists as a URL because a submission is the thing a teacher gets
*linked to* — from a notification, a dashboard count, or a colleague — and
hunting for one student in a table of forty is the workflow it removes.

It reuses `SubmissionRow`, `SUBMISSION_STATUS_LABELS/TONE`, `dueDateTime` and
`fileSize`; the only new contract is `SubmissionDetail`, which adds the
context a deep link lacks (which assignment, what it is out of, where the
student sits in the review queue).

**A 404, not a 403.** Every other guarded page in this app protects a
*section* and renders `PermissionDenied`. This URL is one named student's
work, marks and feedback, so `getSubmissionDetail()` returns nothing unless
the caller may review and the route 404s — the response is byte-identical to
a non-existent submission, so the URL space cannot be probed to discover who
has submitted. Verified for six unauthorised roles plus four malformed ids.

**`previousVersions` exists because §7.3 makes a resubmission a new row** —
`submissions` is UNIQUE on `(assignment_id, milestone_id, student_id,
version)`. A reviewer looking at v2 without v1's feedback cannot see what
they asked for, so the loop is invisible. Reconstructed from the current row
today, with a `TODO(Dev-B)` for the real versions endpoint.

**Score is validated in JS, not with native `min`/`max`** — the native
attributes suppress the form's own message and the field silently refuses to
submit. Approving requires a score; rejecting does not, because a rejection
legitimately carries none.

**Bugs fixed while here.**
1. **Client links dropped the `?role=` preview param**, so "Next to review"
   navigated as the default role and 404'd. Extracted `usePreviewHref()` —
   the same loop three shells had each grown privately — and applied it to
   this page and the new review-table link.
2. **Three pre-existing contrast failures on C-TC-15**: `text-success`
   (2.54:1) and `text-warning` (2.15:1) as 24px KPI values, `text-destructive`
   (3.76:1) on the 11px "· late" tag, and `muted-foreground` on the
   `bg-muted` avatar (4.34:1 — the colour *pair* again). All now use the
   darkened `-text` tokens.

---

## HOD department console — live API

C-HD-01…C-HD-12 are served from the authenticated `/hod/*` console and
`/api/v1/hod/*`; none of these pages reads fixture data. Every request first
resolves the HOD's active departments from `role_assignments.scope_id` / the
canonical `departments.hod_id` link, then applies that fence before grouping,
pagination or mutation.

| Task | Route | Capability |
|---|---|---|
| C-HD-01 | `/hod/dashboard` | Department attendance, results, assignments, notices and upcoming-exam KPIs |
| C-HD-02/03 | `/hod/attendance`, `/hod/attendance/report` | Class heatmap plus per-student/subject detail and CSV export |
| C-HD-04 | `/hod/examinations` | Department schedules and scoped CSV export, read-only |
| C-HD-05 | `/hod/assignments` | Department assignment/submission/review queue |
| C-HD-06 | `/hod/results` | Department class results and CSV export, read-only |
| C-HD-07 | `/hod/teachers` | View teaching load; assign or remove scoped teacher-subject links |
| C-HD-08 | `/hod/mentors` | Assign, reassign and remove mentor allocations |
| C-HD-09/10 | `/hod/notices`, `/hod/notices/new` | Institution feed plus department/class-only posting |
| C-HD-11 | `/hod/discussion` | Pin, unpin, lock, unlock and soft-delete department threads |
| C-HD-12 | `/hod/timetable` | Read-only timetables for department classes |

**Mentor integrity is in the database, not merely the UI.** `update2.sql`
section 10 / Alembic revision `e7f2a6c3b904` adds a partial unique index so one
student can have only one **active** mentor in an academic year. Reassignment
is transactional and preserves inactive history. The attendance threshold is
read from tenant settings when configured; the page does not invent one.

**HOD setup is reconciled automatically.** Selecting a department HOD creates
the matching scoped HOD role assignment. The migration backfills existing
`departments.hod_id` records, so legacy department heads do not lose access on
deployment.

---

## Leadership directories (Principal / Vice Principal)

C-PR-05, C-PR-06 and C-VP-07.

| Task | Page | Route |
|---|---|---|
| C-PR-05 | Staff Directory | `/principal/staff` |
| C-PR-06 | Student Directory | `/principal/students` |
| C-VP-07 | Staff Directory (VP) | `/vp/staff` |

**These are narrowings of the shared directory, not a second one.** `/users`
(PAGE 12) already gives leadership a merged `STAFF_AND_STUDENTS` list; the doc
asks for the same people split by kind. So all three routes pass a different
`DirectoryPermissions` preset into the *same* `getDirectoryData()` and the
*same* `DirectoryView`. No new list component, no new data layer, no second
search box to keep in sync.

The audience is still applied server-side: the staff directory's RSC payload
contains zero student rows, and vice versa — asserted, not assumed.

**Columns differ because the two halves need different ones.** A staff row has
no class; a student row has no designation. C-PR-06 names "class, enrollment
status", so `ENROLMENT_STATUS` was added as a real column reading
`student_enrollments.status` (§6.6) through `structure-data` — the same value
the enrolment board (C-IA-11) and class detail (C-IA-06) show. `Last login` is
deliberately **absent** from the staff list: that is an account-administration
signal (C-IA-08), and §4.3 gives the Principal academic authority only.

**Read-only by construction.** Every preset carries `actions:
["VIEW_PROFILE"]`; §4.3 grants the Principal no user-management rights, so
there is no edit, deactivate, reset-password or assign-roles control on any of
the three — verified against raw HTML, with the Admin's `/users` as a positive
control proving the probes fire.

**Deviations, flagged.**
1. **The Principal no longer sees `/users` in the sidebar.** They have the same
   people under two focused links; a third merged entry would be the same rows
   a third time. The Vice Principal **keeps** `/users`, because C-VP-07 gives
   them a staff page but no student one — dropping it would have silently
   removed access §4.3 grants them.
2. **C-VP-07 uses the same preset as C-PR-05.** The doc describes both as
   "view staff profiles" and §4.3's VP limits are about *delegated duties and
   result approval*, not staff visibility. The VP's real constraint is
   modelled on the results page, which already implements it.
3. **`DirectoryView` gained a `title` prop.** It hard-coded "Users", so the
   Student Directory announced itself as "Users" to a screen reader. Default
   unchanged, so `/users` is untouched.

---

## Institution structure (Institution Admin)

C-IA-02…07, C-IA-11 and C-IA-12 — the institution's skeleton, which every
other module hangs off.

| Task | Page | Route |
|---|---|---|
| C-IA-02 | Department Management | `/departments` |
| C-IA-03 | Department Detail | `/departments/:id` |
| C-IA-04 | Academic Year Setup | `/academic-years` |
| C-IA-05 | Class Management | `/classes` |
| C-IA-06 | Class Detail | `/classes/:id` |
| C-IA-07 | Subject Management | `/subjects` |
| C-IA-11 | Student Enrollment | `/enrollments` |
| C-IA-12 | Parent–Student Links | `/parent-links` |

**`lib/structure-data.ts` is now the single owner of departments, classes and
subjects.** They used to be re-typed in four files that disagreed: global
search listed **3** departments while the attendance report showed **6**, and
search named an HOD ("Rajesh Verma") who holds no HOD grant in
`role_assignments`. Everything is now derived from the module that owns the
underlying people — `getInstitutionSummary()` for departments and headcount,
`getStaffDirectory()` for staff and HODs, `getClassRoster()` for students,
`getAcademicYears()` for years, `getClassSlots()` for the timetable. ABC
College's 910 students still reconcile with the platform console.

**The database constraints are enforced in the UI, not discovered by the API.**
- `departments ←── classes.department_id` (§12): deleting a department with
  classes is *refused with a reason*, not offered and then 409'd.
- `classes` is UNIQUE on `(tenant_id, department_id, academic_year_id, code)` —
  a **composite**, so `SY-A` legitimately exists in both CSE and ECE.
  Validating on code alone would reject a correct entry.
- `subjects` is UNIQUE on `(tenant_id, class_id, code)` — scoped to the class.
- `teacher_subjects` is UNIQUE on `(teacher_id, subject_id, role_in_subject)`,
  so the same person can be Teacher *and* Co-teacher on one subject.
- `academic_years` has a partial unique index on `is_current` (§6.1), so
  making a year current is a **swap** — the dialog names the year it displaces.
- `max_strength` (§6.3) blocks a bulk enrolment *before* the request rather
  than letting the API half-write the batch.
- `passing_marks ≤ max_marks` (§6.4), validated in JS — a native `min`/`max`
  suppresses the form's own message.

**Vacancies are shown as work, not as missing data.** Four of six departments
have no HOD, five classes have no class teacher and six subjects have no
teacher — all real states (`hod_id` and `class_teacher_id` are nullable), and
all the thing these pages exist to fix. Inventing values would have hidden
every empty state the pages were built for.

**Read-only for the Principal and Vice Principal.** §4.3 grants
institution-wide visibility but not structural edit, so they get the data and
a "View only" chip with *no* create, edit, delete, assign or unlink control —
asserted against the raw server HTML across all 8 pages, with a positive
control proving the probes fire on the Admin's copy.

**Deviations, flagged.**
1. **C-IA-04 moved out of Settings.** An Academic Year section already existed
   inside `/settings`; it is now a read-only summary that links to
   `/academic-years` rather than carrying a second copy of the same form.
2. **C-IA-12 is school-only (§6.7)** and ABC College is a college, so the page
   *explains itself* instead of showing an empty table. `?tenantType=SCHOOL`
   previews the school case.
3. **Class enrolment counts show the named demo cohort** (10 students), while
   department totals are the institution's real 910. Both are stated on the
   page so "4/60" doesn't read as a bug.
4. **FY-A's subject list was aligned to the timetable.** The timetable module
   already scheduled Algorithms, Databases and Operating Systems for `fy-a`;
   attaching them to the second-year classes made the class detail page
   contradict itself. The older owner wins.

---

## Support Staff console

C-SP-01…04, under `app/(platform)/platform/support/`.

| Task | Page | Route |
|---|---|---|
| C-SP-01 | Support Dashboard | `/platform/support/dashboard` |
| C-SP-02 | Ticket List | `/platform/support/tickets` |
| C-SP-03 | Ticket Detail | `/platform/support/tickets/:id` |
| C-SP-04 | Institution Read-Only | `/platform/support/institutions/:id` |

**"Cannot modify institution data or settings" (§4.1) is enforced, not
implied.** C-SP-04 has no `<form>`, no `<input>`, no `<select>` and no
mutating button — asserted in the leak suite, not just intended. A support
agent *can* change a ticket, because `support_tickets` (§4.6) is a platform
row; they cannot change anything inside a tenant.

**C-SP-04 is a diagnostic snapshot, not impersonation.** Debugging a login
failure or a missing menu item needs configuration and health — plan, module
toggles, capacity, recent admin actions. It does not need student records,
marks or fee accounts, so none of them are in the payload. Verified by
grepping the raw HTML for 12 institution values; 0 present.

**Deviations, flagged.**
1. **`ticket_replies` does not exist in the schema.** §4.6 has no reply table,
   yet the assignment doc lists `POST /tickets/:id/reply` and C-SP-03 asks for
   a "reply thread". `TicketReply` is the shape that endpoint implies and is
   marked `TODO(Dev-A)` so the table gets added rather than the UI inventing
   it. It carries `is_internal`, because a support agent needs to record a
   diagnosis the customer shouldn't read.
2. **Routes are `/platform/support/*`, not the doc's `/support/*`.** `/support`
   is already the public login-help page (a C-PB task). Both now resolve. The
   dashboard sits at `/platform/support/dashboard`, matching the doc's own
   `/support/dashboard` under the platform prefix.
3. **No SLA is specified anywhere**, so `SLA_HOURS` lives in one table
   (4/12/48/96h by priority) rather than being scattered through the UI, with
   a TODO to move it into plan-based support tiers.
4. The Super Admin can also open this section — §4.1 gives them platform-wide
   oversight, and an escalated ticket has to be reachable.

---

## Sales Executive console

C-SL-01…04, under `app/(platform)/platform/sales/`.

| Task | Page | Route |
|---|---|---|
| C-SL-01 | Sales Dashboard | `/platform/sales/dashboard` |
| C-SL-02 | Trial Institutions | `/platform/sales/trials` |
| C-SL-03 | Convert Trial to Paid | `/platform/sales/trials/:id/convert` |
| C-SL-04 | Subscription Management | `/platform/sales/subscriptions` |

**"Cannot access institution academic data" (§4.1) is decided in the data
layer, not the component.** `toTrialRow()` and `toAccount()` in
`lib/sales-data.ts` are the only two places a tenant becomes a sales payload,
and they name every field that crosses. There is no path from this file to
student, mark, attendance, fee or audit data, so the RSC payload the browser
receives does not contain it — verified by grepping the raw server HTML of all
four pages against 19 probes, with three positive controls proving the probes
fire on the pages that *do* hold that data. Seats, teachers and storage **are**
included: those are the meters a plan is priced on.

**Nothing is re-seeded.** Trials, plans and subscriptions all come from
`lib/platform-data.ts`, so a trial the Sales console lists is the same tenant
row the Super Admin sees, at the same price, with the same headcount. ABC
College still reports the institution app's own 910 students.

**Plan fit has three levels, not two.** A *blocker* (over a seat, teacher or
storage cap) refuses the change — selling Standard to an institution with
2,400 students means their next enrolment fails. A *warning* (a module the
plan doesn't license) is acknowledged with a checkbox and proceeds, because
§4.1 grants "upgrade / **downgrade**" and every downgrade drops something;
collapsing warnings into blockers made downgrades impossible. *Notes* are
headroom. One `planFit()` serves both C-SL-03 and C-SL-04.

**Deviations, flagged.**
1. **`trial_notes` does not exist in the schema.** C-SL-02 asks for "follow-up
   notes" but §4 has nowhere to record a sales conversation. `TrialNote` is the
   shape the page implies, marked `TODO(Dev-A)`, and the UI says so in place
   rather than faking a composer. Same call made for `ticket_replies` (C-SP-03).
2. **`subscriptions` has no billing-cycle column.** §4.4 stores `starts_at` and
   `ends_at`; §4.1 prices both `price_monthly` and `price_yearly`. The cycle is
   therefore the *length of the period*, derived rather than stored, so it can
   never contradict the dates it describes.
3. **Conversion rate is read out of billing history**, not stored. A tenant
   whose TRIAL row is followed by a paid row converted; one with nothing after
   it lapsed — `tenants.trial_ends_at` goes NULL when a trial ends (§4.2), so
   §4.4 is the only place that history survives. Open trials are excluded:
   counting undecided leads as losses would make the number worse every time
   sales generated one.
4. **The urgency bands (3d critical / 7d soon) and the 45-day renewal window
   are conventions, not documented rules** — the doc gives only
   `trial_ends_at`. They live in one table in `lib/sales.ts` with a TODO to
   move them into platform settings, as `SLA_HOURS` did.
5. **Routes are `/platform/sales/*`**, matching the platform prefix the doc
   sets in §2 ("Next.js route prefix `app/(platform)/`") rather than a bare
   `/sales/*` on the tenant origin.

**MRR has one definition.** `tenantMrr()` in `lib/platform-data.ts` is used by
both the Super Admin dashboard and the Sales board, reading each tenant's real
cycle. Computing it locally in the sales layer booked ₹4,999 from a *suspended*
tenant while the platform overview correctly counted zero.

---

## Exam Controller console

C-EC-03…06, under `app/(institution)/exam-controller/`. The dashboard
(C-EC-01), schedule (C-EC-02), results (C-EC-07/08), grade cards (C-EC-09) and
reports (C-EC-10) are the shared pages the controller already reaches.

| Task | Page | Route |
|---|---|---|
| C-EC-03 | Create / Edit Exam Schedule | `/exam-controller/schedule/new` |
| C-EC-04 | Hall Allocation | `/exam-controller/halls` |
| C-EC-05 | Active Exams Monitor | `/exam-controller/monitor` |
| C-EC-06 | Malpractice Logs | `/exam-controller/malpractice` |

**Access (`examControlAccess()` in `lib/exam-control.ts`).** Exam Controller
and Institution Admin edit; Principal and Vice Principal read (§4.3 grants
"approve exam schedules", which needs the view but not the levers); every other
role is refused. The read-only state is threaded all the way to the buttons —
a `canEdit` the component ignores is worse than no flag at all, which is how a
Principal once got working Create/Edit/Delete on eight pages.

**Clash detection is the point of C-EC-03**, so it is a pure function
(`findScheduleClashes()`) with its own test rather than a check buried in the
form. Three kinds **block**: `CLASS_BUSY` (a cohort cannot sit two papers at
once), `ROOM_TAKEN`, and `PAST_DATE`. `INVIGILATOR_BUSY` only **warns** — a
controller legitimately double-books one invigilator across two adjacent halls,
and refusing that would model a rule the institution does not have.

**Everything is IST.** `<input type="date">` and `<input type="time">` return
a *wall-clock* value, so they go through `istToIso()` in `lib/utils.ts`. Pasting
them into a `` `${date}T${time}:00.000Z` `` template claimed the controller's
10:00 was 10:00 **UTC** — 15:30 IST — which slid every proposed exam 5½ hours
and let a genuine double-booking through the clash check reporting "no
clashes". `PAST_DATE` likewise compares `istDate()`, not `iso.slice(0, 10)`:
the UTC slice rolls back before 05:30 and rejected a 01:00 exam booked for
today.

**Deviations, flagged.**
1. **There is no `exam_halls` / rooms table.** §7.2 stores
   `exam_hall_allocations.room_no` as free text `VARCHAR(50)`, so nothing
   records that a hall exists, what it seats, or whether it is usable. Without
   a capacity the page cannot answer "do these rooms fit 45 candidates?", which
   is the whole task. `EXAM_ROOMS` in `lib/exam-control-data.ts` is the shape
   that table needs, marked `TODO(Dev-A)` — the same call made for
   `ticket_replies`, `trial_notes` and `mentor_assignments`.
2. **`ExamSummary.className` holds the class *code*** ("FY-A"), not
   `classes.name` ("FY-BSc-A"), so `resolveClassId()` joins on code + department
   before falling back to the name. Matching on the name alone silently found
   nothing and *every* class clash went undetected. Codes are only unique per
   department (§6.3's composite key) — `SY-A` exists in both CSE and ECE — so
   the department disambiguates.
3. **The auto-flag threshold (3 tab switches) and the 48-hour "starting soon"
   window are conventions, not documented rules.** They are two named constants
   in `lib/exam-control.ts` with a TODO to move them into institution settings,
   as `SLA_HOURS` did.
4. **C-EC-05's "if Mentor role enabled" analogue.** MENTOR and EXAM_CONTROLLER
   are *roles*, not module keys, so the gate is whether anyone holds the grant
   rather than a `modules` lookup.

**A student sees their own anti-cheat counter, and nothing else.** The exam
detail payload for a STUDENT carries exactly one `tabSwitchCount` — their own
attempt row (§7.2) — with `attempts`, `halls` and `malpractice` all empty. The
regression suite asserts the count is theirs *and* runs a positive control
proving the same probe finds all seven on the controller's payload, because a
probe that never fires passes every time.

---

## Academic Coordinator substitutions

C-AC-05 and C-AC-06, under `app/(institution)/coordinator/`. The dashboard
(C-AC-01), timetable builder / grid / conflict checker (C-AC-02…04), academic
calendar (C-AC-07) and notice composer (C-AC-08) are shared pages the
coordinator already reaches.

| Task | Page | Route |
|---|---|---|
| C-AC-05 | Substitution Management | `/coordinator/substitutions` |
| C-AC-06 | Add Substitution | `/coordinator/substitutions/new` |

**Access delegates to the timetable grant, it does not restate it.**
`substitutionAccess()` calls `timetablePermissions()` (PAGE 10) and reads
`canSubstitute`. A substitution *is* a timetable edit, so a second permission
table here would be one refactor away from disagreeing with the grid that
renders the same rows. That gives the Academic Coordinator the levers (§4.5 /
§6 — the only institution role with a build grant), read-only to everyone
holding a timetable view, and a refusal for roles whose view is `NONE`.
C-AC-06 additionally requires `canSubstitute`, so the form context — the
teacher list and the whole grid — is **never built** for a read-only role and
never reaches the browser.

**Clash detection is a pure function** (`findSubstitutionIssues()`) with its
own unit suite, not a check buried in the form. Five kinds **block**:
`ALREADY_COVERED` (violates `UNIQUE (slot_id, date)`, §7.8 — the insert would
fail at the database anyway), `SUBSTITUTE_BUSY` (they teach their own class
that period), `SAME_TEACHER`, `WRONG_DAY` (the slot's weekday doesn't match
the chosen date) and `PAST_DATE`. `HEAVY_LOAD` only **warns** — asking one
teacher to cover a third period is a judgement call a coordinator is entitled
to make on a bad morning, and refusing it would model a rule the institution
does not have.

**Dates are plain DATEs, compared as strings.** §7.8 stores `date DATE` with
no time, so `whenFor()` and the `PAST_DATE` check are string comparisons and
no `Date` is ever constructed — which is what makes them immune to the UTC
roll-back that shifted the exam scheduler by 5½ hours. `dowOf()` parses at UTC
midnight and reads `getUTCDay()` for the same reason.

**Deviations, flagged.**
1. **`timetable_substitutions.reason` has no FK to `leave_requests`.** The
   schema does not connect a substitution to *why* the teacher is away, so
   neither does this page — the reason is free text, as §7.8 defines it.
   Deriving "who is absent today" from the leave module would be inventing a
   join the database has not got. (The leave fixture also has nobody away
   today, so an "uncovered periods" panel would have been permanently empty —
   the fixture-state trap.)
2. **Substitute candidates are read off the timetable, not filtered by role.**
   The grid is the only place that knows a person actually takes classes;
   `getStaffDirectory()` still supplies department and designation so two
   names can be told apart.
3. **`HEAVY_COVER_LOAD = 2` is a convention, not a documented rule** — one
   named constant in `lib/coordinator.ts` with a TODO to move it into
   institution settings, as `SLA_HOURS` did.
4. **Only the Academic Coordinator gets the sidebar link.** Every other
   timetable role can reach the page but has nothing to do there, and a link
   to a read-only list would be noise in fifteen other sidebars.

**Two stubs became real.** The coordinator dashboard's "Add Substitution"
quick action pointed at `/timetable`, and the timetable builder's "Add
substitution" button only fired a placeholder alert. Both now navigate to
C-AC-06 through `usePreviewHref()`, so `?role=` survives the click.

**`Kpi` is now a shared primitive.** Five boards (hall, malpractice, monitor,
mentor, subscription) had each grown a private near-identical copy with its
own tone union and its own hand-rolled ternary chain. They are one
`components/dashboard/primitives.tsx` export taking `Tone`, coloured from the
AA-safe `TONE_TEXT` map.

---

## Librarian console + password reset

Built as one batch because both close **dead ends the app already pointed
at**, not because a role was next in the list. Evidence, measured: 24
quick-action buttons across 7 roles linked to their own dashboard, and
`/forgot-password` promised a reset link to a page that did not exist. See
`BUILD-PRIORITY.md` at the repo root for the full ranking.

| Task | Page | Route |
|---|---|---|
| C-PB-03 | Reset Password | `/reset-password?token=` |
| C-LB-02 | Book Catalogue | `/library/books` |
| C-LB-04 | Issue Book | `/library/issues/new` |
| C-LB-05 | Return Book | `/library/issues/:id/return` |
| C-LB-06 | Issued Books List | `/library/issues` |
| C-LB-07 | Overdue List | `/library/overdue` |
| C-LB-08 | E-Resources | `/library/e-resources` |

**C-LB-06 and C-LB-07 are one component.** "Overdue" is a *filter* over the
loans, not a separate query — two screens reading two sources would eventually
disagree about how many books are late. `/library/overdue` opens the same desk
on the overdue tab.

**Nothing was re-seeded.** `library-data.ts` already owned the catalogue,
copies and issue history feeding PAGE 24; the new pages add cross-title
accessors (`allLoans()`, `getCirculationDesk()`) built from the same
`buildIssues()` the book page uses, so a loan on the desk is byte-for-byte the
loan on the book page. Borrowers come from `getClassRoster()` and
`getStaffDirectory()`.

**Who sees borrower identity.** PAGE 24 gives "current borrowers" and "full
issue history" to the Librarian alone. The catalogue and e-resources are for
readers; the three circulation pages are not, so `LibraryPage requireManage`
refuses them — the roll numbers, accession numbers and fines never enter the
RSC payload. Verified by grepping raw server HTML for 7 roles × 5 routes, with
three positive controls proving the probes fire on the Librarian's payload.

**Deviations, flagged.**
1. **`LOAN_DAYS = 14`, `BORROW_LIMIT = 3`, `DUE_SOON_DAYS = 7` are
   conventions.** §8.1 stores `due_date` per loan but no doc gives a default
   term or a borrowing cap. Three named constants in `lib/library.ts` beside
   `FINE_PER_DAY`, with a TODO to move them to `tenant_settings`.
2. **A borrower at their limit only warns.** A librarian routinely lends one
   more while the late book is promised for tomorrow; refusing it would model
   a rule the institution has not got. Only `COPY_UNAVAILABLE` and
   `PAST_DUE_DATE` block.
3. **`verifyResetToken()` is a stub with a demo convention** — any token
   containing "expired" models the closed 30-minute window (§4.3
   `password_reset_expires`), so both dead-end states are reviewable without a
   backend.
4. **The return screen recomputes the fine** rather than reading
   `book_issues.fine_amount`, which is written when the loan starts and is
   stale the moment the book is late.

## Pre-existing bugs found and fixed this batch

- **All four auth pages had no `h1` on mobile.** The only `h1` lived in
  `BrandingPanel`, which is `hidden lg:flex` — so on a phone login,
  forgot-password and reset-password had zero headings. It was also a slogan
  rather than the page title. The slogan is now a `<p>` and each card heading
  is the `h1`.
- **Auth footer text was 2.45:1** (`#94A3B8` on `#F8FAFC`), far below AA for
  11px. Now `#475569` at **7.24:1**.
- **`Button` defaults to `w-full`** unless the caller passes an explicit
  width, so a submit beside a Cancel link wraps to its own full-width row.
  Fixed on the two new library forms and on C-AC-06, which had the same latent
  bug from last turn.
- **A library KPI pinned at zero.** `ACC-11890` was issued 6 days into a
  14-day loan, leaving "due this week" permanently at 0. Retimed to 8 days.
- **`LOAN_DAYS` was defined twice** — a private copy in `library-data.ts` and
  the new shared one. Consolidated.

---

## Link integrity

`npm run link-check` probes every page for all 18 roles **and crawls every
anchor the app actually renders**, comparing each outcome against the app's own
permission tables. `--md` regenerates `TEST-LINKS.md`.

The crawl matters: an earlier version checked only a hand-written page list and
reported "0 broken" while 55 rendered links were 404ing — including all seven
module hubs, which the sidebar shows to every role. Current state: **832 links
checked, 0 broken.**

---

## Design tokens

The 4-colour system lives in **`tailwind.config.ts`** and **`app/globals.css`**
(both from §3), so all 15 modules stay consistent. Prefer the semantic classes
over raw hex:

| Token | Class | Hex |
|---|---|---|
| Primary | `bg-primary` / `text-primary` | `#0F172A` |
| Accent | `bg-accent`, `hover:bg-accent-hover` | `#4F46E5` → `#4338CA` |
| Accent light | `bg-accent-light` | `#EEF2FF` |
| Secondary | `bg-secondary` | `#06B6D4` |
| Muted text | `text-muted-foreground` | `#64748B` |
| Card | `rounded-card shadow-card` | 16px · soft shadow |
| Field | `rounded-field` | 10px |

Reusable pieces: `components/ui/button.tsx`, `components/ui/text-field.tsx`,
`components/auth/form-alert.tsx`.

---

## Accessibility (§10 — verified)

Checked in a real browser, not by eye:

- Tab order: email → password → Forgot? → remember → Sign in
- Enter submits the form
- 3px indigo focus ring, plus a global `:focus-visible` ring
- Every input has a bound `<label>` and correct `autocomplete`
- Errors linked via `aria-describedby` + `aria-invalid`; alerts use `role="alert"`
- Password toggle has an `aria-label` that flips with state, and is skipped in
  tab order (the field itself is the control)
- Loading state sets `aria-busy` and disables the button (no double submit)
- Contrast measured: `#0F172A` on white **17.85:1** (AAA); white on `#4F46E5`
  **6.29:1** (AA); both meet or beat the doc's estimates
- Renders cleanly at 320 / 390 / 768 / 1440 px
- `prefers-reduced-motion` respected

---

## Deviations from the docs

1. **Next.js version** — see the note at the top.
2. **Tab order** — the login doc's sample markup puts "Forgot?" in the label
   row, which tabs *between* email and password. It's positioned absolutely
   instead: visually identical, correct focus order.
3. **Roll-number field** — `type="text"` (not `email`), since the field accepts
   `ROLL123`. Validation is length-based, not email-shaped.
4. **`components/` at app root** — matches the docs' `apps/web/components/...`
   paths rather than nesting inside `app/`.
5. **Vice Principal has its own slug** — the login doc pointed both `PRINCIPAL`
   and `VICE_PRINCIPAL` at `/principal/dashboard`, which made the VP's
   delegated read-only view (§5.3) unreachable. VP is now
   `/vp/dashboard`.
6. **Role set is the canonical 18** — `InstitutionRole` matches
   `role_based_system_design.md` §2.2 and `packages/shared-types/roles.ts`
   exactly, including `MENTOR`. `DASHBOARDS` is typed
   `Record<InstitutionRole, DashboardConfig>`, so adding a role without a
   dashboard fails the build.
7. **One dynamic route, not 18 pages** — the doc's §9 suggests a file per role
   under `(institution)/[role]/dashboard/`. A single dynamic route driven by
   configs gives the same URLs with no duplicated layout code; all role params
   are pre-rendered via `generateStaticParams`. This is also what
   `role_based_shared_pages.md` asks for: one URL, role-switched view.
8. **Nav is built client-side** — the shell computes its own nav from
   `(role, enabledModules)` because Lucide icon components can't be passed
   across the server→client boundary as props.
9. **Tone text colours are the darkened variants** — `TONE_TEXT` now maps to
   `text-success-text` (#047857) / `text-warning-text` (#B45309) /
   `text-destructive-text` (#B91C1C) / `text-secondary-text` (#0E7490). The
   brand hexes are 2.15–3.76:1 on white and fail WCAG AA as text; they remain
   in `TONE_FILL` / `TONE_BG` where they are shapes. This fixed 32 pre-existing
   contrast failures across the 18 dashboards as well.
10. **`role_assignments.is_active` survives deactivation** — it is
   `users.is_active` (§5.5) that stops sign-in, so a deactivated account
   keeps its role grants and the directory greys the chips rather than
   dropping them. Conflating the two made a deactivated person appear to hold
   no roles, contradicting the deactivate dialog's own promise.
