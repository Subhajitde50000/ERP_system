"""
Real end-to-end integration test for the Teacher & Student consoles.

Embedded Postgres (pgserver) + full schema from the ORM models, seeded with a
tenant, one teacher (CS201 in FY CSE-A) and one enrolled student. The tests
then drive the actual /teacher/* and /student/* HTTP APIs with real JWTs
through the complete documented workflows (doc §6 C-TC-01…22, §10 C-ST-01…20):

  attendance board → mark → lock          notices  targets → post → read
  exam create → questions → publish       content  upload → student view log
    → attempt → answers → submit          discussion  thread → reply → accept
    → grade → release → result            → vote
  assignment → publish → submit → review  fees  account → installments → receipt

This is what the FakeDB unit tests cannot prove: the new LMS ORM mappings, the
SQL joins/aggregates, the role guards and the release-gating all actually work
against the production schema shape.
"""

import asyncio
import pathlib
import tempfile
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

pgserver = pytest.importorskip("pgserver")

import app.models  # noqa: F401,E402  (register models on Base.metadata)
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.academic import AcademicYear, Department, SchoolClass, Subject  # noqa: E402
from app.models.catalog import Plan  # noqa: E402
from app.models.enrollment import Enrollment, TeacherSubject  # noqa: E402
from app.models.lms import (  # noqa: E402
    FeeInstallment,
    FeePayment,
    FeeStructure,
    FeeAccountStatus,
    InstallmentStatus,
    PaymentMode,
    StudentFeeAccount,
)
from app.models.principal import TimetableSlot  # noqa: E402
from app.models.role import Role, RoleAssignment, ScopeLevel  # noqa: E402
from app.models.tenant import Tenant, TenantType  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

