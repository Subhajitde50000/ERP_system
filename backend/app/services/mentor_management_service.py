"""Institution-wide mentor management (Academic Coordinator + Institution Admin).

The Academic Coordinator is the primary owner of mentor allocation; the
Institution Admin is the operational fallback.  Both see the same board:
every mentor with their student / team / class assignments, plus every
target that can still receive a mentor.  Writes go through
``MentorAssignmentService`` so the rules match the HOD console exactly.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.academic import Department, SchoolClass
from app.models.enrollment import Enrollment
from app.models.hod import Assignment, MentorAssignment, MentorScopeType
from app.models.lms import ProjectGroup
from app.models.principal import StaffProfile
from app.models.role import Role, RoleAssignment
from app.models.user import User
from app.schemas.mentor import (
    MentorAssignmentRow,
    MentorAssignRequest,
    MentorBoardMentor,
    MentorCandidate,
    MentorCoverage,
    MentorManagementBoard,
    MentorTargetOption,
)
from app.services.mentor_assignment_service import (
    MENTOR_ELIGIBLE_ROLES,
    MentorAssignmentService,
    active_enrollment_clause,
)
from app.services.mentor_service import MentorScopeService


class MentorManagementService:
    @staticmethod
    async def _teaching_staff(db: AsyncSession, tenant_id: uuid.UUID) -> list[tuple[User, set[str], str | None, str | None]]:
        """Every active user holding a teaching role → (user, roles, designation, department)."""
        now = datetime.now(timezone.utc)
        rows = (
            await db.execute(
                select(User, Role.name, StaffProfile.designation, Department.name)
                .join(RoleAssignment, and_(RoleAssignment.user_id == User.id, RoleAssignment.tenant_id == tenant_id))
                .join(Role, Role.id == RoleAssignment.role_id)
                .outerjoin(StaffProfile, and_(StaffProfile.user_id == User.id, StaffProfile.tenant_id == tenant_id))
                .outerjoin(Department, Department.id == StaffProfile.department_id)
                .where(
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    RoleAssignment.is_active.is_(True),
                    (RoleAssignment.expires_at.is_(None)) | (RoleAssignment.expires_at > now),
                )
                .order_by(User.name)
            )
        ).all()
        merged: dict[uuid.UUID, tuple[User, set[str], str | None, str | None]] = {}
        for user, role_name, designation, department_name in rows:
            entry = merged.setdefault(user.id, (user, set(), designation, department_name))
            entry[1].add(role_name)
        return [entry for entry in merged.values() if entry[1] & MENTOR_ELIGIBLE_ROLES]

    @staticmethod
    async def board(db: AsyncSession, tenant_id: uuid.UUID) -> MentorManagementBoard:
        year = await MentorAssignmentService.current_year(db, tenant_id)
        threshold = await MentorScopeService._attendance_threshold(db, tenant_id)
        staff = await MentorManagementService._teaching_staff(db, tenant_id)
        empty = MentorCoverage(classes_total=0, classes_covered=0, teams_total=0, teams_covered=0, students_total=0, students_direct=0, students_covered=0)
        if year is None:
            return MentorManagementBoard(
                academic_year=None, attendance_threshold=threshold, coverage=empty, mentors=[],
                candidates=[MentorCandidate(id=u.id, name=u.name, designation=d, department_name=dep, roles=sorted(r), active_assignment_count=0) for u, r, d, dep in staff],
                classes=[], teams=[], students=[],
            )

        # ── Targets ─────────────────────────────────────────────────────────
        class_rows = (
            await db.execute(
                select(SchoolClass, Department.name, func.count(Enrollment.id))
                .join(Department, Department.id == SchoolClass.department_id)
                .outerjoin(
                    Enrollment,
                    and_(Enrollment.class_id == SchoolClass.id, Enrollment.academic_year_id == year.id, Enrollment.tenant_id == tenant_id, active_enrollment_clause()),
                )
                .where(SchoolClass.tenant_id == tenant_id, SchoolClass.academic_year_id == year.id, SchoolClass.is_active.is_(True))
                .group_by(SchoolClass.id, Department.name)
                .order_by(Department.name, SchoolClass.name)
            )
        ).all()
        team_rows = (
            await db.execute(
                select(ProjectGroup, Assignment.title, SchoolClass.id, SchoolClass.name)
                .join(Assignment, and_(Assignment.id == ProjectGroup.assignment_id, Assignment.tenant_id == tenant_id))
                .join(SchoolClass, SchoolClass.id == Assignment.class_id)
                .where(ProjectGroup.tenant_id == tenant_id, Assignment.academic_year_id == year.id)
                .order_by(SchoolClass.name, Assignment.title, ProjectGroup.name)
            )
        ).all()
        team_sizes = await MentorAssignmentService.team_member_counts(db, tenant_id, [group.id for group, *_ in team_rows])
        student_rows = (
            await db.execute(
                select(User, Enrollment.roll_number, SchoolClass.id, SchoolClass.name)
                .join(Enrollment, and_(Enrollment.student_id == User.id, Enrollment.tenant_id == tenant_id))
                .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
                .where(User.tenant_id == tenant_id, User.deleted_at.is_(None), User.is_active.is_(True), Enrollment.academic_year_id == year.id, active_enrollment_clause())
                .order_by(User.name)
            )
        ).all()

        # ── Active assignments ──────────────────────────────────────────────
        assigner = aliased(User)
        assignment_rows = (
            await db.execute(
                select(MentorAssignment, assigner.name)
                .outerjoin(assigner, assigner.id == MentorAssignment.assigned_by)
                .where(MentorAssignment.tenant_id == tenant_id, MentorAssignment.academic_year_id == year.id, MentorAssignment.is_active.is_(True))
                .order_by(MentorAssignment.assigned_at.desc())
            )
        ).all()
        staff_by_id = {user.id: (user, roles, designation, department) for user, roles, designation, department in staff}
        class_info = {c.id: (c, dept, int(count)) for c, dept, count in class_rows}
        team_info = {g.id: (g, title, class_id, class_name) for g, title, class_id, class_name in team_rows}
        student_info = {u.id: (u, roll, class_id, class_name) for u, roll, class_id, class_name in student_rows}

        mentor_of_class: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
        mentor_of_team: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
        mentor_of_student: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
        grouped: dict[uuid.UUID, list[MentorAssignmentRow]] = defaultdict(list)
        for assignment, assigner_name in assignment_rows:
            mentor_entry = staff_by_id.get(assignment.mentor_id)
            mentor_name = mentor_entry[0].name if mentor_entry else "Former staff"
            scope = MentorScopeType(assignment.scope_type)
            if scope is MentorScopeType.CLASS:
                info = class_info.get(assignment.class_id)
                if info is None:
                    continue
                school_class, dept, count = info
                row = MentorAssignmentRow(id=assignment.id, scope_type="CLASS", target_id=school_class.id, target_name=school_class.name, target_detail=dept, class_id=school_class.id, class_name=school_class.name, member_count=count, assigned_at=assignment.assigned_at, assigned_by_name=assigner_name, notes=assignment.notes)
                mentor_of_class[school_class.id] = (assignment.mentor_id, mentor_name)
            elif scope is MentorScopeType.TEAM:
                info = team_info.get(assignment.team_id)
                if info is None:
                    continue
                group, title, class_id, class_name = info
                row = MentorAssignmentRow(id=assignment.id, scope_type="TEAM", target_id=group.id, target_name=group.name, target_detail=title, class_id=class_id, class_name=class_name, member_count=team_sizes.get(group.id, 0), assigned_at=assignment.assigned_at, assigned_by_name=assigner_name, notes=assignment.notes)
                mentor_of_team[group.id] = (assignment.mentor_id, mentor_name)
            else:
                info = student_info.get(assignment.student_id)
                if info is None:
                    continue
                student, roll, class_id, class_name = info
                row = MentorAssignmentRow(id=assignment.id, scope_type="STUDENT", target_id=student.id, target_name=student.name, target_detail=roll or student.student_roll_no, class_id=class_id, class_name=class_name, member_count=1, assigned_at=assignment.assigned_at, assigned_by_name=assigner_name, notes=assignment.notes)
                mentor_of_student[student.id] = (assignment.mentor_id, mentor_name)
            grouped[assignment.mentor_id].append(row)

        # ── Mentors with resolved mentee sets (distinct students, at-risk) ──
        mentors: list[MentorBoardMentor] = []
        covered_students: set[uuid.UUID] = set()
        for mentor_id, rows in grouped.items():
            entry = staff_by_id.get(mentor_id)
            scope_state = await MentorScopeService.resolve(db, tenant_id, mentor_id, year, threshold=threshold)
            covered_students.update(scope_state.students)
            mentors.append(
                MentorBoardMentor(
                    mentor_id=mentor_id,
                    mentor_name=entry[0].name if entry else "Former staff",
                    email=entry[0].email if entry else None,
                    designation=entry[2] if entry else None,
                    department_name=entry[3] if entry else None,
                    is_active=entry is not None,
                    assignments=sorted(rows, key=lambda r: ({"CLASS": 0, "TEAM": 1, "STUDENT": 2}[r.scope_type], r.target_name.casefold())),
                    mentee_count=len(scope_state.students),
                    at_risk_count=sum(1 for sid in scope_state.students if scope_state.is_at_risk(sid)),
                )
            )
        mentors.sort(key=lambda m: m.mentor_name.casefold())

        def option(target_id, name, detail, class_id, class_name, member_count, mentor: tuple[uuid.UUID, str] | None) -> MentorTargetOption:
            return MentorTargetOption(
                id=target_id, name=name, detail=detail, class_id=class_id, class_name=class_name, member_count=member_count,
                mentor_id=mentor[0] if mentor else None, mentor_name=mentor[1] if mentor else None,
            )

        return MentorManagementBoard(
            academic_year=year.name,
            attendance_threshold=threshold,
            coverage=MentorCoverage(
                classes_total=len(class_rows), classes_covered=len(mentor_of_class),
                teams_total=len(team_rows), teams_covered=len(mentor_of_team),
                students_total=len(student_rows), students_direct=len(mentor_of_student), students_covered=len(covered_students),
            ),
            mentors=mentors,
            candidates=[
                MentorCandidate(id=u.id, name=u.name, designation=d, department_name=dep, roles=sorted(r), active_assignment_count=len(grouped.get(u.id, [])))
                for u, r, d, dep in staff
            ],
            classes=[option(c.id, c.name, dept, c.id, c.name, count, mentor_of_class.get(c.id)) for c, dept, count in class_rows],
            teams=[option(g.id, g.name, title, class_id, class_name, team_sizes.get(g.id, 0), mentor_of_team.get(g.id)) for g, title, class_id, class_name in team_rows],
            students=[option(u.id, u.name, roll or u.student_roll_no, class_id, class_name, 1, mentor_of_student.get(u.id)) for u, roll, class_id, class_name in student_rows],
        )

    @staticmethod
    async def assign(db: AsyncSession, actor: User, actor_role: str, payload: MentorAssignRequest) -> MentorManagementBoard:
        tenant_id = actor.tenant_id
        year = await MentorAssignmentService.require_current_year(db, tenant_id)
        mentor, roles = await MentorAssignmentService.mentor_candidate(db, tenant_id, payload.mentor_id, require_mentor_role=False)
        target = await MentorAssignmentService.resolve_target(db, tenant_id, year, payload.scope_type, payload.target_id)
        if target.scope_type is MentorScopeType.STUDENT and target.target_id == mentor.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A user cannot mentor themselves")
        await MentorAssignmentService.ensure_mentor_role(db, tenant_id, mentor, roles, actor=actor, actor_role=actor_role)
        await MentorAssignmentService.assign(
            db, tenant_id=tenant_id, year=year, mentor=mentor, target=target, notes=payload.notes, actor=actor, actor_role=actor_role
        )
        return await MentorManagementService.board(db, tenant_id)

    @staticmethod
    async def remove(db: AsyncSession, actor: User, actor_role: str, assignment_id: uuid.UUID) -> MentorManagementBoard:
        tenant_id = actor.tenant_id
        assignment = (
            await db.execute(
                select(MentorAssignment)
                .where(MentorAssignment.id == assignment_id, MentorAssignment.tenant_id == tenant_id, MentorAssignment.is_active.is_(True))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mentor assignment not found")
        await MentorAssignmentService.remove(db, assignment=assignment, actor=actor, actor_role=actor_role)
        return await MentorManagementService.board(db, tenant_id)
