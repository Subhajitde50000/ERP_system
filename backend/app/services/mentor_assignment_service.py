"""Mentor assignment write path — the single implementation of the rules.

Three consoles assign mentors (Academic Coordinator, Institution Admin and,
inside its department fence, the HOD).  They differ only in *who may target
what*; the rules below are identical for all of them and therefore live here:

1. A mentor assignment targets exactly one student, one project team or one
   whole class (``scope_type``).
2. A mentor may hold any number of assignments.
3. Each student / team / class has at most ONE active mentor per academic
   year.  Assigning a new mentor to an already-mentored target is a
   *reassignment*: the previous row is deactivated (history kept) and the new
   one activated in the same transaction.
4. Every write is audited and both sides are notified in-app.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import String, and_, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import AcademicYear, SchoolClass
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.hod import Assignment, MentorAssignment, MentorScopeType
from app.models.lms import ProjectGroup, ProjectGroupMember
from app.models.role import Role, RoleAssignment
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

# Roles whose holders may be picked as a mentor. MENTOR is granted on first
# assignment when missing (see ``ensure_mentor_role``).
MENTOR_ELIGIBLE_ROLES = frozenset({"TEACHER", "HOD", "MENTOR"})
NOTIFICATION_TYPE = "MENTOR_ASSIGNED"


@dataclass(frozen=True)
class MentorTarget:
    """A validated assignment target inside the caller's tenant + year."""

    scope_type: MentorScopeType
    target_id: uuid.UUID
    name: str
    class_id: uuid.UUID | None
    class_name: str | None
    student_ids: tuple[uuid.UUID, ...]

    @property
    def column(self) -> str:
        return {
            MentorScopeType.STUDENT: "student_id",
            MentorScopeType.TEAM: "team_id",
            MentorScopeType.CLASS: "class_id",
        }[self.scope_type]


def active_enrollment_clause():
    """``student_enrollments.status = 'ACTIVE'`` regardless of enum/varchar drift."""
    return cast(Enrollment.status, String) == EnrollmentStatus.ACTIVE.value


