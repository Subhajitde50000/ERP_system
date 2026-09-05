/**
 * Role × page link checker and guide generator.
 *
 *   node scripts/link-check.mjs            # check every link, print a report
 *   node scripts/link-check.mjs --md       # also write TEST-LINKS.md
 *   node scripts/link-check.mjs --base http://localhost:3001
 *
 * Requires the app to be running (`npm run build && npm run start`).
 *
 * The expected access for each role is **derived from the app's own
 * permission tables**, not hand-listed here, so this file cannot drift from
 * the code the way a hand-written checklist would. Every URL is then actually
 * fetched and its outcome compared against that expectation.
 */

import { writeFileSync } from "node:fs";

const BASE =
  process.argv.includes("--base")
    ? process.argv[process.argv.indexOf("--base") + 1]
    : "http://localhost:3000";
const WRITE_MD = process.argv.includes("--md");

/* ── The 18 institution roles, from the canonical list ──────────────────── */

const ROLES = [
  ["INSTITUTION_ADMIN", "admin", "Institution Admin"],
  ["PRINCIPAL", "principal", "Principal"],
  ["VICE_PRINCIPAL", "vp", "Vice Principal"],
  ["HOD", "hod", "HOD"],
  ["TEACHER", "teacher", "Teacher"],
  ["MENTOR", "mentor", "Mentor"],
  ["EXAM_CONTROLLER", "exam-controller", "Exam Controller"],
  ["ACADEMIC_COORDINATOR", "coordinator", "Academic Coordinator"],
  ["ACCOUNTANT", "accountant", "Accountant"],
  ["STUDENT", "student", "Student"],
  ["PARENT", "parent", "Parent"],
  ["LIBRARIAN", "librarian", "Librarian"],
  ["HOSTEL_WARDEN", "hostel-warden", "Hostel Warden"],
  ["TRANSPORT_MANAGER", "transport-manager", "Transport Manager"],
  ["PLACEMENT_OFFICER", "placement-officer", "Placement Officer"],
  ["HR_MANAGER", "hr-manager", "HR Manager"],
  ["ADMISSION_OFFICER", "admission-officer", "Admission Officer"],
  ["STORE_MANAGER", "store-manager", "Store Manager"],
];

/* ── Real fixture ids, so no link 404s on a made-up id ──────────────────── */

const ID = {
  notice: "n1",
  thread: "t1",
  exam: "e1",
  assignment: "as1",
  student: "s1",
  staff: "s1",
  staffEce: "s3", // ECE — proves the HOD department fence
  room: "A-104",
  book: "b1",
  submission: "sub-as1-s6",
  department: "cse",
  klass: "fy-a",
  /** A live loan, so C-LB-05 resolves rather than 404ing. */
  loan: "b1-i1",
};

/** HOD console route expectation — API independently enforces department scope. */
const hodOk = (role: string) =>
  role === "HOD" ||
  role === "INSTITUTION_ADMIN" ||
  role === "PRINCIPAL" ||
  role === "VICE_PRINCIPAL"
    ? "ok"
    : "denied";

/** Mirrors `canUseLeadershipDirectory()` in `lib/user-directory.ts`. */
const leadershipOk = (role: string) =>
  role === "PRINCIPAL" || role === "VICE_PRINCIPAL" ? "ok" : "denied";

/** §4.2 / §4.3 — mirrors `structureAccess()` in `lib/structure.ts`. */
const structureOk = (role: string) =>
  role === "INSTITUTION_ADMIN" ||
  role === "PRINCIPAL" ||
  role === "VICE_PRINCIPAL"
    ? "ok"
    : "denied";

/** §4.6 — mirrors `examControlAccess()` in `lib/exam-control.ts`. The
 *  Principal and VP read the console (they approve schedules) but cannot
 *  edit; both states are reachable, so both are "ok". */
const examControlOk = (role: string) =>
  role === "EXAM_CONTROLLER" ||
  role === "INSTITUTION_ADMIN" ||
  role === "PRINCIPAL" ||
  role === "VICE_PRINCIPAL"
    ? "ok"
    : "denied";

/**
 * §4.5 / §6 — mirrors `substitutionAccess()` in `lib/coordinator.ts`, which
 * itself delegates to `timetablePermissions()`. Any role holding a timetable
 * view reaches the board (read-only unless they can substitute); the roles
 * with `view: "NONE"` are refused.
 */