SLUG = "greenvalley"
TEACHER_EMAIL = "anita@greenvalley.edu"
TEACHER_PASSWORD = "Teach@12345"
STUDENT_EMAIL = "rohan@greenvalley.edu"
STUDENT_PASSWORD = "Study@12345"

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def real_backend():
    """Start Postgres, create schema, seed the school, yield the HTTP client + ids."""
    srv = pgserver.get_server(pathlib.Path(tempfile.mkdtemp()), cleanup_mode="stop")
    srv.ensure_postgres_running()
    async_uri = srv.get_uri().replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(async_uri)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as s:
        plan = Plan(
            id=uuid.uuid4(), name="Professional", slug=f"professional-{SLUG}",
            max_students=5000, max_teachers=500, max_storage_gb=200,
            price_monthly=7999, price_yearly=79990, currency="INR",
            allowed_modules=[], is_active=True,
        )
        s.add(plan)
        for name, scope in (("TEACHER", ScopeLevel.INSTITUTION), ("STUDENT", ScopeLevel.SELF)):
            s.add(Role(id=uuid.uuid4(), name=name, label=name.title(), scope_level=scope,
                       is_platform=False, is_optional=False))
        await s.flush()

        tenant = Tenant(id=uuid.uuid4(), name="Green Valley College", slug=SLUG,
                        type=TenantType.COLLEGE, plan_id=plan.id, is_active=True,
                        country="India", timezone="Asia/Kolkata")
        s.add(tenant)
        await s.flush()

        year = AcademicYear(id=uuid.uuid4(), tenant_id=tenant.id, name="2026-27",
                            start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        dept = Department(id=uuid.uuid4(), tenant_id=tenant.id, name="Computer Science", code="CSE")
        s.add_all([year, dept])
        await s.flush()

        teacher = User(id=uuid.uuid4(), tenant_id=tenant.id, name="Dr. Anita Rao",
                       email=TEACHER_EMAIL, password_hash=hash_password(TEACHER_PASSWORD), is_active=True)
        student = User(id=uuid.uuid4(), tenant_id=tenant.id, name="Rohan Das",
                       email=STUDENT_EMAIL, password_hash=hash_password(STUDENT_PASSWORD), is_active=True)
        s.add_all([teacher, student])
        await s.flush()

        school_class = SchoolClass(
            id=uuid.uuid4(), tenant_id=tenant.id, department_id=dept.id, academic_year_id=year.id,
            name="FY CSE-A", code="CSE-1A", class_teacher_id=teacher.id, is_active=True,
        )
        s.add(school_class)
        await s.flush()

        subject = Subject(id=uuid.uuid4(), tenant_id=tenant.id, class_id=school_class.id,
                          name="Data Structures", code="CS201", subject_type="THEORY", is_active=True)
        s.add(subject)
        await s.flush()

        s.add(TeacherSubject(id=uuid.uuid4(), tenant_id=tenant.id, teacher_id=teacher.id,
                             subject_id=subject.id, role_in_subject="TEACHER"))
        s.add(Enrollment(id=uuid.uuid4(), tenant_id=tenant.id, student_id=student.id,
                         class_id=school_class.id, academic_year_id=year.id,
                         roll_number="CS201-01", status="ACTIVE"))

        # One slot for every weekday so dashboards/schedule have a period "today".
        for weekday in range(7):
            s.add(TimetableSlot(
                id=uuid.uuid4(), tenant_id=tenant.id, class_id=school_class.id,
                academic_year_id=year.id, day_of_week=weekday, period_number=1,
                start_time=time(9, 0), end_time=time(9, 50), subject_id=subject.id,
                teacher_id=teacher.id, room_no="LH-1", slot_type="CLASS",
                effective_from=date(2026, 6, 1), effective_to=None,
            ))

        structure = FeeStructure(id=uuid.uuid4(), tenant_id=tenant.id, academic_year_id=year.id,
                                 name="FY Tuition", total_amount=Decimal("50000.00"), is_active=True)
        s.add(structure)
        await s.flush()

        account = StudentFeeAccount(
            id=uuid.uuid4(), tenant_id=tenant.id, student_id=student.id, academic_year_id=year.id,
            structure_id=structure.id, total_fee=Decimal("50000.00"), concession_amount=Decimal("0"),
            scholarship_amount=Decimal("0"), net_payable=Decimal("50000.00"),
            total_paid=Decimal("20000.00"), balance_due=Decimal("30000.00"),
            status=FeeAccountStatus.PARTIAL,
        )
        s.add(account)
        await s.flush()
        term1 = FeeInstallment(id=uuid.uuid4(), fee_account_id=account.id, tenant_id=tenant.id,
                               installment_number=1, label="Term 1", amount=Decimal("20000.00"),
                               due_date=date(2026, 7, 15), paid_amount=Decimal("20000.00"),
                               status=InstallmentStatus.PAID)
        term2 = FeeInstallment(id=uuid.uuid4(), fee_account_id=account.id, tenant_id=tenant.id,
                               installment_number=2, label="Term 2", amount=Decimal("30000.00"),
                               due_date=date(2026, 11, 15), paid_amount=Decimal("0"),
                               status=InstallmentStatus.PENDING)
        s.add_all([term1, term2])
        await s.flush()
        s.add(FeePayment(id=uuid.uuid4(), tenant_id=tenant.id, fee_account_id=account.id,
                         installment_id=term1.id, student_id=student.id, amount=Decimal("20000.00"),
                         payment_mode=PaymentMode.CASH, transaction_reference=None,
                         payment_date=date(2026, 7, 10), receipt_number="RCP-1001",
                         collected_by=teacher.id, notes="Term 1 cash payment"))

        roles = (await s.execute(select(Role))).scalars().all()
        role_map = {r.name: r.id for r in roles}
        s.add(RoleAssignment(id=uuid.uuid4(), user_id=teacher.id, role_id=role_map["TEACHER"],
                             tenant_id=tenant.id, is_active=True))
        s.add(RoleAssignment(id=uuid.uuid4(), user_id=student.id, role_id=role_map["STUDENT"],
                             tenant_id=tenant.id, is_active=True))
        await s.commit()

        ids = {
            "tenant_id": tenant.id,
            "year_id": year.id,
            "class_id": school_class.id,
            "subject_id": subject.id,
            "teacher_id": teacher.id,
            "student_id": student.id,
        }

    async def override_get_db():
        async with Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", timeout=30.0
    ) as ac:
        yield ac, ids

    app.dependency_overrides.clear()
    await engine.dispose()
    srv.cleanup()


