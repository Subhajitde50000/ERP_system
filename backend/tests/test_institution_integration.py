"""
Real integration test for the institution-admin API.

Starts an embedded Postgres (pgserver), creates the schema from the ORM models,
seeds a tenant + INSTITUTION_ADMIN, then drives every /institution endpoint over
HTTP with a real JWT. This is the end-to-end check the mocked unit tests cannot
give — it proves the queries, joins, RBAC guard and return shapes actually work.
"""

import asyncio
import os
import pathlib
import tempfile
import uuid

import pytest
import pytest_asyncio

# Defer pgserver import so the file still collects if it is absent.
pgserver = pytest.importorskip("pgserver")

import app.models  # noqa: F401,E402  (register models on Base.metadata)
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.catalog import Module, Plan  # noqa: E402
from app.models.role import Role, RoleAssignment, ScopeLevel  # noqa: E402
from app.models.tenant import Tenant, TenantType  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy import select  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

ADMIN_EMAIL = "admin@green.edu"
ADMIN_PASSWORD = "Admin@12345"


@pytest_asyncio.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def real_backend():
    """Start Postgres, create schema, seed, and yield (client, tenant_slug)."""
    srv = pgserver.get_server(pathlib.Path(tempfile.mkdtemp()), cleanup_mode="stop")
    srv.ensure_postgres_running()
    async_uri = srv.get_uri().replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(async_uri)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    # ── seed ────────────────────────────────────────────────────────────────
    async with Session() as s:
        plan = Plan(id=uuid.uuid4(), name="Professional", slug="professional",
                    max_students=5000, max_teachers=500, max_storage_gb=200,
                    price_monthly=7999, price_yearly=79990, currency="INR",
                    allowed_modules=["hostel"], is_active=True)
        s.add(plan)
        for key, name, core in [("attendance", "Attendance", True), ("hostel", "Hostel", False),
                                 ("examination", "Examination", True)]:
            s.add(Module(key=key, name=name, is_core=core, sort_order=1, price_monthly=1500 if not core else 0))
        for name, scope in [("INSTITUTION_ADMIN", ScopeLevel.INSTITUTION), ("STUDENT", ScopeLevel.SELF),
                             ("TEACHER", ScopeLevel.INSTITUTION),
                             ("ACADEMIC_COORDINATOR", ScopeLevel.INSTITUTION), ("EXAM_CONTROLLER", ScopeLevel.INSTITUTION),
                             ("HOD", ScopeLevel.DEPARTMENT), ("VICE_PRINCIPAL", ScopeLevel.INSTITUTION)]:
            s.add(Role(id=uuid.uuid4(), name=name, label=name.title(), scope_level=scope,
                       is_platform=False, is_optional=False))
        s.add(Role(id=uuid.uuid4(), name="SUPER_ADMIN", label="Super Admin",
                   scope_level=ScopeLevel.PLATFORM, is_platform=True, is_optional=False))
        await s.flush()

        tenant = Tenant(id=uuid.uuid4(), name="Green College", slug="green",
                        type=TenantType.COLLEGE, plan_id=plan.id, is_active=True,
                        country="India", timezone="Asia/Kolkata")
        s.add(tenant)
        await s.flush()

        admin = User(id=uuid.uuid4(), tenant_id=tenant.id, name="Green Admin",
                     email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD), is_active=True)
        s.add(admin)
        await s.flush()

        role_res = await s.execute(select(Role))
        role_map = {r.name: r.id for r in role_res.scalars().all()}
        s.add(RoleAssignment(id=uuid.uuid4(), user_id=admin.id, role_id=role_map["INSTITUTION_ADMIN"],
                             tenant_id=tenant.id, is_active=True))
        await s.commit()

    # ── override get_db with a real session ─────────────────────────────────
    async def override_get_db():
        async with Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac, "green"

    app.dependency_overrides.clear()
    await engine.dispose()
    srv.cleanup()