class MentorAssignmentService:
    # ── Lookups ─────────────────────────────────────────────────────────────

    @staticmethod
    async def current_year(db: AsyncSession, tenant_id: uuid.UUID) -> AcademicYear | None:
        return (
            await db.execute(
                select(AcademicYear)
                .where(AcademicYear.tenant_id == tenant_id, AcademicYear.is_current.is_(True))
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def require_current_year(db: AsyncSession, tenant_id: uuid.UUID) -> AcademicYear:
        year = await MentorAssignmentService.current_year(db, tenant_id)
        if year is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Set a current academic year before assigning mentors")
        return year

    @staticmethod
    async def resolve_target(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        year: AcademicYear,
        scope_type: str,
        target_id: uuid.UUID,
        *,
        class_ids: frozenset[uuid.UUID] | None = None,
    ) -> MentorTarget:
        """Validate a target for this tenant + year and list the students it covers.

        ``class_ids`` narrows the search to a class fence (HOD departments);
        ``None`` means institution-wide (Coordinator / Admin).
        """
        try:
            scope = MentorScopeType(scope_type)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scope_type must be STUDENT, TEAM or CLASS")

        class_fence = [SchoolClass.id.in_(class_ids)] if class_ids is not None else []

        if scope is MentorScopeType.CLASS:
            school_class = (
                await db.execute(
                    select(SchoolClass).where(
                        SchoolClass.id == target_id,
                        SchoolClass.tenant_id == tenant_id,
                        SchoolClass.academic_year_id == year.id,
                        SchoolClass.is_active.is_(True),
                        *class_fence,
                    )
                )
            ).scalar_one_or_none()
            if school_class is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found for the current academic year")
            student_ids = (
                await db.execute(
                    select(Enrollment.student_id).where(
                        Enrollment.tenant_id == tenant_id,
                        Enrollment.class_id == school_class.id,
                        Enrollment.academic_year_id == year.id,
                        active_enrollment_clause(),
                    )
                )
            ).scalars().all()
            return MentorTarget(scope, school_class.id, school_class.name, school_class.id, school_class.name, tuple(student_ids))

        if scope is MentorScopeType.TEAM:
            row = (
                await db.execute(
                    select(ProjectGroup, Assignment, SchoolClass)
                    .join(Assignment, and_(Assignment.id == ProjectGroup.assignment_id, Assignment.tenant_id == tenant_id))
                    .join(SchoolClass, and_(SchoolClass.id == Assignment.class_id, SchoolClass.tenant_id == tenant_id))
                    .where(
                        ProjectGroup.id == target_id,
                        ProjectGroup.tenant_id == tenant_id,
                        Assignment.academic_year_id == year.id,
                        *class_fence,
                    )
                )
            ).first()
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project team not found for the current academic year")
            group, coursework, school_class = row
            member_ids = (
                await db.execute(
                    select(ProjectGroupMember.student_id).where(
                        ProjectGroupMember.group_id == group.id,
                        ProjectGroupMember.tenant_id == tenant_id,
                    )
                )
            ).scalars().all()
            return MentorTarget(
                scope, group.id, f"{group.name} · {coursework.title}", school_class.id, school_class.name, tuple(member_ids)
            )

        row = (
            await db.execute(
                select(User, SchoolClass)
                .join(Enrollment, and_(Enrollment.student_id == User.id, Enrollment.tenant_id == tenant_id))
                .join(SchoolClass, and_(SchoolClass.id == Enrollment.class_id, SchoolClass.tenant_id == tenant_id))
                .where(
                    User.id == target_id,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    Enrollment.academic_year_id == year.id,
                    active_enrollment_clause(),
                    *class_fence,
                )
                .limit(1)
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found in the current academic year")
        student, school_class = row
        return MentorTarget(scope, student.id, student.name, school_class.id, school_class.name, (student.id,))

    @staticmethod
    async def live_role_names(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> set[str]:
        """Active, unexpired role names for a user in this tenant."""
        now = datetime.now(timezone.utc)
        rows = await db.execute(
            select(Role.name)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.user_id == user_id,
                RoleAssignment.tenant_id == tenant_id,
                RoleAssignment.is_active.is_(True),
                (RoleAssignment.expires_at.is_(None)) | (RoleAssignment.expires_at > now),
            )
        )
        return set(rows.scalars().all())

    @staticmethod
    async def mentor_candidate(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        mentor_id: uuid.UUID,
        *,
        require_mentor_role: bool,
    ) -> tuple[User, set[str]]:
        """Return the mentor user plus their live role names, or 404.

        ``require_mentor_role`` is True for the HOD (who cannot grant roles) and
        False for the Coordinator / Admin path, which grants MENTOR on demand.
        """
        now = datetime.now(timezone.utc)
        rows = (
            await db.execute(
                select(User, Role.name)
                .join(RoleAssignment, and_(RoleAssignment.user_id == User.id, RoleAssignment.tenant_id == tenant_id))
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(
                    User.id == mentor_id,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    RoleAssignment.is_active.is_(True),
                    (RoleAssignment.expires_at.is_(None)) | (RoleAssignment.expires_at > now),
                )
            )
        ).all()
        roles = {name for _user, name in rows}
        if not rows or not roles & MENTOR_ELIGIBLE_ROLES:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Active teaching staff member not found")
        if require_mentor_role and "MENTOR" not in roles:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Active mentor not found")
        return rows[0][0], roles

    # ── Writes ──────────────────────────────────────────────────────────────

    @staticmethod
    async def ensure_mentor_role(db: AsyncSession, tenant_id: uuid.UUID, mentor: User, roles: set[str], *, actor: User, actor_role: str) -> None:
        """Grant the institution-wide MENTOR role the first time someone is made a mentor."""
        if "MENTOR" in roles:
            return
        role = (await db.execute(select(Role).where(Role.name == "MENTOR"))).scalar_one_or_none()
        if role is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MENTOR role is not seeded")
        existing = (
            await db.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == mentor.id,
                    RoleAssignment.role_id == role.id,
                    RoleAssignment.tenant_id == tenant_id,
                    RoleAssignment.scope_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = RoleAssignment(
                id=uuid.uuid4(), user_id=mentor.id, role_id=role.id, tenant_id=tenant_id,
                scope_id=None, scope_type=None, assigned_by=actor.id,
                assigned_at=datetime.now(timezone.utc), is_active=True,
            )
            db.add(existing)
        else:
            existing.is_active = True
            existing.expires_at = None
            existing.assigned_by = actor.id
            existing.assigned_at = datetime.now(timezone.utc)
        await db.flush()
        roles.add("MENTOR")
        AuditService.record(
            db, actor=actor, actor_role=actor_role, action="ASSIGN_ROLE", entity="RoleAssignment",
            entity_id=existing.id, tenant_id=tenant_id,
            new_value={"user_id": str(mentor.id), "role_name": "MENTOR", "reason": "mentor assignment"},
        )

    @staticmethod
    async def active_for_target(
        db: AsyncSession, tenant_id: uuid.UUID, year_id: uuid.UUID, target: MentorTarget, *, lock: bool = False
    ) -> MentorAssignment:
        stmt = select(MentorAssignment).where(
            MentorAssignment.tenant_id == tenant_id,
            MentorAssignment.academic_year_id == year_id,
            MentorAssignment.is_active.is_(True),
            getattr(MentorAssignment, target.column) == target.target_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def assign(
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        year: AcademicYear,
        mentor: User,
        target: MentorTarget,
        notes: str | None,
        actor: User,
        actor_role: str,
    ) -> MentorAssignment:
        """Make ``mentor`` the single active mentor of ``target`` for ``year``."""
        clean_notes = notes.strip() if notes and notes.strip() else None
        now = datetime.now(timezone.utc)
        existing = await MentorAssignmentService.active_for_target(db, tenant_id, year.id, target, lock=True)

        if existing is not None and existing.mentor_id == mentor.id:
            existing.notes = clean_notes
            existing.assigned_by = actor.id
            existing.assigned_at = now
            await db.flush()
            return existing

        previous_mentor_id = existing.mentor_id if existing is not None else None
        if existing is not None:
            existing.is_active = False
            # Flush the deactivation before the new active row so the partial
            # unique index never sees two active rows for the same target.
            await db.flush()

        # The legacy UNIQUE (mentor_id, student_id, academic_year_id) forbids a
        # second historical row for the same pair, so reactivate it instead.
        historical = (
            await db.execute(
                select(MentorAssignment)
                .where(
                    MentorAssignment.tenant_id == tenant_id,
                    MentorAssignment.academic_year_id == year.id,
                    MentorAssignment.mentor_id == mentor.id,
                    MentorAssignment.is_active.is_(False),
                    getattr(MentorAssignment, target.column) == target.target_id,
                )
                .order_by(MentorAssignment.assigned_at.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if historical is not None:
            assignment = historical
            assignment.is_active = True
        else:
            assignment = MentorAssignment(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                mentor_id=mentor.id,
                scope_type=target.scope_type.value,
                academic_year_id=year.id,
                **{target.column: target.target_id},
            )
            db.add(assignment)
        assignment.assigned_by = actor.id
        assignment.assigned_at = now
        assignment.notes = clean_notes
        try:
            await db.flush()
        except IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This target was assigned concurrently; retry")

        AuditService.record(
            db, actor=actor, actor_role=actor_role,
            action="REASSIGN_MENTOR" if previous_mentor_id else "ASSIGN_MENTOR",
            entity="MentorAssignment", entity_id=assignment.id, tenant_id=tenant_id,
            old_value={"mentor_id": str(previous_mentor_id)} if previous_mentor_id else None,
            new_value={"mentor_id": str(mentor.id), "scope_type": target.scope_type.value, "target_id": str(target.target_id)},
        )
        await MentorAssignmentService._notify(db, tenant_id, mentor, target, assignment.id)
        return assignment

    @staticmethod
    async def remove(
        db: AsyncSession, *, assignment: MentorAssignment, actor: User, actor_role: str
    ) -> None:
        assignment.is_active = False
        await db.flush()
        AuditService.record(
            db, actor=actor, actor_role=actor_role, action="REMOVE_MENTOR", entity="MentorAssignment",
            entity_id=assignment.id, tenant_id=assignment.tenant_id,
            old_value={
                "mentor_id": str(assignment.mentor_id),
                "scope_type": assignment.scope_type,
                "target_id": str(assignment.student_id or assignment.team_id or assignment.class_id),
            },
        )

    @staticmethod
    async def _notify(db: AsyncSession, tenant_id: uuid.UUID, mentor: User, target: MentorTarget, assignment_id: uuid.UUID) -> None:
        label = {
            MentorScopeType.STUDENT: "student",
            MentorScopeType.TEAM: "project team",
            MentorScopeType.CLASS: "class",
        }[target.scope_type]
        data = {"assignment_id": str(assignment_id), "scope_type": target.scope_type.value, "target_id": str(target.target_id)}
        await NotificationService.create_notifications(
            db, tenant_id=tenant_id, user_ids=[mentor.id], notif_type=NOTIFICATION_TYPE,
            title="New mentoring assignment",
            body=f"You are now the mentor of {label} {target.name}.", data=data,
        )
        if target.student_ids:
            await NotificationService.create_notifications(
                db, tenant_id=tenant_id, user_ids=target.student_ids, notif_type=NOTIFICATION_TYPE,
                title="Your mentor has been assigned",
                body=f"{mentor.name} is your mentor" + ("" if target.scope_type is MentorScopeType.STUDENT else f" for {label} {target.name}") + ".",
                data=data,
            )

    # ── Shared read helpers ─────────────────────────────────────────────────

    @staticmethod
    async def team_member_counts(db: AsyncSession, tenant_id: uuid.UUID, team_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not team_ids:
            return {}
        rows = await db.execute(
            select(ProjectGroupMember.group_id, func.count(ProjectGroupMember.id))
            .where(ProjectGroupMember.tenant_id == tenant_id, ProjectGroupMember.group_id.in_(team_ids))
            .group_by(ProjectGroupMember.group_id)
        )
        return {group_id: int(count) for group_id, count in rows.all()}