async def _login(client, email, password):
    res = await client.post("/api/v1/tenant/auth/login", json={
        "slug": SLUG, "identifier": email, "password": password,
    })
    assert res.status_code == 200, res.text
    token = res.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="module")
async def tokens(real_backend):
    """One login per role per module — tenant login is rate-limited (10/min)."""
    client, _ = real_backend
    return {
        "teacher": await _login(client, TEACHER_EMAIL, TEACHER_PASSWORD),
        "student": await _login(client, STUDENT_EMAIL, STUDENT_PASSWORD),
    }


# ── Guards ────────────────────────────────────────────────────────────────────

async def test_consoles_require_token_and_correct_role(real_backend, tokens):
    client, _ = real_backend
    teacher, student = tokens["teacher"], tokens["student"]

    assert (await client.get("/api/v1/teacher/dashboard")).status_code == 401
    assert (await client.get("/api/v1/student/dashboard")).status_code == 401

    # Role boundaries are fail-closed in both directions.
    assert (await client.get("/api/v1/student/dashboard", headers=teacher)).status_code == 403
    assert (await client.get("/api/v1/teacher/dashboard", headers=student)).status_code == 403

    mine = await client.get("/api/v1/teacher/dashboard", headers=teacher)
    assert mine.status_code == 200, mine.text
    assert "today_periods" in mine.json()["data"]
    assert mine.json()["data"]["teaching_assignment_count"] == 1


# ── C-TC-02…05 / C-ST-03…06 attendance & timetable ────────────────────────────

async def test_attendance_cycle_teacher_marks_student_reads(real_backend, tokens):
    client, ids = real_backend
    teacher, student = tokens["teacher"], tokens["student"]

    scope = await client.get("/api/v1/teacher/teaching-assignments", headers=teacher)
    assert scope.status_code == 200, scope.text
    assert scope.json()["data"][0]["subject_code"] == "CS201"

    today = date.today().isoformat()
    board = await client.get(
        f"/api/v1/teacher/attendance/board?subject_id={ids['subject_id']}&class_id={ids['class_id']}",
        headers=teacher,
    )
    assert board.status_code == 200, board.text
    roster = board.json()["data"]["roster"]
    assert [row["roll_number"] for row in roster] == ["CS201-01"]

    saved = await client.put("/api/v1/teacher/attendance/sessions", headers=teacher, json={
        "class_id": str(ids["class_id"]), "subject_id": str(ids["subject_id"]), "date": today,
        "period_label": "P1", "records": [
            {"student_id": str(ids["student_id"]), "status": "PRESENT"},
        ],
    })
    assert saved.status_code == 200, saved.text
    session_id = saved.json()["data"]["id"]
    assert saved.json()["data"]["total_present"] == 1

    sessions = await client.get("/api/v1/teacher/attendance/sessions", headers=teacher)
    assert sessions.status_code == 200
    assert any(row["id"] == session_id for row in sessions.json()["data"]["items"])

    locked = await client.post(f"/api/v1/teacher/attendance/sessions/{session_id}/lock", headers=teacher)
    assert locked.status_code == 200, locked.text
    assert locked.json()["data"]["is_locked"] is True

    # The student immediately sees it: summary, calendar and timetable.
    summary = await client.get("/api/v1/student/attendance", headers=student)
    assert summary.status_code == 200, summary.text
    cs201 = next(r for r in summary.json()["data"]["subjects"] if r["subject_code"] == "CS201")
    assert cs201["present_count"] == 1
    assert cs201["absent_count"] + cs201["late_count"] + cs201["excused_count"] == 0
    assert cs201["attendance_percentage"] == 100.0

    month = date.today().strftime("%Y-%m")
    calendar = await client.get(f"/api/v1/student/attendance/calendar?month={month}", headers=student)
    assert calendar.status_code == 200, calendar.text
    marked = next(d for d in calendar.json()["data"]["days"] if d["date"] == today)
    assert any(e["status"] == "PRESENT" for e in marked["entries"])

    timetable = await client.get("/api/v1/student/timetable", headers=student)
    assert timetable.status_code == 200, timetable.text
    assert any(slot["subject_code"] == "CS201" for slot in timetable.json()["data"]["slots"])

    schedule = await client.get("/api/v1/teacher/schedule", headers=teacher)
    assert schedule.status_code == 200, schedule.text
    assert any(slot["subject_code"] == "CS201" for slot in schedule.json()["data"]["slots"])