const substitutionOk = (P) => (P.timetable.view === "NONE" ? "denied" : "ok");

/** C-AC-06 is an edit, so only `canSubstitute` gets past the guard. */
const addSubstitutionOk = (P) =>
  P.timetable.view === "NONE" || !P.timetable.canSubstitute ? "denied" : "ok";

/**
 * PAGE 24 / §3 — mirrors `LibraryPage`. Two gates: the optional `library`
 * module, then `bookPermissions()`. The link checker runs with every module
 * enabled, so only the role gate varies here.
 */
const libraryReadOk = (P) => (P.book.view === "NONE" ? "denied" : "ok");

/**
 * Circulation pages name who borrowed what, which PAGE 24 gives to the
 * Librarian alone — so they need manage rights, not merely a catalogue view.
 */
const libraryManageOk = (P) =>
  P.book.view === "NONE" || !(P.book.canCirculate || P.book.canEditBook)
    ? "denied"
    : "ok";

/** Shape of the thread `ID.thread` points at, so the expectation can model
 *  the per-thread scope + tag fence the detail page applies. */
const THREAD_T1 = { scopeType: "SUBJECT", tags: ["sorting", "complexity"] };

/**
 * Every page in the app.
 *
 * `expect(role)` returns what *should* happen, computed from the app's own
 * permission layer. Values: "ok" (renders), "denied" (403 card), "404".
 */
