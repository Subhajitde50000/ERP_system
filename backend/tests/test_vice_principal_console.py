"""Tests for the delegated Vice Principal production surface (C-VP-01 … 07).

The critical property is fail-closed scope: an unscoped VP never becomes an
institution-wide reader, and no VP endpoint exposes the Principal's final
approval or notice receipt controls.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.principal import Notice, NoticePriority, NoticeScope
from app.models.user import User
from app.schemas.principal import PrincipalNoticeCreate
from app.services.vice_principal_service import VicePrincipalService


class Result:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows

    def scalars(self):
        return MagicMock(all=lambda: self._rows)


class FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.queries = []
        self.added = []
        self.execute = AsyncMock(side_effect=self._pop)

    async def _pop(self, statement):
        # PostgreSQL compilation catches bad joins / scope predicates without
        # needing a local Postgres daemon in the unit suite.
        statement.compile(dialect=postgresql.dialect())
        self.queries.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)

    async def flush(self):
        pass

    def add(self, value):
        self.added.append(value)


def vp(tenant_id: uuid.UUID | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        name="Vice Principal Rao",
        email="vp@example.edu",
        is_active=True,
    )


async def test_vp_role_guard_rejects_a_non_vp_assignment():
    from app.dependencies.auth import get_current_tenant_user_vice_principal

    db = FakeDB([Result(scalar=None)])
    with pytest.raises(HTTPException) as raised:
        await get_current_tenant_user_vice_principal(vp(), db)
    assert raised.value.status_code == 403


async def test_scope_requires_an_active_delegated_department():
    db = FakeDB([Result(rows=[])])
    with pytest.raises(HTTPException) as raised:
        await VicePrincipalService.scope_for_user(db, vp())
    assert raised.value.status_code == 403
    assert "No active department delegation" in raised.value.detail


async def test_scope_uses_only_delegated_department_ids():
    actor = vp()
    cse, ece = uuid.uuid4(), uuid.uuid4()
    db = FakeDB([Result(rows=[(cse, "Computer Science"), (ece, "Electronics")])])

    scope = await VicePrincipalService.scope_for_user(db, actor)

    assert scope.department_ids == frozenset({cse, ece})
    assert [item.name for item in scope.departments] == ["Computer Science", "Electronics"]


async def test_attendance_query_is_scoped_before_aggregate():
    actor = vp()
    department_id = uuid.uuid4()
    # scope query → tenant timezone → department attendance aggregate
    db = FakeDB([
        Result(rows=[(department_id, "Computer Science")]),
        Result(scalar="Asia/Kolkata"),
        Result(rows=[]),
    ])

    overview = await VicePrincipalService.attendance(db, actor)

    assert overview.departments == []
    sql = str(db.queries[-1].compile(dialect=postgresql.dialect()))
    assert "departments.id IN" in sql
    assert "attendance_sessions.tenant_id" in sql


async def test_exams_results_and_staff_keep_the_department_fence():
    actor = vp()
    department_id = uuid.uuid4()

    exams_db = FakeDB([
        Result(rows=[(department_id, "Computer Science")]),
        Result(scalar=0),
        Result(rows=[]),
    ])
    await VicePrincipalService.examinations(exams_db, actor)
    exam_sql = str(exams_db.queries[-1].compile(dialect=postgresql.dialect()))
    assert "classes.department_id" in exam_sql

    results_db = FakeDB([
        Result(rows=[(department_id, "Computer Science")]),
        Result(rows=[]),
        Result(rows=[]),
        Result(rows=[]),
    ])
    await VicePrincipalService.results(results_db, actor)
    result_sql = str(results_db.queries[1].compile(dialect=postgresql.dialect()))
    assert "departments.id IN" in result_sql

    staff_db = FakeDB([
        Result(rows=[(department_id, "Computer Science")]),
        Result(scalar=0),
        Result(rows=[]),
    ])
    await VicePrincipalService.staff(staff_db, actor)
    staff_sql = str(staff_db.queries[-1].compile(dialect=postgresql.dialect()))
    assert "staff_profiles.department_id IN" in staff_sql


async def test_vp_cannot_create_an_institution_wide_notice():
    actor = vp()
    department_id = uuid.uuid4()
    db = FakeDB([Result(rows=[(department_id, "Computer Science")])])

    with pytest.raises(HTTPException) as raised:
        await VicePrincipalService.create_notice(
            db,
            actor,
            PrincipalNoticeCreate(
                title="All institution",
                body="This must be Principal-only.",
                target_scope="INSTITUTION",
            ),
        )

    assert raised.value.status_code == 403
    assert not db.added


async def test_vp_notice_payload_omits_receipt_data():
    actor = vp()
    department_id = uuid.uuid4()
    notice = Notice(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        title="CSE timetable update",
        body="Room change.",
        author_id=actor.id,
        target_scope=NoticeScope.DEPARTMENT,
        target_id=department_id,
        priority=NoticePriority.NORMAL,
        is_pinned=False,
        published_at=datetime.now(timezone.utc),
    )
    # scope query → count → list rows → department target lookup
    db = FakeDB([
        Result(rows=[(department_id, "Computer Science")]),
        Result(scalar=1),
        Result(rows=[(notice, "Principal", 17)]),
        Result(rows=[(department_id, "Computer Science")]),
    ])

    page = await VicePrincipalService.notices(db, actor)

    assert page.total == 1
    assert page.items[0].target_name == "Computer Science"
    assert "read_count" not in page.items[0].model_dump()


async def test_vp_notice_detail_never_queries_or_serializes_readers():
    actor = vp()
    department_id = uuid.uuid4()
    notice = Notice(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        title="Department update",
        body="Details.",
        author_id=actor.id,
        target_scope=NoticeScope.DEPARTMENT,
        target_id=department_id,
        priority=NoticePriority.NORMAL,
        is_pinned=False,
        published_at=datetime.now(timezone.utc),
    )
    # scope → notice → author → target name → attachments (notice attachments
    # are part of the detail payload). A sixth *reader* query would fail the
    # fake and prove the least-data boundary regressed.
    db = FakeDB([
        Result(rows=[(department_id, "Computer Science")]),
        Result(scalar=notice),
        Result(scalar="Principal"),
        Result(rows=[(department_id, "Computer Science")]),
        Result(rows=[]),  # no attachments
    ])

    detail = await VicePrincipalService.notice_detail(db, actor, notice.id)

    assert detail.title == "Department update"
    assert "read_count" not in detail.model_dump()
    assert "readers" not in detail.model_dump()
    assert len(db.queries) == 5


async def test_admin_cannot_invite_an_unscoped_vp():
    from app.models.role import Role, ScopeLevel
    from app.models.tenant import Tenant, TenantType
    from app.schemas.institution import StaffInvite
    from app.services.institution_service import InstitutionService

    tenant = Tenant(id=uuid.uuid4(), name="College", slug="college", type=TenantType.COLLEGE)
    role = Role(
        id=uuid.uuid4(),
        name="VICE_PRINCIPAL",
        label="Vice Principal",
        scope_level=ScopeLevel.INSTITUTION,
        is_platform=False,
        is_optional=False,
    )
    # Existing-email check → role lookup; enforcement happens before a user,
    # reset token or role assignment can be created.
    db = FakeDB([Result(scalar=None), Result(scalar=role)])

    with pytest.raises(HTTPException) as raised:
        await InstitutionService.invite_staff(
            db,
            tenant,
            StaffInvite(name="VP", email="vp@college.edu", role="VICE_PRINCIPAL"),
        )

    assert raised.value.status_code == 422
    assert "delegated department" in raised.value.detail
    assert not db.added


async def test_admin_cannot_assign_an_unscoped_vp_role():
    from app.models.role import Role, ScopeLevel
    from app.services.institution_service import InstitutionService

    actor = vp()
    role = Role(
        id=uuid.uuid4(),
        name="VICE_PRINCIPAL",
        label="Vice Principal",
        scope_level=ScopeLevel.INSTITUTION,
        is_platform=False,
        is_optional=False,
    )
    # _load_user → _role_by_name; rejection happens before a role assignment
    # can be inserted or a scoped audience can be widened.
    db = FakeDB([Result(scalar=actor), Result(scalar=role)])

    with pytest.raises(HTTPException) as raised:
        await InstitutionService.assign_role(
            db,
            actor.tenant_id,
            actor.id,
            "VICE_PRINCIPAL",
            actor,
        )

    assert raised.value.status_code == 422
    assert "delegated department" in raised.value.detail


async def test_admin_must_revoke_a_specific_vp_department_scope():
    from app.models.role import Role, ScopeLevel
    from app.services.institution_service import InstitutionService

    actor = vp()
    role = Role(
        id=uuid.uuid4(),
        name="VICE_PRINCIPAL",
        label="Vice Principal",
        scope_level=ScopeLevel.INSTITUTION,
        is_platform=False,
        is_optional=False,
    )
    db = FakeDB([Result(scalar=actor), Result(scalar=role)])

    with pytest.raises(HTTPException) as raised:
        await InstitutionService.revoke_role(
            db,
            actor.tenant_id,
            actor.id,
            "VICE_PRINCIPAL",
            actor,
        )

    assert raised.value.status_code == 422
    assert "delegated department" in raised.value.detail


def test_vp_router_has_no_final_approval_endpoints():
    from app.routers.vice_principal import router

    paths = {route.path for route in router.routes}
    assert not any("/approval" in path for path in paths)
    assert "/vice-principal/results" in paths
    assert "/vice-principal/examinations" in paths


@pytest.mark.parametrize(
    "path,method,json",
    [
        ("/api/v1/vice-principal/dashboard", "get", None),
        ("/api/v1/vice-principal/attendance", "get", None),
        ("/api/v1/vice-principal/examinations", "get", None),
        ("/api/v1/vice-principal/results", "get", None),
        ("/api/v1/vice-principal/staff", "get", None),
        ("/api/v1/vice-principal/notices", "get", None),
        ("/api/v1/vice-principal/notices/targets", "get", None),
        ("/api/v1/vice-principal/reports/export?kind=attendance", "get", None),
        (
            "/api/v1/vice-principal/notices",
            "post",
            {"title": "Dept", "body": "Body", "target_scope": "DEPARTMENT", "target_id": str(uuid.uuid4())},
        ),
    ],
)
async def test_vp_routes_require_a_bearer_token(client, path, method, json):
    response = await client.request(method.upper(), path, json=json)
    assert response.status_code == 401