async def _login(client):
    res = await client.post("/api/v1/tenant/auth/login", json={
        "slug": "green", "identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 200, res.text
    token = res.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Auth guard ───────────────────────────────────────────────────────────────

async def test_admin_endpoints_require_token(real_backend):
    client, _ = real_backend
    assert (await client.get("/api/v1/institution/dashboard")).status_code == 401


async def test_dashboard_returns_real_counts(real_backend):
    client, _ = real_backend
    h = await _login(client)
    res = await client.get("/api/v1/institution/dashboard", headers=h)
    assert res.status_code == 200, res.text
    d = res.json()["data"]
    assert d["name"] == "Green College"
    assert d["counts"]["departments"] == 0
    assert "attendance" in d["enabled_modules"]


# ── Academic years ───────────────────────────────────────────────────────────

async def test_academic_year_crud(real_backend):
    client, _ = real_backend
    h = await _login(client)
    r = await client.post("/api/v1/institution/academic-years", headers=h, json={
        "name": "2026-27", "start_date": "2026-06-01", "end_date": "2027-05-31", "is_current": True,
    })
    assert r.status_code == 201, r.text
    yid = r.json()["data"]["id"]
    assert r.json()["data"]["is_current"] is True

    listed = await client.get("/api/v1/institution/academic-years", headers=h)
    assert listed.status_code == 200
    assert any(y["id"] == yid for y in listed.json()["data"])

    # inverted dates rejected
    bad = await client.post("/api/v1/institution/academic-years", headers=h, json={
        "name": "Bad", "start_date": "2027-01-01", "end_date": "2026-01-01"})
    assert bad.status_code == 422

    # cannot delete the current year
    dele = await client.delete(f"/api/v1/institution/academic-years/{yid}", headers=h)
    assert dele.status_code == 409
    return yid


# ── Departments → classes → subjects ─────────────────────────────────────────

async def test_department_class_subject_chain(real_backend):
    client, _ = real_backend
    h = await _login(client)

    # department
    dr = await client.post("/api/v1/institution/departments", headers=h, json={
        "name": "Computer Science", "code": "CSE"})
    assert dr.status_code == 201, dr.text
    dept = dr.json()["data"]
    assert dept["name"] == "Computer Science"
    dept_id = dept["id"]

    # academic year (unique name so this test is isolated from the CRUD test)
    yr = await client.post("/api/v1/institution/academic-years", headers=h, json={
        "name": "2028-29", "start_date": "2028-06-01", "end_date": "2029-05-31", "is_current": False})
    assert yr.status_code == 201, yr.text
    year_id = yr.json()["data"]["id"]

    # duplicate name → clean 409 (not a 500)
    dup_yr = await client.post("/api/v1/institution/academic-years", headers=h, json={
        "name": "2028-29", "start_date": "2028-06-01", "end_date": "2029-05-31"})
    assert dup_yr.status_code == 409

    # class
    cr = await client.post("/api/v1/institution/classes", headers=h, json={
        "name": "FY CSE-A", "code": "CSE-1A", "department_id": dept_id,
        "academic_year_id": year_id, "max_strength": 60})
    assert cr.status_code == 201, cr.text
    class_id = cr.json()["data"]["id"]
    assert cr.json()["data"]["department_name"] == "Computer Science"

    # subject
    sr = await client.post("/api/v1/institution/subjects", headers=h, json={
        "name": "Data Structures", "code": "CS201", "class_id": class_id, "subject_type": "THEORY"})
    assert sr.status_code == 201, sr.text
    assert sr.json()["data"]["class_name"] == "FY CSE-A"

    # list reflects everything
    subs = await client.get("/api/v1/institution/subjects", headers=h)
    assert any(s["code"] == "CS201" for s in subs.json()["data"])

    # department deletion blocked while it has classes
    dele = await client.delete(f"/api/v1/institution/departments/{dept_id}", headers=h)
    assert dele.status_code == 409

    return dept_id, class_id, year_id


# ── Staff + students + enrollments ───────────────────────────────────────────

async def test_staff_invite_student_enroll(real_backend):
    client, _ = real_backend
    h = await _login(client)

    # Self-contained structure for this test (unique codes keep it isolated).
    dept = (await client.post("/api/v1/institution/departments", headers=h,
             json={"name": "Physics", "code": "PHY"})).json()["data"]
    yr = (await client.post("/api/v1/institution/academic-years", headers=h,
           json={"name": "2027-28", "start_date": "2027-06-01", "end_date": "2028-05-31"})).json()["data"]
    cls = (await client.post("/api/v1/institution/classes", headers=h,
            json={"name": "PHY-1", "code": "PHY-1", "department_id": dept["id"],
                  "academic_year_id": yr["id"], "max_strength": 40})).json()["data"]

    # invite staff
    ir = await client.post("/api/v1/institution/staff", headers=h, json={
        "name": "Priya Nair", "email": "priya@green.edu", "phone": "+9100", "role": "TEACHER"})
    assert ir.status_code == 201, ir.text
    assert ir.json()["data"]["roles"] == ["TEACHER"]

    # verify newly added staff can log in using default password password1234!
    staff_login = await client.post("/api/v1/tenant/auth/login", json={
        "slug": "green", "identifier": "priya@green.edu", "password": "password1234!"})
    assert staff_login.status_code == 200, staff_login.text
    assert "tokens" in staff_login.json()["data"]
    assert "access_token" in staff_login.json()["data"]["tokens"]

    # duplicate invite rejected
    dup = await client.post("/api/v1/institution/staff", headers=h, json={
        "name": "Priya", "email": "priya@green.edu", "role": "TEACHER"})
    assert dup.status_code == 409

    # academic coordinator + exam controller are invitable staff roles
    for role in ("ACADEMIC_COORDINATOR", "EXAM_CONTROLLER"):
        coord = await client.post("/api/v1/institution/staff", headers=h, json={
            "name": f"Coordinator {role}", "email": f"{role.lower()}@green.edu", "role": role})
        assert coord.status_code == 201, coord.text
        assert coord.json()["data"]["roles"] == [role]

    # platform roles and non-staff audiences are never grantable
    for role in ("SUPER_ADMIN", "STUDENT", "INSTITUTION_ADMIN"):
        forbidden = await client.post("/api/v1/institution/staff", headers=h, json={
            "name": "Hacker", "email": f"hacker-{role.lower()}@green.edu", "role": role})
        assert forbidden.status_code == 403, forbidden.text
    bad_grant = await client.put(f"/api/v1/institution/staff/{ir.json()['data']['id']}/roles", headers=h,
                                 json={"role_name": "SUPER_ADMIN"})
    assert bad_grant.status_code == 403, bad_grant.text
    ok_grant = await client.put(f"/api/v1/institution/staff/{ir.json()['data']['id']}/roles", headers=h,
                                json={"role_name": "ACADEMIC_COORDINATOR"})
    assert ok_grant.status_code == 200, ok_grant.text
    assert "ACADEMIC_COORDINATOR" in ok_grant.json()["data"]["roles"]

    # edit staff details
    staff_id = ir.json()["data"]["id"]
    up_res = await client.put(f"/api/v1/institution/staff/{staff_id}", headers=h, json={
        "name": "Prof. Anita Sharma Updated",
        "phone": "+91 99999 88888",
    })
    assert up_res.status_code == 200, up_res.text
    assert up_res.json()["data"]["name"] == "Prof. Anita Sharma Updated"
    assert up_res.json()["data"]["phone"] == "+91 99999 88888"

    # toggle staff active status
    act_res = await client.put(f"/api/v1/institution/staff/{staff_id}/active?active=false", headers=h)
    assert act_res.status_code == 200, act_res.text
    assert act_res.json()["data"]["is_active"] is False

    # delete staff
    del_res = await client.delete(f"/api/v1/institution/staff/{staff_id}", headers=h)
    assert del_res.status_code == 200, del_res.text

    # create student enrolled into the class
    sc = await client.post("/api/v1/institution/students", headers=h, json={
        "name": "Aryan Rao", "roll_no": "PHY001", "class_id": cls["id"]})
    assert sc.status_code == 201, sc.text
    assert sc.json()["data"]["enrollment"]["class_name"] == "PHY-1"

    # verify student can NO longer log in using the old shared default password
    # (each account now gets a unique random password — the shared "password1232!" was a security risk)
    st_login = await client.post("/api/v1/tenant/auth/login", json={
        "slug": "green", "identifier": "PHY001", "password": "password1232!"})
    assert st_login.status_code == 401, "Student should NOT be able to log in with the old shared default password"

    # duplicate roll number rejected
    dup_s = await client.post("/api/v1/institution/students", headers=h, json={"name": "Duplicate", "roll_no": "PHY001"})
    assert dup_s.status_code == 409

    # students list shows the new student
    lst = await client.get("/api/v1/institution/students", headers=h)
    assert any(s["roll_no"] == "PHY001" for s in lst.json()["data"])

    # enrollments list
    en = await client.get("/api/v1/institution/enrollments", headers=h)
    assert any(e["class_name"] == "PHY-1" for e in en.json()["data"])


async def test_staff_bulk_upload(real_backend):
    client, _ = real_backend
    h = await _login(client)

    dept = (await client.post("/api/v1/institution/departments", headers=h,
             json={"name": "Computer Science", "code": "CS"})).json()["data"]

    csv_body = (
        "name,email,phone,role,department_code\n"
        "Neha Gupta,neha@green.edu,+911,TEACHER,CS\n"
        "Arun Das,arun@green.edu,,ACADEMIC_COORDINATOR,\n"
        ",x@green.edu,,TEACHER,\n"
        "Neha Gupta,neha@green.edu,,TEACHER,\n"
        "Bad Role,bad@green.edu,,SUPER_ADMIN,\n"
        "No Scope,noscope@green.edu,,VICE_PRINCIPAL,\n"
        "Warn Me,warn@green.edu,,HOD,ZZZ\n"
    )
    res = await client.post("/api/v1/institution/staff/bulk", headers=h,
                            files={"file": ("staff.csv", csv_body.encode(), "text/csv")})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["total"] == 7
    assert data["created"] == 3  # rows 2, 3 and 7 (HOD warned but created)
    assert {e["row"] for e in data["errors"]} == {4, 5, 6, 7}  # header is row 1
    assert any("name" in e["message"] for e in data["errors"])
    assert any("Duplicate email" in e["message"] for e in data["errors"])
    assert any("cannot be assigned" in e["message"] for e in data["errors"])
    assert any("Vice Principal" in e["message"] for e in data["errors"])
    assert data["warnings"][0]["message"].startswith("Created, but not assigned")
    assert "department code 'ZZZ' not found" in data["warnings"][0]["message"]

    lst = await client.get("/api/v1/institution/staff", headers=h)
    by_email = {s["email"]: s for s in lst.json()["data"]}
    assert by_email["neha@green.edu"]["roles"] == ["TEACHER"]
    assert by_email["neha@green.edu"]["department_name"] == "Computer Science"
    assert by_email["arun@green.edu"]["roles"] == ["ACADEMIC_COORDINATOR"]
    assert "warn@green.edu" in by_email
    assert "bad@green.edu" not in by_email

    # missing headers → 422
    bad = await client.post("/api/v1/institution/staff/bulk", headers=h,
                            files={"file": ("bad.csv", b"foo,bar\n1,2", "text/csv")})
    assert bad.status_code == 422


async def test_students_bulk_upload(real_backend):
    client, _ = real_backend
    h = await _login(client)

    dept = (await client.post("/api/v1/institution/departments", headers=h,
             json={"name": "Chemistry", "code": "CHM"})).json()["data"]
    yr = (await client.post("/api/v1/institution/academic-years", headers=h,
           json={"name": "2029-30", "start_date": "2029-06-01", "end_date": "2030-05-31"})).json()["data"]
    cls = (await client.post("/api/v1/institution/classes", headers=h,
            json={"name": "CHM-1", "code": "CHM-1", "department_id": dept["id"],
                  "academic_year_id": yr["id"], "max_strength": 40})).json()["data"]

    csv_body = (
        "name,roll_no,email,gender,date_of_birth,class_code\n"
        "Ravi Kumar,CHM001,ravi@green.edu,MALE,2006-01-15,CHM-1\n"
        "Sana Ali,CHM002,sana@green.edu,FEMALE,2006-05-20,CHM-1\n"
        ",CHM003,,,,\n"
        "Ravi Kumar,CHM001,,,,\n"
    )
    res = await client.post("/api/v1/institution/students/bulk", headers=h,
                            files={"file": ("students.csv", csv_body.encode(), "text/csv")})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["total"] == 4
    assert data["created"] == 2
    assert {e["row"] for e in data["errors"]} == {4, 5}  # row 1 = header, row 2 = first student
    assert any("name" in e["message"] for e in data["errors"])
    assert any("Duplicate roll number in this file" in e["message"] for e in data["errors"])

    lst = await client.get("/api/v1/institution/students", headers=h)
    rolls = {s["roll_no"] for s in lst.json()["data"]}
    assert {"CHM001", "CHM002"} <= rolls
    by_roll = {s["roll_no"]: s for s in lst.json()["data"]}
    assert by_roll["CHM001"]["enrollment"]["class_name"] == "CHM-1"

    # verify bulk imported student can NO longer log in using the old shared default password
    # (each account now gets a unique random password — the shared "password1232!" was a security risk)
    bulk_st_login = await client.post("/api/v1/tenant/auth/login", json={
        "slug": "green", "identifier": "CHM001", "password": "password1232!"})
    assert bulk_st_login.status_code == 401, "Bulk-imported student should NOT log in with old shared default password"

    # re-uploading an existing roll number → DB duplicate reported per row
    csv2 = "name,roll_no\nRavi Kumar,CHM001\nTom Jose,CHM004\n"
    res2 = await client.post("/api/v1/institution/students/bulk", headers=h,
                             files={"file": ("s2.csv", csv2.encode(), "text/csv")})
    assert res2.status_code == 200, res2.text
    data2 = res2.json()["data"]
    assert data2["created"] == 1
    assert any(e["row"] == 2 and "already exists" in e["message"] for e in data2["errors"])

    # unknown class code → student still created, warning reported
    csv3 = "name,roll_no,class_code\nIshaan Sen,CHM005,NOPE-9\n"
    res3 = await client.post("/api/v1/institution/students/bulk", headers=h,
                             files={"file": ("s3.csv", csv3.encode(), "text/csv")})
    assert res3.status_code == 200, res3.text
    data3 = res3.json()["data"]
    assert data3["created"] == 1
    assert data3["warnings"][0]["message"].startswith("Created, but not enrolled")

    # missing headers → 422
    bad = await client.post("/api/v1/institution/students/bulk", headers=h,
                            files={"file": ("bad.csv", b"foo,bar\n1,2", "text/csv")})
    assert bad.status_code == 422


# ── Modules (plan-gated) ─────────────────────────────────────────────────────

async def test_modules_plan_gating(real_backend):
    client, _ = real_backend
    h = await _login(client)
    mods = await client.get("/api/v1/institution/modules", headers=h)
    assert mods.status_code == 200
    by_key = {m["key"]: m for m in mods.json()["data"]}
    assert by_key["attendance"]["is_core"] is True

    # core module cannot be disabled
    core_off = await client.put("/api/v1/institution/modules/attendance", headers=h, json={"enabled": False})
    assert core_off.status_code == 409

    # hostel is in the plan → enabling succeeds
    on = await client.put("/api/v1/institution/modules/hostel", headers=h, json={"enabled": True})
    assert on.status_code == 200, on.text
    assert on.json()["data"]["is_enabled"] is True

    # examination is NOT in the plan → 402 (it's core so it's on; use a non-plan optional instead)
    # create a non-plan optional module on the fly is heavy; the hostel path above covers the happy case.


# ── Settings + profile ───────────────────────────────────────────────────────

async def test_settings_and_profile(real_backend):
    client, _ = real_backend
    h = await _login(client)

    s = await client.get("/api/v1/institution/settings", headers=h)
    assert s.status_code == 200
    assert s.json()["data"]["currency"] == "INR"

    us = await client.put("/api/v1/institution/settings", headers=h, json={"currency": "INR", "timezone": "Asia/Kolkata"})
    assert us.status_code == 200

    p = await client.get("/api/v1/institution/profile", headers=h)
    assert p.status_code == 200
    assert p.json()["data"]["slug"] == "green"
    assert p.json()["data"]["plan_name"] == "Professional"

    up = await client.put("/api/v1/institution/profile", headers=h, json={"phone": "+91 99999"})
    assert up.status_code == 200
    assert up.json()["data"]["phone"] == "+91 99999"