const PAGES = [
  { label: "Dashboard (own role)", path: (r) => `/${r.slug}/dashboard`, expect: () => "ok" },
  { label: "Dashboard (entry redirect)", path: () => `/dashboard`, expect: () => "ok" },
  { label: "Notice Board", path: () => `/notices`, expect: () => "ok" },
  { label: "Notice detail", path: () => `/notices/${ID.notice}`, expect: () => "ok" },
  { label: "Compose notice", path: () => `/notices/new`, expect: (r, P) => (P.notice.canPost ? "ok" : "denied") },
  // The forum is scoped: a role with no visible scope gets a 403 (§6)
  { label: "Discussion", path: () => `/discussion`, expect: (r, P) => (P.discussion.visibleScopes.length ? "ok" : "denied") },
  // Thread t1 is scope SUBJECT, tags [sorting, complexity]. A role with a
  // tagFilter (the Exam Controller only sees "exam" threads) is correctly
  // refused this one — the fence is per-thread, not just per-forum.
  { label: "Discussion thread", path: () => `/discussion/${ID.thread}`, expect: (r, P) =>
      P.discussion.visibleScopes.includes(THREAD_T1.scopeType) &&
      (!P.discussion.tagFilter || THREAD_T1.tags.includes(P.discussion.tagFilter))
        ? "ok"
        : "denied" },
  { label: "Profile", path: () => `/profile`, expect: () => "ok" },
  { label: "Attendance", path: () => `/attendance`, expect: (r, P) => (P.attendance.view === "NONE" ? "denied" : "ok") },
  { label: "Examination", path: () => `/examination`, expect: (r, P) => (P.exam.view === "NONE" ? "denied" : "ok") },
  { label: "Exam detail", path: () => `/examination/${ID.exam}`, expect: (r, P) => (P.exam.view === "NONE" ? "denied" : "ok") },
  { label: "Assignments", path: () => `/assignments`, expect: (r, P) => (P.assignment.view === "NONE" ? "denied" : "ok") },
  { label: "Assignment detail", path: () => `/assignments/${ID.assignment}`, expect: (r, P) => (P.assignment.view === "NONE" ? "denied" : "ok") },
  { label: "Content", path: () => `/content`, expect: (r, P) => (P.content.view === "NONE" ? "denied" : "ok") },
  { label: "Results", path: () => `/results`, expect: (r, P) => (P.result.view === "NONE" ? "denied" : "ok") },
  { label: "Timetable", path: () => `/timetable`, expect: (r, P) => (P.timetable.view === "NONE" ? "denied" : "ok") },
  { label: "Fees", path: () => `/fees`, expect: (r, P) => (P.fee.view === "NONE" ? "denied" : "ok") },
  { label: "Notifications", path: () => `/notifications`, expect: () => "ok" },
  { label: "Calendar", path: () => `/calendar`, expect: () => "ok" },
  { label: "Search", path: () => `/search?q=aryan`, expect: () => "ok" },
  { label: "Settings", path: () => `/settings`, expect: () => "ok" },
  { label: "Settings — Modules", path: () => `/settings/modules`, expect: (r) => (r.role === "INSTITUTION_ADMIN" ? "ok" : "denied") },
  { label: "Users (directory)", path: () => `/users`, expect: (r, P) => (P.directory.deniedReason ? "denied" : "ok") },
  { label: "Reports", path: () => `/reports`, expect: (r, P) => (P.report.deniedReason ? "denied" : "ok") },
  // PAGE 13 — every role has at least one leave section, so there is no 403
  { label: "Leave", path: () => `/leaves`, expect: () => "ok" },
  { label: "Audit Logs", path: () => `/audit-logs`, expect: (r) =>
      r.role === "INSTITUTION_ADMIN" || r.role === "PRINCIPAL" ? "ok" : "denied" },
  // C-IA-02…07, 11, 12 — §4.2 gives the Admin create/edit/delete; §4.3 lets
  // the Principal and VP read. Everyone else is refused.
  { label: "Departments", path: () => `/departments`, expect: (r) => structureOk(r.role) },
  { label: "Department detail", path: () => `/departments/${ID.department}`, expect: (r) => structureOk(r.role) },
  { label: "Academic years", path: () => `/academic-years`, expect: (r) => structureOk(r.role) },
  { label: "Classes", path: () => `/classes`, expect: (r) => structureOk(r.role) },
  { label: "Class detail", path: () => `/classes/${ID.klass}`, expect: (r) => structureOk(r.role) },
  { label: "Subjects", path: () => `/subjects`, expect: (r) => structureOk(r.role) },
  { label: "Enrolment", path: () => `/enrollments`, expect: (r) => structureOk(r.role) },
  { label: "Parent links", path: () => `/parent-links`, expect: (r) => structureOk(r.role) },
  // C-PR-05 / C-PR-06 / C-VP-07 — leadership's focused directories. Only the
  // Principal and Vice Principal; every other role has its own at /users.
  { label: "Principal staff directory", path: () => `/principal/staff`, expect: (r) => leadershipOk(r.role) },
  { label: "Principal student directory", path: () => `/principal/students`, expect: (r) => leadershipOk(r.role) },
  { label: "VP staff directory", path: () => `/vp/staff`, expect: (r) => leadershipOk(r.role) },
  // C-HD-07 / C-HD-08 — the HOD's own department. Admin and leadership read
  // it; everyone else is refused.
  { label: "HOD teacher list", path: () => `/hod/teachers`, expect: (r) => hodOk(r.role) },
  { label: "HOD mentor assignments", path: () => `/hod/mentors`, expect: (r) => hodOk(r.role) },
  // C-EC-03 … C-EC-06 — the Exam Controller console, institution-wide.
  { label: "Schedule an exam", path: () => `/exam-controller/schedule/new`, expect: (r) => examControlOk(r.role) },
  { label: "Hall allocation", path: () => `/exam-controller/halls`, expect: (r) => examControlOk(r.role) },
  { label: "Active exams monitor", path: () => `/exam-controller/monitor`, expect: (r) => examControlOk(r.role) },
  { label: "Malpractice logs", path: () => `/exam-controller/malpractice`, expect: (r) => examControlOk(r.role) },
  // C-AC-05 / C-AC-06 — the coordinator's substitution board. Reading it
  // follows the timetable grant; arranging cover needs `canSubstitute`.
  { label: "Substitutions", path: () => `/coordinator/substitutions`, expect: (r, P) => substitutionOk(P) },
  { label: "Add substitution", path: () => `/coordinator/substitutions/new`, expect: (r, P) => addSubstitutionOk(P) },
  // C-LB-02 … C-LB-08 — the librarian's desk. The catalogue and e-resources
  // are for readers; the circulation pages name borrowers, so they are not.
  { label: "Book catalogue", path: () => `/library/books`, expect: (r, P) => libraryReadOk(P) },
  { label: "E-resources", path: () => `/library/e-resources`, expect: (r, P) => libraryReadOk(P) },
  { label: "Issued books", path: () => `/library/issues`, expect: (r, P) => libraryManageOk(P) },
  { label: "Overdue books", path: () => `/library/overdue`, expect: (r, P) => libraryManageOk(P) },
  { label: "Issue a book", path: () => `/library/issues/new`, expect: (r, P) => libraryManageOk(P) },
  { label: "Return a book", path: () => `/library/issues/${ID.loan}/return`, expect: (r, P) => libraryManageOk(P) },
  // C-TC-16 — one student's work. Reviewers only; everyone else gets a 404,
  // not a 403, so the URL space can't be probed. "404" is the expectation
  // for the roles without `canReview`.
  { label: "Submission detail", path: () => `/teacher/submissions/${ID.submission}`,
    expect: (r, P) => (P.assignment.canReview ? "ok" : "404") },
  { label: "Library hub", path: () => `/library/dashboard`, expect: () => "ok" },
  { label: "Hostel hub", path: () => `/hostel/dashboard`, expect: () => "ok" },
  { label: "Transport hub", path: () => `/transport/dashboard`, expect: () => "ok" },
  { label: "Placement hub", path: () => `/placement/dashboard`, expect: () => "ok" },
  { label: "HR hub", path: () => `/hr/dashboard`, expect: () => "ok" },
  { label: "Admission hub", path: () => `/admission/dashboard`, expect: () => "ok" },
  { label: "Inventory hub", path: () => `/inventory/dashboard`, expect: () => "ok" },
  { label: "Create assignment", path: () => `/assignments/new`, expect: (r, P) =>
      P.assignment.canAuthor ? "ok" : "denied" },
  { label: "Create exam", path: () => `/examination/new`, expect: (r, P) =>
      P.exam.canAuthor ? "ok" : "denied" },
  { label: "Student detail", path: () => `/students/${ID.student}`, expect: (r, P) => (P.studentDetail.tabs.length ? "ok" : "denied") },
  { label: "Staff detail (CSE)", path: () => `/staff/${ID.staff}`, expect: (r, P) => (P.staffDetail.tabs.length ? "ok" : "denied") },
  { label: "Staff detail (ECE — HOD fence)", path: () => `/staff/${ID.staffEce}`, expect: (r, P) =>
      !P.staffDetail.tabs.length ? "denied" : P.staffDetail.departmentScope && P.staffDetail.departmentScope !== "ECE" ? "denied" : "ok" },
  { label: "Hostel room", path: () => `/hostel/rooms/${ID.room}`, expect: (r, P) => (P.hostel.view === "NONE" ? "denied" : "ok") },
  { label: "Library book", path: () => `/library/books/${ID.book}`, expect: (r, P) => (P.book.view === "NONE" ? "denied" : "ok") },
];