async def test_leave_apply_review_and_cancel(real_backend, tokens):
    client, _ = real_backend
    teacher, student = tokens["teacher"], tokens["student"]

    applied = await client.post("/api/v1/student/attendance/leaves", headers=student, json={
        "from_date": "2026-08-20", "to_date": "2026-08-21",
        "reason": "Family function out of town.", "document_url": "https://files.example.com/note.pdf",
    })
    assert applied.status_code == 201, applied.text
    leave_id = applied.json()["data"]["id"]
    assert applied.json()["data"]["status"] == "PENDING"

    queue = await client.get("/api/v1/teacher/attendance/leaves", headers=teacher)
    assert queue.status_code == 200, queue.text
    assert any(row["id"] == leave_id for row in queue.json()["data"]["items"])

    approved = await client.post(f"/api/v1/teacher/attendance/leaves/{leave_id}/review",
                                 headers=teacher, json={"decision": "APPROVED"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "APPROVED"

    own = await client.get("/api/v1/student/attendance/leaves", headers=student)
    assert any(row["id"] == leave_id and row["status"] == "APPROVED" for row in own.json()["data"]["items"])

    second = await client.post("/api/v1/student/attendance/leaves", headers=student, json={
        "from_date": "2026-09-02", "to_date": "2026-09-02", "reason": "Medical appointment.",
    })
    assert second.status_code == 201, second.text
    cancelled = await client.post(
        f"/api/v1/student/attendance/leaves/{second.json()['data']['id']}/cancel", headers=student)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "CANCELLED"


# ── C-TC-07…11 / C-ST-07…09 the full exam lifecycle ───────────────────────────

async def test_exam_lifecycle_end_to_end(real_backend, tokens):
    client, ids = real_backend
    teacher, student = tokens["teacher"], tokens["student"]

    created = await client.post("/api/v1/teacher/examinations", headers=teacher, json={
        "title": "DS Unit Test 1", "subject_id": str(ids["subject_id"]), "class_id": str(ids["class_id"]),
        "exam_type": "MIXED", "mode": "ONLINE", "total_marks": 10, "passing_marks": 4,
        "duration_minutes": 60, "instructions": "Answer all questions.",
        "scheduled_at": (NOW - timedelta(minutes=2)).isoformat(),
        "window_end_at": (NOW + timedelta(minutes=30)).isoformat(),
        "allow_review": True,
    })
    assert created.status_code == 201, created.text
    exam_id = created.json()["data"]["id"]

    mcq = await client.post(f"/api/v1/teacher/examinations/{exam_id}/questions", headers=teacher, json={
        "text": "Which structure gives O(1) push/pop?", "question_type": "MCQ", "marks": 5,
        "difficulty": "EASY",
        "options": [
            {"text": "Linked list head insertion", "is_correct": False, "sort_order": 0},
            {"text": "Stack using array", "is_correct": True, "sort_order": 1},
        ],
    })
    assert mcq.status_code == 201, mcq.text
    mcq_id = mcq.json()["data"]["id"]
    correct_option = next(o for o in mcq.json()["data"]["options"] if o["is_correct"])

    short = await client.post(f"/api/v1/teacher/examinations/{exam_id}/questions", headers=teacher, json={
        "text": "Define a stack in one sentence.", "question_type": "SHORT_ANSWER", "marks": 5,
    })
    assert short.status_code == 201, short.text
    short_id = short.json()["data"]["id"]

    # C-TC-09/10 — editing a draft question through the PATCH endpoint.
    edited = await client.patch(
        f"/api/v1/teacher/examinations/{exam_id}/questions/{mcq_id}", headers=teacher, json={
            "text": "Which structure gives O(1) push/pop at one end?",
            "explanation": "Arrays store the top pointer implicitly.",
        })
    assert edited.status_code == 200, edited.text
    assert edited.json()["data"]["text"] == "Which structure gives O(1) push/pop at one end?"

    published = await client.post(f"/api/v1/teacher/examinations/{exam_id}/publish", headers=teacher)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "PUBLISHED"

    # Student discovers the exam and starts an attempt inside the window.
    exams = await client.get("/api/v1/student/examinations", headers=student)
    assert exams.status_code == 200, exams.text
    assert any(row["id"] == exam_id for row in exams.json()["data"]["items"])

    started = await client.post(f"/api/v1/student/examinations/{exam_id}/attempt", headers=student)
    assert started.status_code in (200, 201), started.text
    attempt_id = started.json()["data"]["attempt_id"]
    assert started.json()["data"]["status"] == "IN_PROGRESS"

    paper = await client.get(f"/api/v1/student/examinations/{exam_id}/attempt/paper", headers=student)
    assert paper.status_code == 200, paper.text
    questions = paper.json()["data"]["questions"]
    assert len(questions) == 2
    # Correct answers must never leak into the attempt paper.
    for question in questions:
        for option in question["options"]:
            assert "is_correct" not in option

    saved = await client.put(f"/api/v1/student/examinations/{exam_id}/attempt/answers",
                             headers=student,
                             json={"question_id": mcq_id, "selected_option_id": correct_option["id"]})
    assert saved.status_code == 200, saved.text
    saved = await client.put(f"/api/v1/student/examinations/{exam_id}/attempt/answers",
                             headers=student,
                             json={"question_id": short_id, "text_answer": "A LIFO container of elements."})
    assert saved.status_code == 200, saved.text

    switched = await client.post(f"/api/v1/student/examinations/{exam_id}/attempt/tab-switch",
                                 headers=student)
    assert switched.status_code == 200, switched.text
    assert switched.json()["data"]["tab_switch_count"] == 1

    submitted = await client.post(f"/api/v1/student/examinations/{exam_id}/attempt/submit", headers=student)
    assert submitted.status_code in (200, 201), submitted.text
    assert submitted.json()["data"]["status"] == "SUBMITTED"

    # Result is gated until the teacher releases it: the endpoint answers
    # with a typed UNDER_EVALUATION header (identity + submitted_at, never
    # scores/answers) instead of the old prose 404 the UI had to string-match.
    gated = await client.get(f"/api/v1/student/examinations/{exam_id}/result", headers=student)
    assert gated.status_code == 200, gated.text
    gated_data = gated.json()["data"]
    assert gated_data["result_state"] == "UNDER_EVALUATION"
    assert gated_data["total_score"] is None
    assert gated_data["answers"] == []
    assert gated_data["submitted_at"] is not None

    # Teacher grades the descriptive answer, then releases results.
    attempts = await client.get(f"/api/v1/teacher/examinations/{exam_id}/attempts", headers=teacher)
    assert attempts.status_code == 200, attempts.text
    assert attempts.json()["data"]["items"][0]["attempt_id"] == attempt_id

    detail = await client.get(f"/api/v1/teacher/examinations/{exam_id}/attempts/{attempt_id}", headers=teacher)
    assert detail.status_code == 200, detail.text
    answers = detail.json()["data"]["answers"]
    mcq_answer = next(a for a in answers if a["question_id"] == mcq_id)
    short_answer = next(a for a in answers if a["question_id"] == short_id)
    assert mcq_answer["score"] == 5.0          # auto-graded on submit
    assert short_answer["score"] is None       # awaiting manual grading

    blocked = await client.post(f"/api/v1/teacher/examinations/{exam_id}/release", headers=teacher)
    assert blocked.status_code == 409, blocked.text  # descriptive grading pending

    graded = await client.post(
        f"/api/v1/teacher/examinations/{exam_id}/attempts/{attempt_id}/grade", headers=teacher,
        json={"grades": [{"answer_id": short_answer["answer_id"], "score": 4.5, "feedback": "Crisp definition."}]})
    assert graded.status_code == 200, graded.text

    released = await client.post(f"/api/v1/teacher/examinations/{exam_id}/release", headers=teacher)
    assert released.status_code == 200, released.text
    assert released.json()["data"]["status"] == "RESULTS_RELEASED"

    result = await client.get(f"/api/v1/student/examinations/{exam_id}/result", headers=student)
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["total_score"] == 9.5
    assert data["percentage"] == 95.0
    graded_short = next(a for a in data["answers"] if a["question_id"] == short_id)
    assert graded_short["score"] == 4.5


# ── C-TC-12…16 / C-ST-10…12 assignment lifecycle ──────────────────────────────

async def test_assignment_submission_review_cycle(real_backend, tokens):
    client, ids = real_backend
    teacher, student = tokens["teacher"], tokens["student"]

    created = await client.post("/api/v1/teacher/assignments", headers=teacher, json={
        "title": "Implement a stack", "description": "Push, pop, peek with tests.",
        "subject_id": str(ids["subject_id"]), "class_id": str(ids["class_id"]),
        "assignment_type": "REGULAR", "total_marks": 20, "passing_marks": 8,
        "due_date": (NOW + timedelta(days=3)).isoformat(), "publish": True,
    })
    assert created.status_code == 201, created.text
    assignment_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "PUBLISHED"

    listing = await client.get("/api/v1/student/assignments", headers=student)
    assert listing.status_code == 200, listing.text
    row = next(r for r in listing.json()["data"]["items"] if r["id"] == assignment_id)
    assert row["my_status"] == "PENDING"

    submitted = await client.post(f"/api/v1/student/assignments/{assignment_id}/submit",
                                  headers=student, json={
                                      "text_response": "Implemented with an array-backed stack.",
                                      "files": [{"file_name": "stack.pdf", "file_key": "work/rohan/stack.pdf",
                                                 "file_size_bytes": 2048, "mime_type": "application/pdf"}],
                                  })
    assert submitted.status_code == 201, submitted.text
    submission_id = submitted.json()["data"]["id"]
    assert submitted.json()["data"]["status"] == "SUBMITTED"

    queue = await client.get("/api/v1/teacher/submissions", headers=teacher)
    assert queue.status_code == 200, queue.text
    assert any(row["id"] == submission_id for row in queue.json()["data"]["items"])

    one = await client.get(f"/api/v1/teacher/submissions/{submission_id}", headers=teacher)
    assert one.status_code == 200, one.text
    assert one.json()["data"]["files"][0]["file_name"] == "stack.pdf"

    reviewed = await client.post(f"/api/v1/teacher/submissions/{submission_id}/review",
                                 headers=teacher,
                                 json={"decision": "APPROVED", "score": 18, "feedback": "Clean edge-case handling."})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["status"] == "APPROVED"

    own = await client.get(f"/api/v1/student/assignments/{assignment_id}", headers=student)
    assert own.status_code == 200, own.text
    assert any(
        row["status"] == "APPROVED" and row["score"] == 18.0
        for row in own.json()["data"]["my_submissions"]
    )


# ── C-TC-17…22 / C-ST-13…19 content, notices, discussion ──────────────────────

async def test_content_notices_discussion_cycle(real_backend, tokens):
    client, ids = real_backend
    teacher, student = tokens["teacher"], tokens["student"]

    uploaded = await client.post("/api/v1/teacher/content", headers=teacher, json={
        "title": "Stacks lecture notes", "subject_id": str(ids["subject_id"]), "class_id": str(ids["class_id"]),
        "content_type": "PDF", "external_url": "https://files.example.com/stacks.pdf",
        "chapter": "Chapter 3", "tags": ["stack", "ds"], "is_visible": True,
    })
    assert uploaded.status_code == 201, uploaded.text
    content_id = uploaded.json()["data"]["id"]

    library = await client.get("/api/v1/student/content", headers=student)
    assert library.status_code == 200, library.text
    assert any(row["id"] == content_id for row in library.json()["data"]["items"])

    viewed = await client.get(f"/api/v1/student/content/{content_id}", headers=student)
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["data"]["title"] == "Stacks lecture notes"

    mine = await client.get("/api/v1/teacher/content", headers=teacher)
    row = next(r for r in mine.json()["data"]["items"] if r["id"] == content_id)
    assert row["view_count"] == 1  # the student's open was access-logged

    targets = await client.get("/api/v1/teacher/notices/targets", headers=teacher)
    assert targets.status_code == 200, targets.text
    assert any(row["id"] == str(ids["class_id"]) for row in targets.json()["data"])

    posted = await client.post("/api/v1/teacher/notices", headers=teacher, json={
        "title": "Unit test on Friday", "body": "Syllabus: chapters 1–3.",
        "class_id": str(ids["class_id"]), "priority": "IMPORTANT",
    })
    assert posted.status_code == 201, posted.text
    notice_id = posted.json()["data"]["id"]

    feed = await client.get("/api/v1/student/notices", headers=student)
    assert feed.status_code == 200, feed.text
    seen = next(row for row in feed.json()["data"]["items"] if row["id"] == notice_id)
    assert seen["is_read"] is False

    read = await client.post(f"/api/v1/student/notices/{notice_id}/read", headers=student)
    assert read.status_code == 200, read.text
    assert read.json()["data"]["is_read"] is True

    thread = await client.post("/api/v1/teacher/discussion", headers=teacher, json={
        "title": "Doubt: stack vs queue", "body": "Where do both fall short?",
        "scope_type": "CLASS", "scope_id": str(ids["class_id"]),
    })
    assert thread.status_code == 201, thread.text
    thread_id = thread.json()["data"]["id"]

    listing = await client.get("/api/v1/student/discussion", headers=student)
    assert any(row["id"] == thread_id for row in listing.json()["data"]["items"])

    replied = await client.post(f"/api/v1/student/discussion/{thread_id}/replies", headers=student,
                                json={"body": "Queues cannot do LIFO traversal."})
    assert replied.status_code in (200, 201), replied.text
    reply_id = next(r["id"] for r in replied.json()["data"]["replies"])

    accepted = await client.post(f"/api/v1/teacher/discussion/replies/{reply_id}/accept", headers=teacher)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["is_resolved"] is True
    assert any(r["id"] == reply_id and r["is_accepted_answer"] for r in accepted.json()["data"]["replies"])

    voted = await client.post("/api/v1/student/discussion/vote", headers=student,
                              json={"target_type": "THREAD", "target_id": thread_id})
    assert voted.status_code == 200, voted.text
    assert voted.json()["data"]["upvote_count"] == 1

    detail = await client.get(f"/api/v1/student/discussion/{thread_id}", headers=student)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["is_resolved"] is True
    assert any(r["id"] == reply_id and r["is_accepted_answer"] for r in detail.json()["data"]["replies"])


# ── C-ST-02 / C-ST-20 profile & fees ──────────────────────────────────────────

async def test_student_profile_and_fee_account(real_backend, tokens):
    client, _ = real_backend
    student = tokens["student"]

    profile = await client.get("/api/v1/student/profile", headers=student)
    assert profile.status_code == 200, profile.text
    assert profile.json()["data"]["name"] == "Rohan Das"
    assert profile.json()["data"]["class_info"]["class_name"] == "FY CSE-A"

    updated = await client.patch("/api/v1/student/profile", headers=student, json={
        "phone": "+91-9000000001", "avatar_url": "https://files.example.com/rohan.jpg",
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["phone"] == "+91-9000000001"

    fees = await client.get("/api/v1/student/fees", headers=student)
    assert fees.status_code == 200, fees.text
    data = fees.json()["data"]
    assert data["net_payable"] == 50000.0
    assert data["total_paid"] == 20000.0
    assert data["balance_due"] == 30000.0
    assert data["status"] == "PARTIAL"
    assert [row["label"] for row in data["installments"]] == ["Term 1", "Term 2"]
    # The printable receipt page renders from this payload.
    assert data["payments"][0]["receipt_number"] == "RCP-1001"
    assert data["payments"][0]["payment_mode"] == "CASH"
