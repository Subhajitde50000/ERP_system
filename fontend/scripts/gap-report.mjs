/**
 * Build-gap report.
 *
 *   node scripts/gap-report.mjs        # print the summary
 *   node scripts/gap-report.mjs --md   # write PAGES-TODO.md
 *
 * Reads the 211-row master table out of
 * `doc/complete_webpage_developer_assignment.md`, matches every documented
 * route against the routes that actually exist in `app/`, and reports what is
 * still missing. Derived from the doc + the filesystem, so it cannot drift the
 * way a hand-written checklist would.
 */

import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const DOC = "../doc/complete_webpage_developer_assignment.md";
const APP = "app";

/* ── 1. Every documented page ───────────────────────────────────────────── */

const md = readFileSync(DOC, "utf8");
const master = md.slice(md.indexOf("## 20. Full Master Page Table"));

const pages = [];
for (const line of master.split("\n")) {
  // | 12 | Role | Page Name | `/route` | Dev-A | C-XX-01 |
  const m = line.match(
    /^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([A-Z-0-9]+)\s*\|/,
  );
  if (!m) continue;
  pages.push({
    num: Number(m[1]),
    role: m[2].trim(),
    name: m[3].trim(),
    route: m[4].trim(),
    backend: m[5].trim(),
    task: m[6].trim(),
  });
}

/* ── 2. Every route that exists ─────────────────────────────────────────── */

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (entry === "page.tsx") out.push(full);
  }
  return out;
}

const built = walk(APP)
  .map((f) =>
    f
      .replace(/^app/, "")
      .replace(/\/page\.tsx$/, "")
      // route groups (auth)/(institution) are not URL segments
      .replace(/\/\([^)]+\)/g, "")
      .replace(/\[(\w+)\]/g, ":$1"),
  )
  .map((r) => (r === "" ? "/" : r));

/**
 * The 24 role-based shared pages absorb many master-table rows.
 * `role_based_shared_pages.md` says so explicitly: "The 24 role-based shared
 * pages are already **included** in the 211 count." So `/principal/attendance`,
 * `/hod/attendance` and `/student/attendance` are all served by the one
 * `/attendance` page — they are built, not missing.
 *
 * Each entry maps a documented per-role route pattern to the shared page that
 * now serves it.
 */
const SHARED = [
  [/^\/[a-z-]+\/dashboard$/, "/dashboard"],
  [/attendance/, "/attendance"],
  [/\/(exams?|examinations?)(\/|$)/, "/examination"],
  [/assignment/, "/assignments"],
  [/\/notices?(\/|$)/, "/notices"],
  [/discussion|forum/, "/discussion"],
  [/\/content|materials|notes/, "/content"],
  [/\/results?(\/|$)|grade-?card/, "/results"],
  [/timetable|schedule$/, "/timetable"],
  [/\/fees?(\/|$)|payment|invoice|defaulter|scholarship/, "/fees"],
  [/\/users?(\/|$)|staff-?directory|student-?list|profiles?$/, "/users"],
  [/leave/, "/leaves"],
  [/report/, "/reports"],
  [/notification/, "/notifications"],
  [/\/settings(\/|$)/, "/settings"],
  [/search/, "/search"],
  [/calendar/, "/calendar"],
  [/\/profile$/, "/profile"],
  [/students?\/:id|student-detail/, "/students/:id"],
  [/staff\/:id|staff-detail/, "/staff/:id"],
  [/audit/, "/audit-logs"],
];

/**
 * Platform-console route prefixes (assignment doc §2).
 *
 * These live at `app.shikshasync.me` and are a *different application* from the
 * institution app — `/finance/invoices` is the platform's billing page, not
 * the tenant's `/fees`. They must never fall through to the SHARED table
 * below, which is written for institution routes: `/report/` matched
 * `/finance/reports`, `payment|invoice` matched `/finance/payments` and
 * `/finance/invoices`, and `/[a-z-]+/dashboard$` matched `/finance/dashboard`
 * — so the report claimed Finance Manager was 4/4 built when none of the four
 * pages existed. A gap report that hides gaps is worse than no report.
 */
/** Is this master-table row a platform-console page rather than a tenant one? */
function isPlatformRoute(page) {
  return /^(Super Admin|Support Staff|Sales Executive|Finance Manager)$/.test(
    page.role,
  );
}

/** Does a documented route resolve to a built one? */
function isBuilt(route, page) {
  const norm = (r) => r.replace(/:\w+/g, ":id").replace(/\/$/, "");
  const target = norm(route);

  if (built.some((b) => norm(b) === target)) return "exact";

  // Platform rows resolve only under `/platform/*`, never via SHARED
  if (page && isPlatformRoute(page)) {
    return built.includes(`/platform${target}`) ? "platform" : false;
  }

  // `[role]/dashboard` serves /library/dashboard, /student/dashboard, …
  if (/^\/[a-z-]+\/dashboard$/.test(target) && built.includes("/:role/dashboard"))
    return "dynamic";

  // 404 and 403 are not routes in Next.js: 404 is `app/not-found.tsx` and
  // 403 is the `<PermissionDenied>` component every guarded page renders.
  // Both are built and verified; they simply have no URL of their own.
  if (target === "/404") return "app/not-found.tsx";
  if (target === "/403") return "components/shared/permission-denied.tsx";

  // A shared page covering this role-specific route
  for (const [pattern, page] of SHARED) {
    if (!pattern.test(route)) continue;
    if (built.some((b) => norm(b) === norm(page))) return `shared:${page}`;
  }

  return false;
}