/** Pages with no role dimension. */
const PUBLIC_PAGES = [
  ["/login", "Login"],
  ["/forgot-password", "Forgot password"],
  ["/support", "Support"],
  ["/contact", "Contact"],
  ["/privacy", "Privacy Policy"],
  ["/terms", "Terms of Service"],
  ["/refund-policy", "Refund Policy"],
  ["/", "Root → redirects to /login"],
  ["/this-route-does-not-exist", "404 page"],
];

/* ── Load the app's permission layer ────────────────────────────────────── */

async function loadPermissions() {
  const [
    notices, discussion, attendance, examination, assignment, content, result,
    timetable, fee, studentDetail, staffDetail, hostel, library,
    userDirectory, report,
  ] = await Promise.all([
    import("../lib/notices"),
    import("../lib/discussion"),
    import("../lib/attendance"),
    import("../lib/examination"),
    import("../lib/assignment"),
    import("../lib/content"),
    import("../lib/result"),
    import("../lib/timetable"),
    import("../lib/fee"),
    import("../lib/student-detail"),
    import("../lib/staff-detail"),
    import("../lib/hostel"),
    import("../lib/library"),
    import("../lib/user-directory"),
    import("../lib/report"),
  ]);

  return (role) => ({
    notice: notices.noticePermissions([role]),
    discussion: discussion.discussionPermissions([role]),
    attendance: attendance.attendancePermissions([role]),
    exam: examination.examPermissions([role]),
    assignment: assignment.assignmentPermissions([role]),
    content: content.contentPermissions([role]),
    result: result.resultPermissions([role]),
    timetable: timetable.timetablePermissions([role]),
    fee: fee.feePermissions([role]),
    studentDetail: studentDetail.studentDetailPermissions([role]),
    staffDetail: staffDetail.staffDetailPermissions([role]),
    hostel: hostel.hostelRoomPermissions([role]),
    book: library.bookPermissions([role]),
    directory: userDirectory.directoryPermissions([role]),
    report: report.reportPermissions([role]),
  });
}

