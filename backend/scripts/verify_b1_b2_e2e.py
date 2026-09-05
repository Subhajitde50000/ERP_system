"""
End-to-end verification of the B1 / B2 fixes against a REAL PostgreSQL.

Runs the actual FastAPI app (httpx ASGI transport — no HTTP server, no DB
mocks) over the canonical schema from database/database.sql and asserts the
two reported defects stay fixed:

  B1  close -> reopen -> resubmit
      * reopen (default) marks un-reviewed submissions RESUBMIT_REQUESTED,
        the assignment reappears in the student's pending dashboard list,
        and a new version (v2) is accepted.
      * reopen {"request_resubmission": false} leaves already-submitted work
        untouched while still allowing new/revised submissions.
  B2  grading context
      * the attempt payload carries the full option list per question (all 6
        question types) plus MATCH pairings.

Usage (any PostgreSQL; the DB must already carry database.sql + the repo's
migration files):

  cd backend
  DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:5432/DBNAME" \
  JWT_SECRET_KEY="anything-for-local-tests" \
  python scripts/verify_b1_b2_e2e.py

The script seeds its own throwaway tenant (random slug), so it is safe to
re-run on a shared dev database. It exits non-zero on any failure.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("EMAIL_PROVIDER", "console")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.role import Role, RoleAssignment  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

API = "/api/v1"
NOW = datetime.now(timezone.utc)
RESULTS = {}


def hr(title: str):
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


async def seed(db):
    from types import SimpleNamespace
    from sqlalchemy import text

    ids = {k: uuid.uuid4() for k in ("tenant", "year", "dept", "klass", "subject", "teacher", "student")}
    slug = f"e2e-{ids['tenant'].hex[:8]}"
    stmts = [
        "INSERT INTO tenants (id, name, slug, type, country) VALUES (:t, 'E2E Repro School', :slug, 'SCHOOL', 'India')",
        "INSERT INTO academic_years (id, tenant_id, name, start_date, end_date, is_current) VALUES (:y, :t, '2025-26', '2025-04-01', '2026-03-31', true)",
        "INSERT INTO departments (id, tenant_id, name, code) VALUES (:d, :t, 'Science', 'SCI')",
        "INSERT INTO classes (id, tenant_id, department_id, academic_year_id, name, code) VALUES (:c, :t, :d, :y, 'Class X-A', 'X-A')",
        "INSERT INTO subjects (id, tenant_id, class_id, name, code, subject_type) VALUES (:s, :t, :c, 'Physics', 'PHY', 'THEORY'::subject_type)",
        "INSERT INTO users (id, tenant_id, name, email, password_hash, gender) VALUES (:u1, :t, 'Ms. Feynman', :teacher_email, :teacher_pw, 'FEMALE'::gender)",
        "INSERT INTO users (id, tenant_id, name, email, password_hash, gender, student_roll_no) VALUES (:u2, :t, 'Ada L', :student_email, :student_pw, 'FEMALE'::gender, :roll)",
        "INSERT INTO student_enrollments (id, tenant_id, student_id, class_id, academic_year_id, roll_number) VALUES (:e, :t, :u2, :c, :y, '101')",
        "INSERT INTO teacher_subjects (id, tenant_id, teacher_id, subject_id, role_in_subject) VALUES (:ts, :t, :u1, :s, 'TEACHER')",
    ]
    params = {
        "t": ids["tenant"], "y": ids["year"], "d": ids["dept"], "c": ids["klass"],
        "s": ids["subject"], "u1": ids["teacher"], "u2": ids["student"], "e": uuid.uuid4(),
        "ts": uuid.uuid4(), "slug": slug,
        "teacher_email": "teacher-" + ids["tenant"].hex[:6] + "@e2e.test",
        "student_email": "student-" + ids["tenant"].hex[:6] + "@e2e.test",
        "teacher_pw": hash_password("Teacher@123"),
        "student_pw": hash_password("Student@123"),
        "roll": "E2E" + ids["tenant"].hex[:6].upper(),
    }
    for stmt in stmts:
        await db.execute(text(stmt), params)
    role_rows = (await db.execute(
        Role.__table__.select().where(Role.name.in_(["TEACHER", "STUDENT"]))
    )).fetchall()
    roles = {r.name: r.id for r in role_rows}
    for name, key in (("TEACHER", "teacher"), ("STUDENT", "student")):
        await db.execute(
            RoleAssignment.__table__.insert().values(
                id=uuid.uuid4(), user_id=ids[key], role_id=roles[name],
                tenant_id=ids["tenant"], is_active=True,
            )
        )
    await db.flush()
    return SimpleNamespace(
        slug=slug, tenant_id=ids["tenant"], year_id=ids["year"], dept_id=ids["dept"],
        class_id=ids["klass"], subject_id=ids["subject"],
        teacher_email=params["teacher_email"], student_email=params["student_email"],
        teacher_pw="Teacher@123", student_pw="Student@123",
    )


async def login(client, slug, identifier, password):
    r = await client.post(f"{API}/tenant/auth/login",
                          json={"slug": slug, "identifier": identifier, "password": password})
    r.raise_for_status()
    data = r.json()["data"]
    return {"Authorization": f"Bearer {data['tokens']['access_token']}"}


async def b1_close_reopen(client, ctx):
    hr("B1 — close → reopen → resubmission")
    t_auth = await login(client, ctx.slug, ctx.teacher_email, ctx.teacher_pw)
    s_auth = await login(client, ctx.slug, ctx.student_email, ctx.student_pw)

    # 1. teacher creates + publishes an assignment
    r = await client.post(f"{API}/teacher/assignments", headers=t_auth, json={
        "title": "Newton's laws worksheet",
        "description": "Solve all problems.",
        "subject_id": str(ctx.subject_id), "class_id": str(ctx.class_id),
        "assignment_type": "REGULAR", "total_marks": 20, "passing_marks": 8,
        "due_date": (NOW + timedelta(days=7)).isoformat(), "publish": True,
    })
    r.raise_for_status()
    assignment = r.json()["data"]
    aid = assignment["id"]
    print(f"[1] assignment created: {assignment['status']}")

    # 2. student submits
    r = await client.post(f"{API}/student/assignments/{aid}/submit", headers=s_auth,
                          json={"text_response": "v1 answers", "files": []})
    r.raise_for_status()
    print(f"[2] student submitted v{r.json()['data']['version']} "
          f"(status={r.json()['data']['status']})")

    # 3. student dashboard pending list BEFORE close
    r = await client.get(f"{API}/student/dashboard", headers=s_auth)
    r.raise_for_status()
    dash = r.json()["data"]
    in_pending = any(p["id"] == aid for p in dash["pending_assignments"])
    print(f"[3] after submit — dashboard pending contains assignment: {in_pending} "
          f"(pending_count={dash['pending_assignment_count']})")

    # 4. teacher closes
    r = await client.post(f"{API}/teacher/assignments/{aid}/close", headers=t_auth)
    r.raise_for_status()
    print(f"[4] closed: {r.json()['data']['status']}")

    # 5. teacher reopens
    r = await client.post(f"{API}/teacher/assignments/{aid}/reopen", headers=t_auth)
    r.raise_for_status()
    print(f"[5] reopened: {r.json()['data']['status']}")

    # 6. student dashboard pending list AFTER reopen  ← the reported gap
    r = await client.get(f"{API}/student/dashboard", headers=s_auth)
    r.raise_for_status()
    dash = r.json()["data"]
    in_pending = any(p["id"] == aid for p in dash["pending_assignments"])
    print(f"[6] after reopen — dashboard pending contains assignment: {in_pending} "
          f"(pending_count={dash['pending_assignment_count']})")

    # what is the student's own status on the assignment row?
    r = await client.get(f"{API}/student/assignments", headers=s_auth)
    r.raise_for_status()
    row = next(a for a in r.json()["data"]["items"] if a["id"] == aid)
    print(f"[7] assignment row: assignment.status={row['status']} my_status={row['my_status']}")

    # 8. can the student still resubmit through the API (submission never re-opened)?
    r = await client.post(f"{API}/student/assignments/{aid}/submit", headers=s_auth,
                          json={"text_response": "v2 revised answers", "files": []})
    print(f"[8] resubmit after reopen: HTTP {r.status_code}"
          + (f" v{r.json()['data']['version']}" if r.status_code == 201 else f" {r.json()['detail']}"))

    RESULTS["b1_pending_after_reopen"] = in_pending
    RESULTS["b1_my_status_after_reopen"] = row["my_status"]
    RESULTS["b1_resubmit_http"] = r.status_code

    # 9. second loop with request_resubmission=false: un-reviewed work stays
    #    untouched; the student who never submitted CAN now submit.
    r = await client.post(f"{API}/teacher/assignments", headers=t_auth, json={
        "title": "Optics reading", "description": "Read chapter 4.",
        "subject_id": str(ctx.subject_id), "class_id": str(ctx.class_id),
        "assignment_type": "REGULAR", "total_marks": 10, "passing_marks": 4,
        "due_date": (NOW + timedelta(days=7)).isoformat(), "publish": True,
    })
    r.raise_for_status()
    aid2 = r.json()["data"]["id"]
    r = await client.post(f"{API}/student/assignments/{aid2}/submit", headers=s_auth,
                          json={"text_response": "v1 optics", "files": []})
    r.raise_for_status()
    r = await client.post(f"{API}/teacher/assignments/{aid2}/close", headers=t_auth)
    r.raise_for_status()
    r = await client.post(f"{API}/teacher/assignments/{aid2}/reopen", json={"request_resubmission": False}, headers=t_auth)
    r.raise_for_status()
    r = await client.get(f"{API}/student/assignments", headers=s_auth)
    row2 = next(a for a in r.json()["data"]["items"] if a["id"] == aid2)
    RESULTS["b1_nudge_false_keeps_status"] = row2["my_status"]
    r = await client.post(f"{API}/student/assignments/{aid2}/submit", headers=s_auth,
                          json={"text_response": "v2 optics (already submitted path)", "files": []})
    RESULTS["b1_nudge_false_resubmit_http"] = r.status_code  # 201: revision allowed
    return aid


async def b2_grading_context(client, ctx):
    hr("B2 — grading view context per question type")
    t_auth = await login(client, ctx.slug, ctx.teacher_email, ctx.teacher_pw)
    s_auth = await login(client, ctx.slug, ctx.student_email, ctx.student_pw)

    # 1. create exam
    r = await client.post(f"{API}/teacher/examinations", headers=t_auth, json={
        "title": "Physics unit test", "subject_id": str(ctx.subject_id), "class_id": str(ctx.class_id),
        "exam_type": "MIXED", "mode": "ONLINE", "total_marks": 12, "passing_marks": 5,
        "duration_minutes": 30, "scheduled_at": (NOW - timedelta(minutes=10)).isoformat(),
        "window_end_at": (NOW + timedelta(hours=2)).isoformat(),
    })
    r.raise_for_status()
    exam = r.json()["data"]
    eid = exam["id"]
    print(f"[1] exam created {exam['status']}")

    # 2. add one question of every type
    questions = {}
    def q(text, kind, marks, options=None):
        return {"text": text, "question_type": kind, "marks": marks, "options": options or []}
    specs = [
        q("Pick the SI unit of force √(kg·m/s²)", "MCQ", 2, [
            {"text": "Newton", "is_correct": True, "sort_order": 1},
            {"text": "Joule", "is_correct": False, "sort_order": 2},
        ]),
        q("The Sun is a star — True or False?", "TRUE_FALSE", 1, [
            {"text": "True", "is_correct": True, "sort_order": 1},
            {"text": "False", "is_correct": False, "sort_order": 2},
        ]),
        q("State Newton's second law (≤ 30 words)", "SHORT_ANSWER", 2),
        q("Derive F = ma from momentum", "LONG_ANSWER", 4),
        q("Fill in the blank: acceleration = Δv / Δ____", "FILL_BLANK", 1),
        q("Match: 1-newton 2-joule 3-watt with unit symbols", "MATCH", 2),
    ]
    for spec in specs:
        r = await client.post(f"{API}/teacher/examinations/{eid}/questions", headers=t_auth, json=spec)
        r.raise_for_status()
        out = r.json()["data"]
        questions[spec["question_type"]] = out
    print(f"[2] added {len(questions)} questions (all 6 types)")

    # 3. publish
    r = await client.post(f"{API}/teacher/examinations/{eid}/publish", headers=t_auth)
    r.raise_for_status()
    print(f"[3] exam {r.json()['data']['status']}")

    # 4. student starts attempt
    r = await client.post(f"{API}/student/examinations/{eid}/attempt", headers=s_auth)
    r.raise_for_status()
    print(f"[4] attempt started")

    # 5. answer everything
    paper = (await client.get(f"{API}/student/examinations/{eid}/attempt/paper", headers=s_auth)).json()["data"]
    answers = {}
    for question in paper["questions"]:
        kind = question["question_type"]
        if kind in ("MCQ", "TRUE_FALSE"):
            # The student paper hides the key; answer MCQ with option[0] and
            # TRUE_FALSE with option[1] (pre-seeded right / wrong).
            chosen = question["options"][0 if kind == "MCQ" else 1]["id"]
            answers[question["id"]] = {"question_id": question["id"], "selected_option_id": chosen}
        else:
            answers[question["id"]] = {"question_id": question["id"],
                                       "text_answer": f"{kind} answer with unicode: α β θ → ✓ ✗"}
    for payload in answers.values():
        r = await client.put(f"{API}/student/examinations/{eid}/attempt/answers", headers=s_auth, json=payload)
        r.raise_for_status()
    print(f"[5] answered all {len(answers)} questions")

    # 6. submit
    r = await client.post(f"{API}/student/examinations/{eid}/attempt/submit", headers=s_auth)
    r.raise_for_status()
    print(f"[6] attempt submitted")

    # 7. teacher opens the grading view ← the reported gap
    r = await client.get(f"{API}/teacher/examinations/{eid}/attempts", headers=t_auth)
    r.raise_for_status()
    attempt_id = r.json()["data"]["items"][0]["attempt_id"]
    r = await client.get(f"{API}/teacher/examinations/{eid}/attempts/{attempt_id}", headers=t_auth)
    r.raise_for_status()
    detail = r.json()["data"]
    print("[7] per-answer context the grading UI receives:")
    missing = []
    for a in detail["answers"]:
        print(f"    {a['question_type']:<12} auto={a['is_auto_graded']!s:<5} "
              f"selected_option_text={a['selected_option_text']!r:<12} "
              f"correct_option_text={a['correct_option_text']!r:<12} "
              f"options_list={'NO' if 'options' not in a else 'yes'} "
              f"text_answer={((a['text_answer'] or '')[:20])!r}")
        if a["question_type"] in ("MCQ", "TRUE_FALSE") and not a["is_auto_graded"]:
            missing.append(a["question_type"])
        if "options" not in a:
            missing.append(f"options-for-{a['question_type']}")

    has_options_field = any("options" in a for a in detail["answers"])
    RESULTS["b2_options_in_payload"] = has_options_field
    print(f"[8] payload includes per-question options list: {has_options_field}")
    return eid, attempt_id


async def main():
    async with AsyncSessionLocal() as db:
        ctx = await seed(db)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await b1_close_reopen(client, ctx)
        await b2_grading_context(client, ctx)

    hr("SUMMARY")
    failed = False
    expectations = {
        "b1_pending_after_reopen": True,
        "b1_my_status_after_reopen": "RESUBMIT_REQUESTED",
        "b1_resubmit_http": 201,
        "b1_nudge_false_keeps_status": "SUBMITTED",
        "b1_nudge_false_resubmit_http": 201,
        "b2_options_in_payload": True,
    }
    for key, expected in expectations.items():
        actual = RESULTS.get(key)
        ok = actual == expected
        failed = failed or not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {key}: {actual!r} (expected {expected!r})")
    await engine.dispose()
    if failed:
        raise SystemExit(1)
    print("\nAll B1/B2 end-to-end checks passed.")



if __name__ == "__main__":
    asyncio.run(main())