/* ── 3. Compare ─────────────────────────────────────────────────────────── */

const done = [];
const todo = [];
for (const p of pages) {
  const hit = isBuilt(p.route, p);
  (hit ? done : todo).push({ ...p, how: hit });
}

/* ── 4. Report ──────────────────────────────────────────────────────────── */

const byRole = new Map();
for (const p of todo) {
  if (!byRole.has(p.role)) byRole.set(p.role, []);
  byRole.get(p.role).push(p);
}

const doneByRole = new Map();
for (const p of done) doneByRole.set(p.role, (doneByRole.get(p.role) ?? 0) + 1);

console.log(`\nDocumented pages: ${pages.length}`);
console.log(`Built:            ${done.length}`);
console.log(`Not built:        ${todo.length}\n`);

const roles = [...new Set(pages.map((p) => p.role))];
for (const role of roles) {
  const missing = byRole.get(role) ?? [];
  const built_ = doneByRole.get(role) ?? 0;
  const total = built_ + missing.length;
  const bar = missing.length === 0 ? "✓" : " ";
  console.log(
    `${bar} ${role.padEnd(22)} ${String(built_).padStart(2)}/${String(total).padEnd(3)} built` +
      (missing.length ? `  · ${missing.length} to build` : ""),
  );
}

if (process.argv.includes("--md")) {
  const L = [];
  L.push("# Pages still to build\n");
  L.push("> Generated by `node scripts/gap-report.mjs --md` — do not edit by hand.");
  L.push("> Compares the 211-row master table in");
  L.push("> `complete_webpage_developer_assignment.md` against the routes that");
  L.push("> actually exist under `app/`.\n");
  L.push(`**${done.length} of ${pages.length} built · ${todo.length} remaining**\n`);

  L.push("## Summary by role\n");
  L.push("| Role | Built | Remaining |");
  L.push("|---|---:|---:|");
  for (const role of roles) {
    const missing = (byRole.get(role) ?? []).length;
    const b = doneByRole.get(role) ?? 0;
    L.push(`| ${role} | ${b}/${b + missing} | ${missing || "—"} |`);
  }
  L.push("");

  /* Priority: what unblocks the most, judged by layer.
     Institution-layer gaps are inside the product users already have;
     optional-module gaps sit behind hubs that now exist and render; the
     platform layer is a separate console on another host (§8). */
  const TIER = {
    "Institution Admin": 1, Principal: 1, "Vice Principal": 1, HOD: 1,
    Teacher: 1, "Exam Controller": 1, "Acad. Coordinator": 1, Accountant: 1,
    Student: 1, Parent: 1,
    Librarian: 2, "Hostel Warden": 2, "Transport Manager": 2,
    "Placement Officer": 2, "HR Manager": 2, "Admission Officer": 2,
    "Store Manager": 2,
    Public: 3,
    "Super Admin": 4, "Support Staff": 4, "Sales Executive": 4,
    "Finance Manager": 4,
  };
  const TIER_LABEL = {
    1: "Tier 1 — institution pages (inside the app users already use)",
    2: "Tier 2 — optional-module depth (hubs exist; these are the inner pages)",
    3: "Tier 3 — public/auth",
    4: "Tier 4 — platform console (separate host, §8 — different app)",
  };

  L.push("## Build order\n");
  for (const tier of [1, 2, 3, 4]) {
    const inTier = todo.filter((p) => TIER[p.role] === tier);
    if (!inTier.length) continue;
    L.push(`**${TIER_LABEL[tier]}** — ${inTier.length} pages`);
  }
  L.push("");

  L.push("## Remaining pages\n");
  for (const role of roles) {
    const missing = byRole.get(role) ?? [];
    if (!missing.length) continue;
    L.push(`### ${role} — ${missing.length}\n`);
    L.push("| # | Page | Route | Task | Backend |");
    L.push("|---|---|---|---|---|");
    for (const p of missing) {
      L.push(`| ${p.num} | ${p.name} | \`${p.route}\` | ${p.task} | ${p.backend} |`);
    }
    L.push("");
  }

  L.push("## Already built\n");
  L.push("| # | Role | Page | Route | Task |");
  L.push("|---|---|---|---|---|");
  for (const p of done) {
    L.push(`| ${p.num} | ${p.role} | ${p.name} | \`${p.route}\` | ${p.task} |`);
  }
  L.push("");

  writeFileSync("../doc/PAGES-TODO.md", L.join("\n"));
  console.log("\nWrote PAGES-TODO.md");
}