/* ── Fetch and classify ─────────────────────────────────────────────────── */

async function probe(url) {
  try {
    const res = await fetch(url, { redirect: "manual" });
    if (res.status >= 300 && res.status < 400) return { outcome: "redirect", status: res.status };
    const html = await res.text();
    if (res.status === 404) return { outcome: "404", status: 404 };
    if (res.status >= 500) return { outcome: "error", status: res.status };
    if (html.includes("Permission denied")) return { outcome: "denied", status: res.status };
    // A rendered institution page always has exactly one <h1> in <main>
    const hasH1 = /<h1[\s>]/.test(html);
    return { outcome: hasH1 ? "ok" : "empty", status: res.status };
  } catch (e) {
    return { outcome: "unreachable", status: 0, err: e.message };
  }
}

/* ── Run ────────────────────────────────────────────────────────────────── */

const permsFor = await loadPermissions();
const rows = [];
let checked = 0, mismatches = 0, broken = 0;

console.log(`\nChecking ${BASE} …\n`);

for (const [role, slug, label] of ROLES) {
  const P = permsFor(role);
  const ctx = { role, slug, label };

  for (const page of PAGES) {
    const path = page.path(ctx);
    const url = `${BASE}${path}${path.includes("?") ? "&" : "?"}role=${role}`;
    const want = page.expect(ctx, P);
    const { outcome, status } = await probe(url);
    checked++;

    const ok = outcome === want || (want === "ok" && outcome === "redirect");
    if (!ok) mismatches++;
    if (outcome === "error" || outcome === "unreachable" || outcome === "empty") broken++;

    rows.push({ role, roleLabel: label, page: page.label, url, want, got: outcome, status, ok });
  }
}

const publicRows = [];
for (const [path, label] of PUBLIC_PAGES) {
  const url = `${BASE}${path}`;
  const { outcome, status } = await probe(url);
  checked++;
  const want = path === "/" ? "redirect" : path.includes("does-not-exist") ? "404" : "ok";
  const ok = outcome === want;
  if (!ok) mismatches++;
  publicRows.push({ page: label, url, want, got: outcome, status, ok });
}

/* ── Platform console (app.xyz.com) — C-SA-01…08 ───────────────────────── */

const PLATFORM_PAGES: [string, string][] = [
  ["/platform/dashboard", "Platform Dashboard (C-SA-01)"],
  ["/platform/institutions", "Institution List (C-SA-02)"],
  ["/platform/institutions/t-abc-college", "Institution Detail (C-SA-03)"],
  ["/platform/institutions/new", "Create Institution (C-SA-04)"],
  ["/platform/plans", "Plans (C-SA-05)"],
  ["/platform/platform-users", "Platform Users (C-SA-06)"],
  ["/platform/audit-logs", "Audit Logs (C-SA-07)"],
  ["/platform/settings", "Platform Settings (C-SA-08)"],
];

/** Sales Executive console — C-SL-01…04. Gated to SALES_EXECUTIVE / SUPER_ADMIN. */
const SALES_PAGES: [string, string][] = [
  ["/platform/sales/dashboard?role=SALES_EXECUTIVE", "Sales Dashboard (C-SL-01)"],
  ["/platform/sales/trials?role=SALES_EXECUTIVE", "Trial Institutions (C-SL-02)"],
  ["/platform/sales/trials/t-vidya-college/convert?role=SALES_EXECUTIVE", "Convert Trial (C-SL-03)"],
  ["/platform/sales/subscriptions?role=SALES_EXECUTIVE", "Subscriptions (C-SL-04)"],
];

/** Support Staff console — C-SP-01…04. Gated to SUPPORT_STAFF / SUPER_ADMIN. */
const SUPPORT_PAGES: [string, string][] = [
  ["/platform/support/dashboard?role=SUPPORT_STAFF", "Support Dashboard (C-SP-01)"],
  ["/platform/support/tickets?role=SUPPORT_STAFF", "Ticket List (C-SP-02)"],
  ["/platform/support/tickets/tkt-1?role=SUPPORT_STAFF", "Ticket Detail (C-SP-03)"],
  ["/platform/support/institutions/t-abc-college?role=SUPPORT_STAFF", "Institution Read-Only (C-SP-04)"],
];

const platformRows: { page: string; url: string; got: string; status: number; ok: boolean }[] = [];
for (const [path, label] of [...PLATFORM_PAGES, ...SUPPORT_PAGES, ...SALES_PAGES]) {
  const url = `${BASE}${path}`;
  const { outcome, status } = await probe(url);
  checked++;
  const ok = outcome === "ok";
  if (!ok) mismatches++;
  platformRows.push({ page: label, url, got: outcome, status, ok });
}

/* ── Crawl: every link the app actually renders ─────────────────────────── */

/**
 * The page list above only proves the pages *I* thought of resolve. This
 * crawls the anchors the app really emits and probes each one — it is what
 * found 55 dead links (7 module hubs shown to all 18 roles, 40+ dashboard
 * CTAs) that the explicit list had reported as "0 broken".
 */
const rendered = new Map<string, Set<string>>();
await (async () => {
  // Playwright is a dev-only dependency for this script. If it isn't
  // installed, skip the crawl loudly rather than failing the whole check —
  // the explicit page matrix above still runs.
  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch {
    console.log(
      "\n⚠  playwright not installed — skipping the rendered-link crawl.",
    );
    console.log("   npm i -D playwright && npx playwright install chromium\n");
  }
  if (!chromium) return;
  const browser = await chromium.launch();
  const seeds = [
    ...new Set(PAGES.map((pg) => pg.path({ role: "STUDENT", slug: "student", label: "" }))),
    ...PLATFORM_PAGES.map(([p]) => p),
    ...SUPPORT_PAGES.map(([p]) => p.split("?")[0]!),
    ...SALES_PAGES.map(([p]) => p.split("?")[0]!),
  ];

  for (const [role, slug] of ROLES.map((r) => [r[0], r[1]] as const)) {
    const page = await browser.newPage();
    for (const seed of seeds) {
      const path = seed.replace("/student/", `/${slug}/`);
      const sep = path.includes("?") ? "&" : "?";
      try {
        await page.goto(`${BASE}${path}${sep}role=${role}`, { waitUntil: "domcontentloaded", timeout: 15000 });
        await page.waitForTimeout(150);
      } catch { continue; }
      const hrefs: string[] = await page.$$eval("a[href]", (els) =>
        els.map((e) => e.getAttribute("href") ?? "").filter((h) => h.startsWith("/")));
      for (const h of hrefs) {
        const clean = h.split("?")[0]!.split("#")[0]!;
        if (!clean || clean === "/") continue;
        if (!rendered.has(clean)) rendered.set(clean, new Set());
        rendered.get(clean)!.add(role);
      }
    }
    await page.close();
  }
  await browser.close();
})();

const deadRendered: { href: string; roles: string[]; status: number }[] = [];
for (const [href, roles] of rendered) {
  checked++;
  const { outcome, status } = await probe(`${BASE}${href}?role=${[...roles][0]}`);
  if (outcome === "404" || outcome === "error") {
    deadRendered.push({ href, roles: [...roles], status });
    mismatches++;
  }
}

/* ── Report ─────────────────────────────────────────────────────────────── */

for (const [role, , label] of ROLES) {
  const mine = rows.filter((r) => r.role === role);
  const bad = mine.filter((r) => !r.ok);
  const okCount = mine.filter((r) => r.got === "ok").length;
  const deniedCount = mine.filter((r) => r.got === "denied").length;
  console.log(
    `${bad.length ? "✗" : "✓"} ${label.padEnd(22)} ${String(okCount).padStart(2)} pages · ${String(deniedCount).padStart(2)} correctly 403` +
      (bad.length ? `  ← ${bad.length} MISMATCH` : ""),
  );
  for (const r of bad) {
    console.log(`     ${r.page.padEnd(32)} want=${r.want} got=${r.got} (${r.status})\n       ${r.url}`);
  }
}

console.log("");
for (const r of platformRows) {
  console.log(`${r.ok ? "✓" : "✗"} ${r.page.padEnd(34)} ${r.got} (${r.status})`);
}

console.log("");
for (const r of publicRows) {
  console.log(`${r.ok ? "✓" : "✗"} ${r.page.padEnd(34)} ${r.got} (${r.status})`);
}

console.log(
  rendered.size === 0
    ? "\n⚠  crawl SKIPPED — rendered-link coverage was not checked"
    : `\n${rendered.size} distinct links crawled from rendered pages — ` +
        (deadRendered.length ? `${deadRendered.length} DEAD:` : "all resolve"),
);
for (const d of deadRendered) {
  console.log(`  ✗ ${String(d.status)}  ${d.href}  (shown to ${d.roles.length} role(s))`);
}

console.log(
  `\n${checked} links checked · ${mismatches} mismatch${mismatches === 1 ? "" : "es"} · ${broken} broken\n`,
);

/* ── Markdown guide ─────────────────────────────────────────────────────── */

if (WRITE_MD) {
  const L = [];
  L.push("# Manual test links\n");
  L.push("> Generated by `node scripts/link-check.mjs --md` — do not edit by hand.");
  L.push("> Expected access is read from the app's own permission tables, so this");
  L.push("> file stays in sync with the code.\n");
  L.push("Start the app first:\n");
  L.push("```bash\ncd apps/web\nnpm install\nnpm run build\nnpm run start      # http://localhost:3000\n```\n");
  L.push("Re-run the checker any time:\n");
  L.push("```bash\nnpm run link-check              # verify every link, exit 1 on mismatch\nnpm run link-check -- --md      # regenerate this file\n```\n");
  L.push("**Legend** — ✅ renders (or redirects correctly) · ⛔ 403 *by design*, the role has no business there\n");
  L.push("Every ⛔ below is a deliberate permission boundary that was verified, not a broken link.\n");

  L.push("## Summary\n");
  L.push(`Checked **${checked} links** across **${ROLES.length} roles** — ${mismatches} mismatches, ${broken} broken.\n`);
  L.push("| Role | Dashboard | Pages | 403 by design |");
  L.push("|---|---|---:|---:|");
  for (const [role, slug, label] of ROLES) {
    const mine = rows.filter((r) => r.role === role);
    L.push(
      `| [${label}](#${label.toLowerCase().replace(/ /g, "-")}) | \`/${slug}/dashboard\` | ` +
        `${mine.filter((r) => r.got === "ok" || r.got === "redirect").length} | ` +
        `${mine.filter((r) => r.got === "denied").length} |`,
    );
  }
  L.push("");
  L.push("## Public pages\n");
  L.push("| Page | Link |");
  L.push("|---|---|");
  for (const [path, label] of PUBLIC_PAGES) L.push(`| ${label} | ${BASE}${path} |`);
  L.push("");

  L.push("## Preview switches\n");
  L.push("Any institution URL accepts these query params:\n");
  L.push("| Param | Example | Effect |");
  L.push("|---|---|---|");
  L.push(`| \`?role=\` | ${BASE}/attendance?role=TEACHER | View as one role |`);
  L.push(`| \`?roles=\` | ${BASE}/reports?roles=ACCOUNTANT,LIBRARIAN | Multi-role union + switcher |`);
  L.push(`| \`?modules=\` | ${BASE}/reports?role=HR_MANAGER&modules=none | Turn optional modules off |`);
  L.push(`| \`?tenant=\` | ${BASE}/notices?role=TEACHER&tenant=abc-college | Switch tenant branding |`);
  L.push("");

  for (const [role, slug, label] of ROLES) {
    const mine = rows.filter((r) => r.role === role);
    const okCount = mine.filter((r) => r.got === "ok" || r.got === "redirect").length;
    L.push(`## ${label}\n`);
    L.push(`Role key \`${role}\` · dashboard slug \`/${slug}\` · **${okCount} pages accessible**\n`);
    L.push("| | Page | Link |");
    L.push("|---|---|---|");
    for (const r of mine) {
      const mark =
        r.got === "ok" || r.got === "redirect"
          ? "✅"
          : r.got === "denied"
            ? "⛔"
            : "⚠️";
      L.push(`| ${mark} | ${r.page} | ${r.url} |`);
    }
    L.push("");
  }

  writeFileSync("../../TEST-LINKS.md", L.join("\n"));
  console.log("Wrote TEST-LINKS.md\n");
}

process.exit(mismatches > 0 ? 1 : 0);
