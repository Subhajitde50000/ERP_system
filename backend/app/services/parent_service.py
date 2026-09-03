"""Parent portal (C-PA-01 … C-PA-12) and the school-side guardian links (C-IA-12).

Two classes in one file, because they are the two ends of the same object: the
``parent_student_links`` row. :class:`ParentService` is a guardian reading
through a link; :class:`ParentLinkService` is the institution creating, changing
and removing those links, plus the two flows that turn an activation code into
one.

# How a parent is fenced in

The student console needs no scope argument because *the caller is the scope*.
A parent console cannot do that — the caller is not the subject — so this module
closes the same hole from the other side:

1. the caller must hold a live PARENT role (``dependencies/auth``);
2. a ``parent_student_links`` row must join caller → ``child_id``, in the
   caller's tenant, with ``status = ACTIVE`` and ``access_upto`` not passed;
3. the module being read must appear in that row's ``access_scope``;
4. only then is the child's ``User`` row handed to a reader.

Steps 2–3 run on every request inside :meth:`ParentService.link`. Nothing here
takes a student id and trusts it: ``child_id`` is a lookup key that is
meaningless without a matching link, so swapping it yields the same 404 as a
child that does not exist — which is what stops this becoming an enumeration
oracle for student ids.

# Why the readers delegate

Every per-child screen calls the *student* service with the child's own row after
step 4. ``StudentService`` is where the visibility rules live (a result appears
only once its publication is visible **and** approved; a paper never ships
correct answers before release; soft-deleted rows are excluded), and those are
exactly the rules a guardian is entitled to. Re-implementing them here would
create a second definition of "released" — the classic way one console ends up
showing what the other hides.

Three deliberate exceptions:

* **exam results** are re-projected into ``ParentExamSummary`` without the answer
  rows. A student may be allowed to review their own answers; putting the correct
  options of a still-running exam in front of a parent is an integrity leak.
* **leave requests** are written here rather than through the student path, so
  the requester is recorded as the guardian (``attendance_leaves.request_source``)
  and the audit row names the parent, not the child.
* **the child dashboard** is filtered by ``access_scope`` server-side. A fee
  balance that reaches the browser and is hidden with CSS has already left.

Writes flush and never commit, matching the rest of the codebase: ``get_db``
commits once per request, so an action and its audit row land together or not at
all.
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.academic import AcademicYear, Department, SchoolClass
from app.models.billing import TenantModule
from app.models.catalog import Plan
from app.models.enrollment import Enrollment
from app.models.hod import AttendanceRecord, MentorAssignment
from app.models.lms import AttendanceLeave, LeaveStatus
from app.models.parent import (
    DEFAULT_PARENT_ACCESS_SCOPE,
    PARENT_ACCESS_MODULES,
    LinkStatus,
    ParentStudentLink,
)
from app.models.principal import AttendanceSession, ResultPublication, StudentResult
from app.models.role import Role, RoleAssignment
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.parent import (
    CODE_VALID_DAYS,
    ParentAccountClaim,
    ParentChildDashboard,
    ParentChildProfile,
    ParentChildRow,
    ParentClaimByCode,
    ParentClaimedChild,
    ParentCodeCheck,
    ParentChildren,
    ParentExamSummary,
    ParentFamilyOverview,
    ParentFamilyRollup,
    ParentGuardianProfile,
    ParentGuardianUpdate,
    ParentLeaveCreate,
    ParentLeavePage,
    ParentLeaveRow,
    ParentLinkCreate,
    ParentLinkPage,
    ParentLinkRow,
    ParentLinkUpdate,
    ParentPendingInvite,
)
from app.schemas.student import StudentDashboard
from app.services.audit_service import AuditService
from app.services.mailer import queue_email
from app.services.principal_service import PrincipalService, _value
from app.services.push_service import PushService
from app.services.student_service import StudentService
from app.utils.security import generate_secure_token, hash_password, hash_token

logger = logging.getLogger("erp.parent")

#: Crockford-style alphabet: no I, L, O or U, so a code copied from a printed
#: slip cannot gain or lose a letter. 13 characters is ~70 bits, and the unique
#: partial index means a guess can never resolve to more than one family.
#: Crockford's base-32: no I, L, O or U, so a code read over the phone and one
#: copied off a printed slip cannot disagree about a character. 12 symbols is
#: 60 bits — unguessable against an endpoint limited to 20 tries per hour — and
#: it groups into 4-4-4, which is what a slip can actually carry.
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_LENGTH = 12

#: Attendance below this is worth naming on the family overview — 75 % is the
#: threshold the exam-eligibility rules in this codebase already use.
_ATTENDANCE_ALERT_BELOW = 75.0

#: Rows a guardian's phone may have, so `+91 98765 43210` survives and a paste
#: of four numbers does not.
_PHONE_MIN_DIGITS = 7


def _format_code(raw: str) -> str:
    """Group the code the way the slip prints it (XXXX-XXXX-XXXX)."""
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def _new_activation_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def _normalise_phone(value: str | None) -> str | None:
    """Keep the digits and a leading '+', reject anything shorter than a number.

    Guardians type phones from memory, in every format on earth. Normalising
    here — rather than storing "98765432 1 (91)…" — is what makes the school's
    SMS export usable.
    """
    if not value:
        return None
    cleaned = value.strip()
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if len(digits) < _PHONE_MIN_DIGITS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Phone number needs at least 7 digits",
        )
    return ("+" if cleaned.startswith("+") else "") + digits


async def _tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Institution not found")
    return tenant


#: Constraint name → the sentence the office should read. The database is the
#: only component that can answer "why did this write fail?" once two requests
#: race, so the message is taken from the violated constraint instead of being
#: guessed from the code path. Relabelling every IntegrityError as "already
#: linked" once turned an ordering bug into a wrong explanation for a school
#: (and lost the real cause from the log), which is the failure mode this map
#: exists to prevent. An unmapped constraint is logged at error level and the
#: caller gets its own fallback sentence.
_CONSTRAINT_MESSAGES = {
    "uq_parent_student_links__parent_id_student_id": (
        "That guardian is already linked to this student."
    ),
    "uq_parent_student_links_primary_active": (
        "Another active primary guardian already exists for this student."
    ),
    "uq_parent_student_links_pending_email_student": (
        "An invitation for that email is already pending for this student."
    ),
}


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    name = getattr(orig, "constraint_name", None)
    if name:
        return str(name)
    match = re.search(r'constraint "([^"]+)"', str(orig or exc))
    return match.group(1) if match else None


def _integrity_conflict(
    exc: IntegrityError, *, fallback: str, tenant_id: uuid.UUID | None = None
) -> HTTPException:
    """Turn a rejected write into a 409 that names the real rule it broke."""
    name = _constraint_name(exc)
    message = _CONSTRAINT_MESSAGES.get(name or "")
    if message is None:
        # Not a rule the caller can act on: log the database's own words, since
        # that is the only copy anyone will ever have of this.
        logger.error(
            "unexpected database constraint while saving parent access: %s",
            exc.orig or exc,
            extra={
                "event": "parent.db.constraint_violation",
                "constraint": name,
                "tenant_id": str(tenant_id) if tenant_id else None,
            },
        )
        message = fallback
    return HTTPException(status.HTTP_409_CONFLICT, detail=message)


def _serialise(value: object) -> object:
    """Audit JSON is a dict of scalars — UUIDs, dates and lists have to become
    strings before they can be stored."""
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    if isinstance(value, (date, datetime, uuid.UUID)):
        return str(value)
    return value


async def _role_by_name(db: AsyncSession, name: str) -> Role | None:
    return (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()


class ParentService:
    """The guardian console. Read-mostly; the only write is an excused absence."""

    @staticmethod
    async def _is_portal_enabled(db: AsyncSession, tenant: Tenant) -> bool:
        """A tenant may use the guardian portal if:
        1. The 'parent' module is explicitly enabled/disabled in tenant_modules.
        2. The tenant's subscription plan includes 'parent' in allowed_modules.
        3. By default for SCHOOL tenants (unless explicitly disabled above).
        """
        tm_enabled = (
            await db.execute(
                select(TenantModule.is_enabled).where(
                    TenantModule.tenant_id == tenant.id,
                    TenantModule.module_key == "parent",
                )
            )
        ).scalar_one_or_none()
        if tm_enabled is not None:
            return bool(tm_enabled)

        if tenant.plan_id is not None:
            plan = (
                await db.execute(select(Plan).where(Plan.id == tenant.plan_id))
            ).scalar_one_or_none()
            if plan and "parent" in (plan.allowed_modules or []):
                return True

        return _value(tenant.type) == "SCHOOL"

    # ── the fence ────────────────────────────────────────────────────────────

    @staticmethod
    async def link(
        db: AsyncSession,
        parent: User,
        child_id: uuid.UUID,
        *,
        module: str | None = None,
    ) -> tuple[ParentStudentLink, User]:
        """Resolve caller → child, or refuse. Returns the link *and* the child.

        The child row is handed back because every caller needs it; making them
        re-query would tempt a future reader into fetching a student before the
        fence has been checked, which is the whole bug this function exists to
        prevent.
        """
        row = (
            await db.execute(
                select(ParentStudentLink, User)
                .join(
                    User,
                    and_(
                        User.id == ParentStudentLink.student_id,
                        User.tenant_id == parent.tenant_id,
                        User.deleted_at.is_(None),
                    ),
                )
                .where(
                    ParentStudentLink.tenant_id == parent.tenant_id,
                    ParentStudentLink.parent_id == parent.id,
                    ParentStudentLink.student_id == child_id,
                )
                .limit(1)
            )
        ).first()
        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="No linked student with that id"
            )
        link_row, child = row

        tenant = await _tenant(db, parent.tenant_id)
        if not await ParentService._is_portal_enabled(db, tenant):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Parent Portal is not enabled for this institution's subscription plan.",
            )

        today = await PrincipalService._tenant_today(db, parent.tenant_id)
        if link_row.status == LinkStatus.SUSPENDED.value:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Your access to this student has been paused by the school.",
            )
        if not link_row.is_live(today):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your access to this student is no longer active. "
                    "Contact the school office."
                ),
            )
        if module is not None and not link_row.allows(module):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=(
                    f"The school has not granted guardians access to "
                    f"{module.replace('_', ' ')} for this student."
                ),
            )
        return link_row, child

    @staticmethod
    async def _links(db: AsyncSession, parent: User) -> list[ParentStudentLink]:
        return list(
            (
                await db.execute(
                    select(ParentStudentLink)
                    .where(
                        ParentStudentLink.tenant_id == parent.tenant_id,
                        ParentStudentLink.parent_id == parent.id,
                    )
                    .order_by(
                        ParentStudentLink.is_primary.desc(),
                        ParentStudentLink.created_at,
                    )
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def _current_enrollments(
        db: AsyncSession, tenant_id: uuid.UUID, student_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[Enrollment, SchoolClass, Department | None, AcademicYear]]:
        """One query for a whole family: each student's current-year enrolment.

        Deliberately not a join onto the link list — a student with three years of
        enrolment history would multiply the family rows and every caller would
        have to dedupe them again.
        """
        if not student_ids:
            return {}
        rows = (
            await db.execute(
                select(Enrollment, SchoolClass, Department, AcademicYear)
                .join(
                    SchoolClass,
                    and_(
                        SchoolClass.id == Enrollment.class_id,
                        SchoolClass.tenant_id == tenant_id,
                    ),
                )
                .outerjoin(
                    Department,
                    and_(
                        Department.id == SchoolClass.department_id,
                        Department.tenant_id == tenant_id,
                    ),
                )
                .join(
                    AcademicYear,
                    and_(
                        AcademicYear.id == Enrollment.academic_year_id,
                        AcademicYear.tenant_id == tenant_id,
                        AcademicYear.is_current.is_(True),
                    ),
                )
                .where(
                    Enrollment.tenant_id == tenant_id,
                    Enrollment.student_id.in_(student_ids),
                    Enrollment.status == "ACTIVE",
                )
                # Newest wins if a student somehow has two active rows this year;
                # mirrors StudentService.context_for_user.
                .order_by(Enrollment.student_id, Enrollment.created_at.desc())
            )
        ).all()
        out: dict[uuid.UUID, tuple] = {}
        for enrollment, school_class, department, year in rows:
            out.setdefault(enrollment.student_id, (enrollment, school_class, department, year))
        return out

    @staticmethod
    def _child_row(
        link_row: ParentStudentLink,
        child: User,
        enrollment: tuple | None,
        today: date,
    ) -> ParentChildRow:
        """One link + one enrolment → the row in the guardian's child switcher."""
        blocked: str | None = None
        if enrollment is None:
            blocked = "NOT_ENROLLED"
        elif link_row.status == LinkStatus.SUSPENDED.value:
            blocked = "SUSPENDED"
        elif not link_row.is_live(today):
            blocked = "EXPIRED"
        return ParentChildRow(
            link_id=link_row.id,
            student_id=child.id,
            name=child.name,
            avatar_url=child.avatar_url,
            roll_number=enrollment[0].roll_number if enrollment else child.student_roll_no,
            class_name=enrollment[1].name if enrollment else None,
            department_name=enrollment[2].name if enrollment and enrollment[2] else None,
            academic_year=enrollment[3].name if enrollment else None,
            relation=link_row.relation,
            is_primary=bool(link_row.is_primary),
            access_scope=list(link_row.access_scope or []),
            access_upto=link_row.access_upto,
            days_left=(link_row.access_upto - today).days if link_row.access_upto else None,
            is_live=blocked is None,
            # Names the reason instead of showing a console full of zeros, which
            # is the difference between "the school paused me" and a support call.
            blocked_reason=blocked,
        )

    # ── C-PA-01 the family ───────────────────────────────────────────────────

    @staticmethod
    async def children(db: AsyncSession, parent: User) -> ParentChildren:
        tenant = await _tenant(db, parent.tenant_id)
        today = await PrincipalService._tenant_today(db, parent.tenant_id)
        links = await ParentService._links(db, parent)
        by_student = {row.student_id: row for row in links}

        students = []
        if by_student:
            students = list(
                (
                    await db.execute(
                        select(User).where(
                            User.id.in_(list(by_student)), User.deleted_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
        enrollments = await ParentService._current_enrollments(
            db, parent.tenant_id, [s.id for s in students]
        )
        rows = [
            ParentService._child_row(by_student[s.id], s, enrollments.get(s.id), today)
            for s in students
        ]
        rows.sort(key=lambda r: (not r.is_primary, r.name.lower()))

        # Invites recorded against this guardian's email before they had an
        # account, so a parent who signed up late can still claim them.
        pending: list[tuple[ParentStudentLink, User]] = []
        if parent.email:
            pending = list(
                (
                    await db.execute(
                        select(ParentStudentLink, User)
                        .join(User, User.id == ParentStudentLink.student_id)
                        .where(
                            ParentStudentLink.tenant_id == parent.tenant_id,
                            ParentStudentLink.parent_id.is_(None),
                            ParentStudentLink.status == LinkStatus.PENDING_CLAIM.value,
                            func.lower(ParentStudentLink.parent_email) == parent.email.lower(),
                        )
                        .order_by(ParentStudentLink.created_at.desc())
                    )
                ).all()
            )

        portal_enabled = await ParentService._is_portal_enabled(db, tenant)
        return ParentChildren(
            parent_name=parent.name,
            parent_email=parent.email,
            tenant_name=tenant.name,
            tenant_type=_value(tenant.type) or "SCHOOL",
            portal_enabled=portal_enabled,
            children=rows,
            pending_invites=[
                ParentPendingInvite(
                    link_id=link.id,
                    student_name=student.name,
                    student_roll_no=student.student_roll_no,
                    relation=link.relation,
                    is_primary=bool(link.is_primary),
                    code_expires_at=link.code_expires_at,
                    created_at=link.created_at,
                )
                for link, student in pending
            ],
        )

    # ── C-PA-02 family overview (one request, every child) ───────────────────

    @staticmethod
    async def overview(db: AsyncSession, parent: User) -> ParentFamilyOverview:
        tenant = await _tenant(db, parent.tenant_id)
        today = await PrincipalService._tenant_today(db, parent.tenant_id)
        links = await ParentService._links(db, parent)
        by_student = {row.student_id: row for row in links}
        student_ids = [row.student_id for row in links]
        live_ids = {row.student_id for row in links if row.is_live(today)}

        children = []
        if student_ids:
            children = list(
                (
                    await db.execute(
                        select(User).where(
                            User.id.in_(student_ids), User.deleted_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
        enrollments = await ParentService._current_enrollments(db, parent.tenant_id, student_ids)

        # Results waiting on a release: telling a guardian "no results" when two
        # exist but are not out yet is how the office gets the phone call.
        pending_results: dict[uuid.UUID, int] = {}
        if student_ids:
            pending_rows = (
                await db.execute(
                    select(StudentResult.student_id, func.count(StudentResult.id))
                    .join(
                        ResultPublication,
                        and_(
                            ResultPublication.id == StudentResult.publication_id,
                            ResultPublication.tenant_id == parent.tenant_id,
                            or_(
                                ResultPublication.is_visible_to_students.is_(False),
                                ResultPublication.approval_status != "APPROVED",
                            ),
                        ),
                    )
                    .where(
                        StudentResult.tenant_id == parent.tenant_id,
                        StudentResult.student_id.in_(student_ids),
                    )
                    .group_by(StudentResult.student_id)
                )
            ).all()
            pending_results = {sid: int(count or 0) for sid, count in pending_rows}

        rollups: list[ParentFamilyRollup] = []
        for child in children:
            link_row = by_student[child.id]
            scope = set(link_row.access_scope or [])
            if child.id not in live_ids:
                # A paused or expired link is still listed, with no numbers: a
                # guardian who sees an empty screen calls the office, one who sees
                # "paused by the school" waits until Monday and gets the same
                # answer without the phone bill. The reason travels on the row.
                rollups.append(
                    ParentFamilyRollup(
                        child=ParentService._child_row(
                            link_row, child, enrollments.get(child.id), today
                        ),
                        restricted_modules=sorted(set(PARENT_ACCESS_MODULES) - scope),
                    )
                )
                continue
            rollup = ParentFamilyRollup(
                child=ParentService._child_row(
                    link_row, child, enrollments.get(child.id), today
                ),
                unpublished_result_count=pending_results.get(child.id, 0),
                restricted_modules=sorted(set(PARENT_ACCESS_MODULES) - scope),
            )
            # One filtered student dashboard per child. Six indexed queries each,
            # for a family — a screen a guardian opens a few times a week, not a
            # hot path, and reusing the student numbers is what keeps "pending
            # assignment" meaning one thing across both consoles.
            try:
                data = await ParentService._dashboard_payload(db, child, link_row, scope)
            except HTTPException as exc:
                # No enrolment this year: report the child as blocked instead of
                # failing the whole family's overview over one stale row.
                if exc.status_code not in (
                    status.HTTP_403_FORBIDDEN,
                    status.HTTP_404_NOT_FOUND,
                ):
                    raise
                rollups.append(rollup)
                continue
            rollup.attendance_percentage = data.attendance_percentage
            rollup.attendance_low = (
                data.attendance_percentage is not None
                and data.attendance_percentage < _ATTENDANCE_ALERT_BELOW
            )
            rollup.pending_assignment_count = data.pending_assignment_count
            rollup.next_exam = (
                f"{data.next_exam.subject_code} · {data.next_exam.scheduled_at:%d %b}"
                if data.next_exam
                else None
            )
            rollup.fee_balance_due = data.fee_balance_due
            rollup.fee_overdue = bool(data.fee_balance_due)
            rollup.unread_notices = (
                len(data.recent_notices) if "notice" in scope else None
            )
            rollups.append(rollup)

        rollups.sort(key=lambda r: (not r.child.is_primary, r.child.name.lower()))
        portal_enabled = await ParentService._is_portal_enabled(db, tenant)
        return ParentFamilyOverview(
            parent_name=parent.name,
            tenant_name=tenant.name,
            portal_enabled=portal_enabled,
            children=rollups,
        )

    # ── C-PA-03 child dashboard ──────────────────────────────────────────────

    @staticmethod
    async def _dashboard_payload(
        db: AsyncSession,
        child: User,
        link_row: ParentStudentLink,
        scope: set[str] | None = None,
    ) -> StudentDashboard:
        scope = scope if scope is not None else set(link_row.access_scope or [])
        data = await StudentService.dashboard(db, child)
        if "attendance" not in scope:
            data.attendance_percentage = None
            data.attendance_marks = 0
        if "examination" not in scope:
            data.next_exam = None
            data.upcoming_exam_count = 0
        if "assignment" not in scope:
            data.pending_assignment_count = 0
            data.pending_assignments = []
        if "timetable" not in scope:
            data.today_periods = []
        if "notice" not in scope:
            data.recent_notices = []
        if "finance" not in scope:
            data.fee_balance_due = None
        return data

    @staticmethod
    async def dashboard(
        db: AsyncSession, parent: User, child_id: uuid.UUID
    ) -> ParentChildDashboard:
        link_row, child = await ParentService.link(db, parent, child_id)
        today = await PrincipalService._tenant_today(db, parent.tenant_id)
        enrollments = await ParentService._current_enrollments(
            db, parent.tenant_id, [child.id]
        )
        scope = set(link_row.access_scope or [])
        return ParentChildDashboard(
            child=ParentService._child_row(link_row, child, enrollments.get(child.id), today),
            student=await ParentService._dashboard_payload(db, child, link_row, scope),
            restricted_modules=sorted(set(PARENT_ACCESS_MODULES) - scope),
        )

    # ── C-PA-04 child profile, and who the guardian should call ───────────────

    @staticmethod
    async def child_profile(
        db: AsyncSession, parent: User, child_id: uuid.UUID
    ) -> ParentChildProfile:
        _, child = await ParentService.link(db, parent, child_id)
        profile = await StudentService.profile(db, child)

        teacher_name: str | None = None
        teacher_email: str | None = None
        mentor_name: str | None = None

        school_class = (
            await db.execute(
                select(SchoolClass)
                .join(
                    Enrollment,
                    and_(
                        Enrollment.class_id == SchoolClass.id,
                        Enrollment.tenant_id == parent.tenant_id,
                        Enrollment.student_id == child.id,
                        Enrollment.status == "ACTIVE",
                    ),
                )
                .where(SchoolClass.tenant_id == parent.tenant_id)
                .order_by(Enrollment.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if school_class is not None and school_class.class_teacher_id is not None:
            teacher = (
                await db.execute(
                    select(User.name, User.email).where(User.id == school_class.class_teacher_id)
                )
            ).first()
            if teacher:
                teacher_name, teacher_email = teacher[0], teacher[1]

        mentor_name = (
            await db.execute(
                select(User.name)
                .join(MentorAssignment, MentorAssignment.mentor_id == User.id)
                .where(
                    MentorAssignment.tenant_id == parent.tenant_id,
                    MentorAssignment.student_id == child.id,
                    MentorAssignment.is_active.is_(True),
                )
                .order_by(MentorAssignment.academic_year_id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        return ParentChildProfile(
            student=profile,
            class_teacher_name=teacher_name,
            class_teacher_email=teacher_email,
            mentor_name=mentor_name,
        )

    # ── C-PA-05 attendance (module: attendance) ──────────────────────────────

    @staticmethod
    async def attendance(db: AsyncSession, parent: User, child_id: uuid.UUID):
        _, child = await ParentService.link(db, parent, child_id, module="attendance")
        return await StudentService.attendance(db, child)

    @staticmethod
    async def attendance_calendar(
        db: AsyncSession, parent: User, child_id: uuid.UUID, *, month: str
    ):
        _, child = await ParentService.link(db, parent, child_id, module="attendance")
        return await StudentService.attendance_calendar(db, child, month=month)

    @staticmethod
    async def last_attendance(
        db: AsyncSession, parent: User, child_id: uuid.UUID
    ) -> tuple[date | None, str | None]:
        """The most recent marked day and its status: "was she at school today?"

        Its own endpoint because it is the one question that is asked daily, and
        pulling a whole calendar to answer it is the kind of thing that turns into
        a 4 MB payload on a term-end page.
        """
        _, child = await ParentService.link(db, parent, child_id, module="attendance")
        row = (
            await db.execute(
                select(AttendanceSession.date, AttendanceRecord.status)
                .join(AttendanceRecord, AttendanceRecord.session_id == AttendanceSession.id)
                .where(
                    AttendanceRecord.tenant_id == parent.tenant_id,
                    AttendanceRecord.student_id == child.id,
                )
                .order_by(AttendanceSession.date.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return None, None
        return row[0], _value(row[1]) or str(row[1])

    # ── C-PA-06 leave, requested by the guardian ────────────────────────────

    @staticmethod
    def _leave_row(leave: AttendanceLeave, *, parent_id: uuid.UUID) -> ParentLeaveRow:
        return ParentLeaveRow(
            id=leave.id,
            from_date=leave.from_date,
            to_date=leave.to_date,
            reason=leave.reason,
            status=_value(leave.status) or LeaveStatus.PENDING.value,
            document_url=leave.document_url,
            created_at=leave.created_at,
            reviewed_at=leave.reviewed_at,
            request_source=leave.request_source or "STUDENT",
            mine=leave.requested_by == parent_id,
        )

    @staticmethod
    async def leaves(
        db: AsyncSession,
        parent: User,
        child_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ParentLeavePage:
        StudentService._validate_page(limit, offset)
        _, child = await ParentService.link(db, parent, child_id, module="attendance")
        rows = list(
            (
                await db.execute(
                    select(AttendanceLeave)
                    .where(
                        AttendanceLeave.tenant_id == parent.tenant_id,
                        AttendanceLeave.student_id == child.id,
                    )
                    .order_by(AttendanceLeave.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        total = (
            await db.execute(
                select(func.count(AttendanceLeave.id)).where(
                    AttendanceLeave.tenant_id == parent.tenant_id,
                    AttendanceLeave.student_id == child.id,
                )
            )
        ).scalar_one()
        return ParentLeavePage(
            total=int(total or 0),
            limit=limit,
            offset=offset,
            items=[ParentService._leave_row(r, parent_id=parent.id) for r in rows],
        )

    @staticmethod
    async def apply_leave(
        db: AsyncSession,
        parent: User,
        child_id: uuid.UUID,
        payload: ParentLeaveCreate,
    ) -> ParentLeaveRow:
        """File an absence for the child.

        The limits are the student's (30-day cap, no overlapping pending or
        approved request) — a guardian is not owed a wider window than the child,
        and two definitions of "overlapping" is how double-booked leaves happen.
        The one rule that is *stricter* here is the look-back: the office accepts
        a late condonation from a parent, but a fortnight of retroactive absences
        filed from a phone is not a record anyone can sign off.
        """
        _, child = await ParentService.link(db, parent, child_id, module="attendance")
        if payload.to_date < payload.from_date:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="to_date must be on or after from_date",
            )
        if (payload.to_date - payload.from_date).days > 30:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Leave cannot exceed 30 days"
            )
        if payload.from_date < date.today() - timedelta(days=7):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Absences starting more than a week ago cannot be filed here — "
                    "contact the class teacher"
                ),
            )

        # The lock is what makes the overlap check below trustworthy: two guardians
        # submitting the same illness from two phones would otherwise both read
        # "no conflict" and both insert. Postgres could express the rule directly
        # with an EXCLUDE constraint over daterange, but that needs btree_gist,
        # which this deployment does not guarantee — so the portable answer is to
        # serialise on the row a leave is filed against, one lock per student.
        enrollment = (
            await db.execute(
                select(Enrollment)
                .where(
                    Enrollment.tenant_id == parent.tenant_id,
                    Enrollment.student_id == child.id,
                    Enrollment.status == "ACTIVE",
                )
                .order_by(Enrollment.created_at.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if enrollment is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your child has no active enrolment this academic year. "
                    "Contact the school office."
                ),
            )

        overlap = (
            await db.execute(
                select(AttendanceLeave.id).where(
                    AttendanceLeave.tenant_id == parent.tenant_id,
                    AttendanceLeave.student_id == child.id,
                    AttendanceLeave.status.in_((LeaveStatus.PENDING, LeaveStatus.APPROVED)),
                    AttendanceLeave.from_date <= payload.to_date,
                    AttendanceLeave.to_date >= payload.from_date,
                )
            )
        ).scalar_one_or_none()
        if overlap is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="A leave request already covers these dates"
            )

        leave = AttendanceLeave(
            id=uuid.uuid4(),
            tenant_id=parent.tenant_id,
            student_id=child.id,
            class_id=enrollment.class_id,
            from_date=payload.from_date,
            to_date=payload.to_date,
            reason=payload.reason.strip(),
            document_url=payload.document_url,
            requested_by=parent.id,
            request_source="PARENT",
        )
        db.add(leave)
        try:
            await db.flush()
        except IntegrityError as exc:
            # Anything reaching here broke a rule the SELECT-based overlap check
            # could not see (a stale enrolment, a deleted student), so it is
            # neither "already filed" nor something the guardian can fix by
            # rephrasing — log it and let the office know.
            await db.rollback()
            raise _integrity_conflict(
                exc,
                fallback=(
                    "The leave request could not be saved right now. Try again, or "
                    "contact the school office."
                ),
                tenant_id=parent.tenant_id,
            ) from exc

        # Tell the child an absence was filed for them, so the family is not
        # running two different stories past the class teacher. Uses the shared
        # notification service so the child also receives a push on their
        # registered devices (in-app row + FCM outbox in one call).
        await PushService.create_in_app_notifications(
            db,
            tenant_id=parent.tenant_id,
            user_ids=[child.id],
            title="Leave request filed by your guardian",
            body=(
                f"{parent.name} requested leave from {payload.from_date:%d %b %Y} "
                f"to {payload.to_date:%d %b %Y}."
            ),
            notif_type="parent.leave.filed",
            data={"leave_id": str(leave.id)},
        )
        AuditService.record(
            db,
            actor=parent,
            actor_role="PARENT",
            action="APPLY_LEAVE_FOR_CHILD",
            entity="AttendanceLeave",
            entity_id=leave.id,
            tenant_id=parent.tenant_id,
            new_value={
                "student_id": str(child.id),
                "from_date": str(leave.from_date),
                "to_date": str(leave.to_date),
            },
        )
        logger.info(
            "leave filed by parent for child",
            extra={
                "event": "parent.leave.apply",
                "parent_id": str(parent.id),
                "student_id": str(child.id),
            },
        )
        return ParentService._leave_row(leave, parent_id=parent.id)

    @staticmethod
    async def cancel_leave(
        db: AsyncSession, parent: User, child_id: uuid.UUID, leave_id: uuid.UUID
    ) -> ParentLeaveRow:
        """Withdraw a pending request.

        Either the guardian's own or the child's counts: in a school context the
        adult is the one who excuses an absence. What is not allowed here is
        undoing a decision a teacher already made — hence pending-only.
        """
        _, child = await ParentService.link(db, parent, child_id, module="attendance")
        leave = (
            await db.execute(
                select(AttendanceLeave)
                .where(
                    AttendanceLeave.id == leave_id,
                    AttendanceLeave.tenant_id == parent.tenant_id,
                    AttendanceLeave.student_id == child.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if leave is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        if leave.status != LeaveStatus.PENDING:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Only pending leave requests can be cancelled",
            )
        leave.status = LeaveStatus.CANCELLED
        await db.flush()
        AuditService.record(
            db,
            actor=parent,
            actor_role="PARENT",
            action="CANCEL_LEAVE_FOR_CHILD",
            entity="AttendanceLeave",
            entity_id=leave.id,
            tenant_id=parent.tenant_id,
            old_value={"status": LeaveStatus.PENDING.value},
            new_value={"status": LeaveStatus.CANCELLED.value, "student_id": str(child.id)},
        )
        return ParentService._leave_row(leave, parent_id=parent.id)

    # ── C-PA-07 … C-PA-11 the delegated readers ─────────────────────────────

    @staticmethod
    async def timetable(db: AsyncSession, parent: User, child_id: uuid.UUID):
        _, child = await ParentService.link(db, parent, child_id, module="timetable")
        return await StudentService.timetable(db, child)

    @staticmethod
    async def examinations(
        db: AsyncSession,
        parent: User,
        child_id: uuid.UUID,
        *,
        when: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        _, child = await ParentService.link(db, parent, child_id, module="examination")
        return await StudentService.examinations(
            db, child, when=when, limit=limit, offset=offset
        )

    @staticmethod
    async def exam_result(
        db: AsyncSession, parent: User, child_id: uuid.UUID, exam_id: uuid.UUID
    ) -> ParentExamSummary:
        """Score only. The student's answer review stays with the student."""
        _, child = await ParentService.link(db, parent, child_id, module="examination")
        result = await StudentService.exam_result(db, child, exam_id)
        return ParentExamSummary(
            exam_id=result.exam_id,
            title=result.title,
            subject_name=result.subject_name,
            total_marks=result.total_marks,
            passing_marks=result.passing_marks,
            status=result.status,
            total_score=result.total_score,
            percentage=result.percentage,
            grade=result.grade,
            submitted_at=result.submitted_at,
        )

    @staticmethod
    async def assignments(
        db: AsyncSession,
        parent: User,
        child_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        _, child = await ParentService.link(db, parent, child_id, module="assignment")
        return await StudentService.assignments(
            db, child, status_filter=status_filter, limit=limit, offset=offset
        )

    @staticmethod
    async def results(db: AsyncSession, parent: User, child_id: uuid.UUID):
        _, child = await ParentService.link(db, parent, child_id, module="results")
        return await StudentService.results(db, child)

    @staticmethod
    async def result_detail(
        db: AsyncSession, parent: User, child_id: uuid.UUID, publication_id: uuid.UUID
    ):
        _, child = await ParentService.link(db, parent, child_id, module="results")
        return await StudentService.result_detail(db, child, publication_id)

    @staticmethod
    async def notices(
        db: AsyncSession,
        parent: User,
        child_id: uuid.UUID,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        """The child's notice board, read as the child.

        Visibility rules are the student's (institution / department / class
        scopes), so a guardian never sees a notice the class was not addressed.
        Marking one *read* is deliberately absent: that flag measures whether the
        student looked, and ticking it from a parent account would falsify it.
        """
        _, child = await ParentService.link(db, parent, child_id, module="notice")
        return await StudentService.notices(
            db, child, query=query, limit=limit, offset=offset
        )

    @staticmethod
    async def fees(db: AsyncSession, parent: User, child_id: uuid.UUID):
        _, child = await ParentService.link(db, parent, child_id, module="finance")
        return await StudentService.fees(db, child)

    # ── C-PA-12 the guardian's own account ───────────────────────────────────

    @staticmethod
    async def guardian_profile(db: AsyncSession, parent: User) -> ParentGuardianProfile:
        links = await ParentService._links(db, parent)
        return ParentGuardianProfile(
            id=parent.id,
            name=parent.name,
            email=parent.email,
            phone=parent.phone,
            avatar_url=parent.avatar_url,
            address=parent.address,
            last_login_at=parent.last_login_at,
            children_count=len(
                [row for row in links if row.status == LinkStatus.ACTIVE.value]
            ),
            can_edit_contact=True,
        )

    @staticmethod
    async def update_guardian(
        db: AsyncSession, parent: User, payload: ParentGuardianUpdate
    ) -> ParentGuardianProfile:
        """Self-service contact details.

        `name` is not editable: it is the identity on the admission record,
        staff verify it against documents, and the audit trail quotes whatever
        the account says. A guardian who has legally changed their name asks the
        office, which is also the only way the change reaches the transport list.
        """
        phone = _normalise_phone(payload.phone) if payload.phone is not None else None
        changed: dict[str, object] = {}
        if payload.phone is not None and phone != (parent.phone or None):
            changed["phone"] = [parent.phone, phone]
            parent.phone = phone
            # A new number is an unverified number: the school's SMS alerts fire
            # on `phone_verified_at`, so re-verification is not optional.
            parent.phone_verified_at = None
        if payload.address is not None and payload.address != (parent.address or ""):
            changed["address"] = [parent.address, payload.address]
            parent.address = payload.address
        if changed:
            await db.flush()
            AuditService.record(
                db,
                actor=parent,
                actor_role="PARENT",
                action="UPDATE_GUARDIAN_PROFILE",
                entity="User",
                entity_id=parent.id,
                tenant_id=parent.tenant_id,
                new_value={key: value[1] for key, value in changed.items()},
                old_value={key: value[0] for key, value in changed.items()},
            )
        return await ParentService.guardian_profile(db, parent)

    # ── C-PA-12b claim an invitation with an existing account ────────────────

    @staticmethod
    async def claim(
        db: AsyncSession, parent: User, payload: ParentClaimByCode
    ) -> ParentClaimedChild:
        """Attach this account to a code the school issued.

        A parent whose account the office already created should not have to wait
        for someone to click. The code is the whole authority here, so it is
        single-use: matched, claimed, then cleared in the same transaction.
        """
        link_row = await ParentLinkService.find_pending_code(
            db, payload.code, for_update=True
        )
        if link_row.tenant_id != parent.tenant_id:
            # Same answer as a bad code: a guardian on the wrong subdomain must
            # not learn that the code is real elsewhere.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Invitation code not found for this institution"
            )
        child = (
            await db.execute(
                select(User).where(User.id == link_row.student_id, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="This invitation is no longer valid"
            )
        if link_row.parent_email and (parent.email or "").lower() != link_row.parent_email.lower():
            # The code opens the door; the address still has to match, or a
            # photographed slip lets anyone attach their own account to a child.
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=(
                    "This invitation was issued to a different email address. "
                    "Ask the school office to update it."
                ),
            )
        if parent.email is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Add an email address to your account before claiming an invitation",
            )
        return await ParentLinkService.attach(db, link_row, parent, child, actor=parent)


class ParentLinkService:
    """School-side guardian links (C-IA-12) and the claim mechanics."""

    # ── code lookup, shared with the claim flows ─────────────────────────────

    @staticmethod
    async def find_pending_code(
        db: AsyncSession, code: str, *, for_update: bool = False
    ) -> ParentStudentLink:
        normalised = "".join(ch for ch in (code or "").upper() if ch.isalnum())
        if not normalised:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter your invitation code")
        stmt = select(ParentStudentLink).where(
            ParentStudentLink.status == LinkStatus.PENDING_CLAIM.value,
            ParentStudentLink.activation_code == normalised,
        )
        if for_update:
            # Lock the row: two guardians claiming one slip must not both
            # succeed. `SELECT … FOR UPDATE` makes the second wait for the first
            # commit and then find nothing left to claim.
            stmt = stmt.with_for_update()
        link_row = (await db.execute(stmt)).scalar_one_or_none()
        if link_row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=(
                    "Invitation code not found. Check the slip, or ask the school "
                    "office to reissue it."
                ),
            )
        if link_row.code_expires_at is not None and link_row.code_expires_at < datetime.now(
            timezone.utc
        ):
            raise HTTPException(
                status.HTTP_410_GONE,
                detail="This invitation has expired. Ask the school office to reissue a code.",
            )
        return link_row

    @staticmethod
    async def check_code(db: AsyncSession, code: str) -> ParentCodeCheck:
        """Preview before claiming: enough to confirm the child, nothing else."""
        link_row = await ParentLinkService.find_pending_code(db, code)
        child = (
            await db.execute(select(User).where(User.id == link_row.student_id))
        ).scalar_one_or_none()
        tenant = await _tenant(db, link_row.tenant_id)
        enrollments = await ParentService._current_enrollments(
            db, link_row.tenant_id, [link_row.student_id]
        )
        info = enrollments.get(link_row.student_id)
        return ParentCodeCheck(
            institution_name=tenant.name,
            student_name=child.name if child else "Student",
            class_name=info[1].name if info else None,
            relation=link_row.relation,
            is_primary=bool(link_row.is_primary),
            expires_at=link_row.code_expires_at,
        )

    @staticmethod
    async def attach(
        db: AsyncSession,
        link_row: ParentStudentLink,
        parent: User,
        child: User,
        *,
        actor: User,
    ) -> ParentClaimedChild:
        """Connect a pending link to an account and close the code."""
        existing = (
            await db.execute(
                select(ParentStudentLink.id).where(
                    ParentStudentLink.tenant_id == link_row.tenant_id,
                    ParentStudentLink.parent_id == parent.id,
                    ParentStudentLink.student_id == child.id,
                    ParentStudentLink.id != link_row.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            # The school can create two invites for one family (Father and
            # Mother) that the same account then claims; the second becomes
            # redundant rather than a 409 on a row nobody can see.
            link_row.status = LinkStatus.SUSPENDED.value
            link_row.activation_code = None
            link_row.code_expires_at = None
            link_row.note = "Redundant after another guardian link was claimed"
            await db.flush()
            logger.info(
                "duplicate guardian invitation retired after claim",
                extra={"event": "parent.link.redundant", "link_id": str(link_row.id)},
            )

        link_row.parent_id = parent.id
        link_row.status = LinkStatus.ACTIVE.value
        link_row.claimed_at = datetime.now(timezone.utc)
        link_row.activation_code = None
        link_row.code_expires_at = None
        link_row.managed_by = actor.id
        if link_row.is_primary:
            # Only one live primary per child (the partial unique index). Demote
            # the holder rather than refusing the claim: whoever the school
            # listed is who the office should call, and the claim does not
            # silently re-route alerts… unless somebody already holds it, in
            # which case the newcomer is not the primary.
            held = (
                await db.execute(
                    select(ParentStudentLink.id).where(
                        ParentStudentLink.tenant_id == link_row.tenant_id,
                        ParentStudentLink.student_id == child.id,
                        ParentStudentLink.is_primary.is_(True),
                        ParentStudentLink.status == LinkStatus.ACTIVE.value,
                        ParentStudentLink.id != link_row.id,
                    )
                )
            ).scalar_one_or_none()
            if held is not None:
                link_row.is_primary = False
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise _integrity_conflict(
                exc,
                fallback="This student is already linked to your account",
                tenant_id=link_row.tenant_id,
            ) from exc

        AuditService.record(
            db,
            actor=actor,
            actor_role="PARENT" if actor.id == parent.id else "INSTITUTION_ADMIN",
            action="CLAIM_GUARDIAN_LINK",
            entity="ParentStudentLink",
            entity_id=link_row.id,
            tenant_id=link_row.tenant_id,
            new_value={
                "parent_id": str(parent.id),
                "student_id": str(child.id),
                "relation": link_row.relation,
                "is_primary": link_row.is_primary,
            },
        )
        enrollments = await ParentService._current_enrollments(
            db, link_row.tenant_id, [child.id]
        )
        info = enrollments.get(child.id)
        logger.info(
            "guardian link claimed",
            extra={
                "event": "parent.link.claimed",
                "parent_id": str(parent.id),
                "student_id": str(child.id),
                "link_id": str(link_row.id),
            },
        )
        return ParentClaimedChild(
            student_id=child.id,
            student_name=child.name,
            class_name=info[1].name if info else None,
            relation=link_row.relation,
            is_primary=bool(link_row.is_primary),
        )

    # ── public self-service: create the account and claim in one step ────────

    @staticmethod
    async def activate_with_code(
        db: AsyncSession, payload: ParentAccountClaim
    ) -> dict[str, object]:
        """Turn an admission slip into a working login.

        Two factors, because this endpoint is reachable without any prior
        account: the code (which only the family has) and the child's roll
        number (which proves you read the slip). A guessed code alone therefore
        gets a 422, not a child's record.

        Returns no token on purpose — the caller signs in through the ordinary
        tenant login and gets the session, rate limits and lockout that path
        already enforces. Handing out a JWT here would be a second, weaker
        authentication route to the same account.
        """
        link_row = await ParentLinkService.find_pending_code(
            db, payload.code, for_update=True
        )
        tenant = await _tenant(db, link_row.tenant_id)

        email = payload.email.strip().lower()
        if link_row.parent_email and link_row.parent_email.lower() != email:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="This invitation was issued to a different email address",
            )

        child = (
            await db.execute(
                select(User).where(User.id == link_row.student_id, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This invitation is no longer valid")

        roll = payload.student_roll_no.strip().upper()
        child_roll = (child.student_roll_no or "").strip().upper()
        if not child_roll:
            enrollment = (
                await db.execute(
                    select(Enrollment.roll_number)
                    .where(
                        Enrollment.tenant_id == tenant.id,
                        Enrollment.student_id == child.id,
                        Enrollment.status == "ACTIVE",
                    )
                    .order_by(Enrollment.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            child_roll = (enrollment or "").strip().upper()
        if roll != child_roll:
            logger.warning(
                "guardian activation rejected: roll number mismatch",
                extra={"event": "parent.activation.rejected", "tenant_id": str(tenant.id)},
            )
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The roll number does not match this invitation",
            )

        clash = (
            await db.execute(
                select(User.id).where(User.tenant_id == tenant.id, func.lower(User.email) == email)
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="An account already uses this email — sign in and claim the code from your profile",
            )

        role = await _role_by_name(db, "PARENT")
        if role is None:
            # Fail closed with an actionable message rather than half a user: an
            # account with no role can log in and see nothing, which reads as a
            # broken portal.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The Parent role is not available for this institution yet",
            )

        parent = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name=payload.name,
            email=email,
            phone=_normalise_phone(payload.phone),
            password_hash=hash_password(payload.password),
            # The address came from the school's own admission record and the
            # claimer proved access to it by authenticating… which they have not
            # yet done. Mark it unverified and let the first login confirm it.
            email_verified_at=None,
            is_active=True,
        )
        db.add(parent)
        await db.flush()
        db.add(
            RoleAssignment(
                id=uuid.uuid4(),
                user_id=parent.id,
                role_id=role.id,
                tenant_id=tenant.id,
                assigned_at=datetime.now(timezone.utc),
                is_active=True,
            )
        )
        try:
            await db.flush()
        except IntegrityError as exc:  # a concurrent claim took the same email
            await db.rollback()
            raise _integrity_conflict(
                exc,
                fallback=(
                    "An account already uses this email — sign in and claim the "
                    "code instead"
                ),
                tenant_id=tenant.id,
            ) from exc

        await ParentLinkService.attach(db, link_row, parent, child, actor=parent)

        queue_email(
            db,
            "parent.account_created",
            to=email,
            context={
                "name": parent.name,
                "tenant_name": tenant.name,
                "student_name": child.name,
                "login_url": f"https://{tenant.slug}.{get_settings().PUBLIC_ROOT_DOMAIN or 'xyz.com'}/login",
            },
            tenant_id=tenant.id,
        )
        await db.flush()
        logger.info(
            "guardian account created by self-service activation",
            extra={
                "event": "parent.account.activated",
                "tenant_id": str(tenant.id),
                "parent_id": str(parent.id),
            },
        )
        return {
            "slug": tenant.slug,
            "institution_name": tenant.name,
            "email": email,
            "student_name": child.name,
        }

    # ── C-IA-12 admin: the board ─────────────────────────────────────────────

    @staticmethod
    async def _rows_out(
        db: AsyncSession, tenant_id: uuid.UUID, links: list[ParentStudentLink]
    ) -> list[ParentLinkRow]:
        """Serialize links without an N+1: parents, students and classes in bulk."""
        if not links:
            return []
        parent_ids = {row.parent_id for row in links if row.parent_id}
        student_ids = {row.student_id for row in links}
        manager_ids = {row.managed_by for row in links if row.managed_by}

        people: dict[uuid.UUID, User] = {}
        ids = parent_ids | student_ids | manager_ids
        if ids:
            for user in (
                await db.execute(select(User).where(User.id.in_(list(ids))))
            ).scalars():
                people[user.id] = user

        enrollments = await ParentService._current_enrollments(db, tenant_id, list(student_ids))

        out: list[ParentLinkRow] = []
        for row in links:
            parent = people.get(row.parent_id) if row.parent_id else None
            student = people.get(row.student_id)
            manager = people.get(row.managed_by) if row.managed_by else None
            info = enrollments.get(row.student_id)
            out.append(
                ParentLinkRow(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    parent_id=row.parent_id,
                    parent_name=parent.name if parent else None,
                    parent_email=row.parent_email or (parent.email if parent else None),
                    parent_phone=parent.phone if parent else None,
                    parent_is_active=parent.is_active if parent else None,
                    student_id=row.student_id,
                    student_name=student.name if student else "Removed student",
                    student_roll_no=student.student_roll_no if student else None,
                    class_name=info[1].name if info else None,
                    relation=row.relation,
                    is_primary=bool(row.is_primary),
                    status=row.status,
                    access_scope=list(row.access_scope or []),
                    access_upto=row.access_upto,
                    # Shown only while it is still redeemable — the code is a
                    # capability, so it is not returned once access exists.
                    activation_code=(
                        _format_code(row.activation_code)
                        if row.status == LinkStatus.PENDING_CLAIM.value and row.activation_code
                        else None
                    ),
                    code_expires_at=row.code_expires_at,
                    claimed_at=row.claimed_at,
                    note=row.note,
                    managed_by_name=manager.name if manager else None,
                    created_at=row.created_at,
                    updated_at=row.updated_at or row.created_at,
                )
            )
        return out

    @staticmethod
    async def board(
        db: AsyncSession,
        admin: User,
        *,
        query: str | None = None,
        link_status: str = "ALL",
        class_id: uuid.UUID | None = None,
        relation: str | None = None,
        primary_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ParentLinkPage:
        """The C-IA-12 board: links, counts, and the students nobody is linked to."""
        if not 1 <= limit <= 200 or offset < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid pagination")
        tenant = await _tenant(db, admin.tenant_id)

        base = [ParentStudentLink.tenant_id == admin.tenant_id]
        if link_status in {member.value for member in LinkStatus}:
            base.append(ParentStudentLink.status == link_status)
        if relation:
            base.append(func.lower(ParentStudentLink.relation) == relation.strip().lower())
        if primary_only:
            base.append(ParentStudentLink.is_primary.is_(True))
        if class_id is not None:
            base.append(
                ParentStudentLink.student_id.in_(
                    select(Enrollment.student_id).where(
                        Enrollment.tenant_id == admin.tenant_id,
                        Enrollment.class_id == class_id,
                        Enrollment.status == "ACTIVE",
                    )
                )
            )
        if query:
            like = f"%{query.strip().lower()}%"
            base.append(
                or_(
                    func.lower(ParentStudentLink.parent_email).like(like),
                    func.lower(ParentStudentLink.relation).like(like),
                    func.lower(User.name).like(like),
                )
            )

        from_clause = (
            select(ParentStudentLink)
            .outerjoin(User, User.id == ParentStudentLink.parent_id)
            .where(*base)
        )
        total = (
            await db.execute(
                select(func.count()).select_from(from_clause.subquery())
            )
        ).scalar_one()
        links = list(
            (
                await db.execute(
                    from_clause.order_by(
                        ParentStudentLink.status,
                        ParentStudentLink.created_at.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )

        counts_rows = (
            await db.execute(
                select(ParentStudentLink.status, func.count(ParentStudentLink.id))
                .where(ParentStudentLink.tenant_id == admin.tenant_id)
                .group_by(ParentStudentLink.status)
            )
        ).all()
        counts = {row[0]: int(row[1] or 0) for row in counts_rows}
        counts["total"] = int(total or 0)

        # Students with no guardian at all. A school measures this as "unlinked",
        # so it is answered by the database rather than by paging through the
        # board; capped because the admin only needs to see the gap, not export
        # the roster.
        linked_students = select(ParentStudentLink.student_id).where(
            ParentStudentLink.tenant_id == admin.tenant_id
        )
        # `notin_` rather than an anti-join: on Postgres a NOT IN over a
        # non-nullable subquery is planned as an anti-hash-join anyway, and it
        # keeps the predicate readable in one place.
        unlinked_where = [
            User.tenant_id == admin.tenant_id,
            User.deleted_at.is_(None),
            Role.name == "STUDENT",
            User.id.notin_(linked_students),
        ]
        unlinked_total = (
            await db.execute(
                select(func.count(distinct(User.id)))
                .join(
                    RoleAssignment,
                    and_(RoleAssignment.user_id == User.id, RoleAssignment.tenant_id == admin.tenant_id),
                )
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(*unlinked_where)
            )
        ).scalar_one()
        # The metric is the whole gap; the list is the next twenty to work through,
        # with the class attached because that is who the office calls first.
        unlinked_rows = (
            await db.execute(
                select(User.id, User.name, User.student_roll_no, SchoolClass.name)
                .join(
                    RoleAssignment,
                    and_(RoleAssignment.user_id == User.id, RoleAssignment.tenant_id == admin.tenant_id),
                )
                .join(Role, Role.id == RoleAssignment.role_id)
                .outerjoin(
                    Enrollment,
                    and_(
                        Enrollment.student_id == User.id,
                        Enrollment.tenant_id == admin.tenant_id,
                        Enrollment.status == "ACTIVE",
                    ),
                )
                .outerjoin(SchoolClass, SchoolClass.id == Enrollment.class_id)
                .where(*unlinked_where)
                .order_by(User.name)
                .limit(20)
            )
        ).all()

        portal_enabled = await ParentService._is_portal_enabled(db, tenant)
        return ParentLinkPage(
            total=int(total or 0),
            limit=limit,
            offset=offset,
            items=await ParentLinkService._rows_out(db, admin.tenant_id, links),
            counts=counts,
            tenant_type=_value(tenant.type) or "SCHOOL",
            portal_enabled=portal_enabled,
            unlinked_count=int(unlinked_total or 0),
            unlinked=[
                {
                    "student_id": str(row[0]),
                    "student_name": row[1],
                    "student_roll_no": row[2],
                    "class_name": row[3],
                }
                for row in dict.fromkeys(unlinked_rows)  # one row per student
            ],
        )

    # ── C-IA-12 admin: create ────────────────────────────────────────────────

    @staticmethod
    async def create_link(
        db: AsyncSession, admin: User, tenant: Tenant, payload: ParentLinkCreate
    ) -> ParentLinkRow:
        """Link a guardian to a student, or invite them and let them claim it.

        Three shapes, one endpoint, because the admin's form decides which it is:
        an existing parent account is attached directly; an email becomes a
        PENDING_CLAIM invite behind a code; `create_account` makes the login now
        and posts a reset link, the same way staff invites work.
        """
        portal_enabled = await ParentService._is_portal_enabled(db, tenant)
        if not portal_enabled:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "Guardian portal is not enabled in this institution's subscription plan. "
                    "Upgrade your plan or enable the Parent Portal module to create guardian links."
                ),
            )
        child = (
            await db.execute(
                select(User).where(
                    User.id == payload.student_id,
                    User.tenant_id == tenant.id,
                    User.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
        is_student = (
            await db.execute(
                select(RoleAssignment.id)
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(
                    RoleAssignment.user_id == child.id,
                    RoleAssignment.tenant_id == tenant.id,
                    Role.name == "STUDENT",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if is_student is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This user is not enrolled as a student",
            )
        if not payload.parent_user_id and not payload.email:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide either an existing parent account or an email to invite",
            )
        if payload.parent_user_id and payload.email:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Choose one of parent_user_id or email, not both",
            )

        # A second slip for a family that already holds access is a mis-click, not
        # a new relationship — adding "Father" twice, or re-inviting the address
        # that claimed a link last term. Checked here rather than left to the
        # indexes, which only compare pending-with-pending and account-with-account
        # and so let a pending invite sit next to that guardian's active link.
        same_guardian = []
        if payload.parent_user_id:
            same_guardian.append(ParentStudentLink.parent_id == payload.parent_user_id)
        if payload.email:
            same_guardian.append(
                func.lower(ParentStudentLink.parent_email) == payload.email.strip().lower()
            )
        clash = (
            await db.execute(
                select(ParentStudentLink.status)
                .where(
                    ParentStudentLink.tenant_id == tenant.id,
                    ParentStudentLink.student_id == child.id,
                    or_(*same_guardian),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "That guardian is already linked to this student "
                    f"({clash.replace('_', ' ').lower()}) — edit the existing "
                    "link instead of adding another"
                ),
            )

        # `None` means "the school default, which is everything"; `[]` means the
        # office unticked every box. Those are opposite intentions and the previous
        # `payload.access_scope or DEFAULT` read them the same way — so a form
        # submitted with nothing selected granted full access, which is the single
        # most dangerous way this feature could fail.
        if payload.access_scope is None:
            scope = list(DEFAULT_PARENT_ACCESS_SCOPE)
        else:
            scope = list(dict.fromkeys(payload.access_scope))
            if not scope:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "A guardian link with no modules grants nothing — pick at "
                        "least one, or leave access_scope unset for the school default"
                    ),
                )
        unknown = set(scope) - set(PARENT_ACCESS_MODULES)
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown access modules: {', '.join(sorted(unknown))}",
            )

        link_row = ParentStudentLink(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            student_id=child.id,
            relation=payload.relation.strip(),
            is_primary=payload.is_primary,
            access_scope=scope,
            access_upto=payload.access_upto,
            note=payload.note,
            managed_by=admin.id,
        )

        if payload.parent_user_id:
            parent = (
                await db.execute(
                    select(User).where(
                        User.id == payload.parent_user_id,
                        User.tenant_id == tenant.id,
                        User.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if parent is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Parent account not found")
            await ParentLinkService._ensure_parent_role(db, parent, admin)
            link_row.parent_id = parent.id
            link_row.parent_email = parent.email
            link_row.status = LinkStatus.ACTIVE.value
            link_row.claimed_at = datetime.now(timezone.utc)
        elif payload.create_account:
            parent = await ParentLinkService._create_guardian_account(db, tenant, admin, payload)
            link_row.parent_id = parent.id
            link_row.parent_email = parent.email
            link_row.status = LinkStatus.ACTIVE.value
            link_row.claimed_at = datetime.now(timezone.utc)
        else:
            # Nobody to authorise yet: the row waits, and the code is the only
            # thing that turns it into access.
            link_row.parent_email = payload.email.strip().lower()
            link_row.status = LinkStatus.PENDING_CLAIM.value
            link_row.activation_code = _new_activation_code()
            link_row.code_expires_at = datetime.now(timezone.utc) + timedelta(days=CODE_VALID_DAYS)

        # A primary link is demoted-then-inserted, never inserted-then-demoted:
        # `uq_parent_student_links_primary_active` allows one live primary per
        # student, so writing the newcomer first aborts the transaction before
        # the demotion can run. The row is not in the session yet, which is also
        # what keeps the UPDATE below from autoflushing it half-written.
        if link_row.is_primary and link_row.status == LinkStatus.ACTIVE.value:
            await ParentLinkService._demote_other_primaries(db, link_row)

        db.add(link_row)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise _integrity_conflict(
                exc,
                fallback="That guardian is already linked to this student",
                tenant_id=tenant.id,
            ) from exc

        if payload.send_email:
            await ParentLinkService._queue_guardian_email(db, tenant, link_row, child)
        await db.flush()

        AuditService.record(
            db,
            actor=admin,
            actor_role="INSTITUTION_ADMIN",
            action="CREATE_GUARDIAN_LINK",
            entity="ParentStudentLink",
            entity_id=link_row.id,
            tenant_id=tenant.id,
            new_value={
                "student_id": str(child.id),
                "relation": link_row.relation,
                "status": link_row.status,
                "is_primary": link_row.is_primary,
                "access_scope": scope,
                "create_account": bool(payload.create_account),
            },
        )
        logger.info(
            "guardian link created",
            extra={
                "event": "parent.link.created",
                "tenant_id": str(tenant.id),
                "student_id": str(child.id),
                "status": link_row.status,
            },
        )
        return (await ParentLinkService._rows_out(db, tenant.id, [link_row]))[0]

    @staticmethod
    async def _ensure_parent_role(db: AsyncSession, parent: User, admin: User) -> None:
        """Grant PARENT if the account somehow lacks it, or the link is inert."""
        role = await _role_by_name(db, "PARENT")
        if role is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The Parent role is not available for this institution yet",
            )
        held = (
            await db.execute(
                select(RoleAssignment.id).where(
                    RoleAssignment.user_id == parent.id,
                    RoleAssignment.role_id == role.id,
                    RoleAssignment.tenant_id == parent.tenant_id,
                    RoleAssignment.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if held is not None:
            return
        db.add(
            RoleAssignment(
                id=uuid.uuid4(),
                user_id=parent.id,
                role_id=role.id,
                tenant_id=parent.tenant_id,
                assigned_at=datetime.now(timezone.utc),
                is_active=True,
                assigned_by=admin.id,
            )
        )
        await db.flush()

    @staticmethod
    async def _create_guardian_account(
        db: AsyncSession, tenant: Tenant, admin: User, payload: ParentLinkCreate
    ) -> User:
        """Provision a login for the guardian, mirroring the staff-invite shape.

        The password is the institution's default plus a forced reset, exactly
        as `invite_staff` does: the office is vouching for the identity, the
        guardian picks the secret. Same trade-off, so the same rule — and the
        reset token is hashed, never mailed in the clear.
        """
        from app.services.institution_service import DEFAULT_STAFF_PASSWORD

        email = payload.email.strip().lower()
        clash = (
            await db.execute(
                select(User.id).where(User.tenant_id == tenant.id, func.lower(User.email) == email)
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="An account already uses this email — link to it instead of creating one",
            )
        raw_token = generate_secure_token(32)
        parent = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name=payload.parent_name or (email.split("@", 1)[0].replace(".", " ").title() or "Guardian"),
            email=email,
            phone=_normalise_phone(payload.phone),
            password_hash=hash_password(DEFAULT_STAFF_PASSWORD),
            password_reset_token=hash_token(raw_token),
            password_reset_expires=datetime.now(timezone.utc) + timedelta(days=7),
            is_active=True,
        )
        db.add(parent)
        await db.flush()
        await ParentLinkService._ensure_parent_role(db, parent, admin)

        link_url = (
            f"https://{tenant.slug}."
            f"{get_settings().PUBLIC_ROOT_DOMAIN or 'xyz.com'}/reset-password?token={raw_token}"
        )
        queue_email(
            db,
            "staff.invited",
            to=email,
            context={"name": parent.name, "tenant_name": tenant.name, "invite_url": link_url},
            tenant_id=tenant.id,
        )
        return parent

    @staticmethod
    async def _demote_other_primaries(db: AsyncSession, link_row: ParentStudentLink) -> None:
        """Exactly one live primary per child; the index will not allow two."""
        await db.execute(
            ParentStudentLink.__table__.update()
            .where(
                ParentStudentLink.__table__.c.tenant_id == link_row.tenant_id,
                ParentStudentLink.__table__.c.student_id == link_row.student_id,
                ParentStudentLink.__table__.c.id != link_row.id,
                ParentStudentLink.__table__.c.is_primary.is_(True),
                ParentStudentLink.__table__.c.status == LinkStatus.ACTIVE.value,
            )
            .values(is_primary=False, updated_at=func.now())
        )

    @staticmethod
    async def _queue_guardian_email(
        db: AsyncSession, tenant: Tenant, link_row: ParentStudentLink, child: User
    ) -> None:
        """The activation slip, in the guardian's inbox instead of on paper.

        The same code a printed slip would carry. It is written to the outbox in
        plain text because it is a capability the recipient needs; the DB stores
        it plainly too, and both are cleared the moment the link is claimed.
        """
        if not link_row.parent_email:
            return
        root = get_settings().PUBLIC_ROOT_DOMAIN or "xyz.com"
        queue_email(
            db,
            "parent.link_invited",
            to=link_row.parent_email,
            context={
                "tenant_name": tenant.name,
                "student_name": child.name,
                "relation": link_row.relation,
                "code": _format_code(link_row.activation_code or ""),
                # /guardian-access is the public activation page. Deliberately not a
                # route under /parent (that whole tree sits behind a session) and
                # deliberately without ?code= — a query string ends up in browser
                # history and in the access log, and this one would carry the
                # capability itself. The code travels in the body of this email only.
                "claim_url": f"https://{tenant.slug}.{root}/guardian-access",
                "days": CODE_VALID_DAYS,
            },
            tenant_id=tenant.id,
        )

    # ── C-IA-12 admin: change ────────────────────────────────────────────────

    @staticmethod
    async def _load(db: AsyncSession, tenant_id: uuid.UUID, link_id: uuid.UUID) -> ParentStudentLink:
        row = (
            await db.execute(
                select(ParentStudentLink)
                .where(
                    ParentStudentLink.id == link_id,
                    ParentStudentLink.tenant_id == tenant_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Guardian link not found")
        return row

    @staticmethod
    async def update_link(
        db: AsyncSession, admin: User, link_id: uuid.UUID, payload: ParentLinkUpdate
    ) -> ParentLinkRow:
        link_row = await ParentLinkService._load(db, admin.tenant_id, link_id)
        before = {
            "relation": link_row.relation,
            "is_primary": link_row.is_primary,
            "status": link_row.status,
            "access_scope": list(link_row.access_scope or []),
            "access_upto": str(link_row.access_upto) if link_row.access_upto else None,
            "note": link_row.note,
        }
        changed: dict[str, object] = {}

        if payload.relation is not None and payload.relation != link_row.relation:
            changed["relation"] = link_row.relation
            link_row.relation = payload.relation
        if payload.access_scope is not None:
            scope = list(dict.fromkeys(payload.access_scope))
            if not scope:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A guardian link with no modules grants nothing — pick at least one",
                )
            changed["access_scope"] = before["access_scope"]
            link_row.access_scope = scope
        if payload.access_upto is not None:
            if payload.access_upto < date.today():
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="access_upto must be today or later (or clear it)",
                )
            changed["access_upto"] = before["access_upto"]
            link_row.access_upto = payload.access_upto
        if payload.note is not None:
            changed["note"] = link_row.note
            link_row.note = payload.note or None
        if payload.status is not None and payload.status != link_row.status:
            if link_row.status == LinkStatus.PENDING_CLAIM.value:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        "This invite has not been claimed yet — reissue the code "
                        "or delete it instead"
                    ),
                )
            changed["status"] = link_row.status
            link_row.status = payload.status
        if payload.is_primary is not None and payload.is_primary != bool(link_row.is_primary):
            if payload.is_primary and link_row.status != LinkStatus.ACTIVE.value:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Only an active guardian can be the primary contact",
                )
            changed["is_primary"] = link_row.is_primary
            link_row.is_primary = payload.is_primary

        if not changed:
            return (await ParentLinkService._rows_out(db, admin.tenant_id, [link_row]))[0]

        # Whoever ends up the live primary has to clear the field first, and that
        # includes a *resume*: suspending a primary releases the slot, so another
        # guardian may have taken it in the meantime, and flipping the status back
        # without checking would collide with them.
        if link_row.is_primary and link_row.status == LinkStatus.ACTIVE.value:
            await ParentLinkService._demote_other_primaries(db, link_row)

        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise _integrity_conflict(
                exc,
                fallback="Another active primary guardian already exists for this student",
                tenant_id=admin.tenant_id,
            ) from exc

        AuditService.record(
            db,
            actor=admin,
            actor_role="INSTITUTION_ADMIN",
            action="UPDATE_GUARDIAN_LINK",
            entity="ParentStudentLink",
            entity_id=link_row.id,
            tenant_id=admin.tenant_id,
            old_value={key: before[key] for key in changed},
            new_value={key: _serialise(getattr(link_row, key)) for key in changed},
        )
        return (await ParentLinkService._rows_out(db, admin.tenant_id, [link_row]))[0]

    @staticmethod
    async def delete_link(db: AsyncSession, admin: User, link_id: uuid.UUID) -> None:
        """Unlink.

        A hard delete, unlike the soft-delete on `users`: this row *is* the
        access grant, so leaving it in place soft-deleted would mean a status
        flag every reader has to remember to check. The history the school may
        want later is the audit row, which keeps the full previous value.
        """
        link_row = await ParentLinkService._load(db, admin.tenant_id, link_id)
        snapshot = {
            "parent_id": str(link_row.parent_id) if link_row.parent_id else None,
            "parent_email": link_row.parent_email,
            "student_id": str(link_row.student_id),
            "relation": link_row.relation,
            "status": link_row.status,
            "is_primary": link_row.is_primary,
            "access_scope": list(link_row.access_scope or []),
        }
        await db.delete(link_row)
        AuditService.record(
            db,
            actor=admin,
            actor_role="INSTITUTION_ADMIN",
            action="DELETE_GUARDIAN_LINK",
            entity="ParentStudentLink",
            entity_id=link_id,
            tenant_id=admin.tenant_id,
            old_value=snapshot,
        )
        logger.info(
            "guardian link deleted",
            extra={"event": "parent.link.deleted", "link_id": str(link_id), "tenant_id": str(admin.tenant_id)},
        )

    @staticmethod
    async def issue_code(db: AsyncSession, admin: User, link_id: uuid.UUID) -> ParentLinkRow:
        """Generate (or regenerate) an activation code and email it.

        A fresh code replaces the old one, so a slip that went into a drawer
        stops working the moment the office decides it should.
        """
        link_row = await ParentLinkService._load(db, admin.tenant_id, link_id)
        if link_row.status == LinkStatus.ACTIVE.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="This guardian has already claimed their access",
            )
        child = (
            await db.execute(select(User).where(User.id == link_row.student_id))
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
        tenant = await _tenant(db, admin.tenant_id)

        link_row.status = LinkStatus.PENDING_CLAIM.value
        link_row.activation_code = _new_activation_code()
        link_row.code_expires_at = datetime.now(timezone.utc) + timedelta(days=CODE_VALID_DAYS)
        link_row.parent_id = None
        link_row.managed_by = admin.id
        await db.flush()
        await ParentLinkService._queue_guardian_email(db, tenant, link_row, child)
        await db.flush()

        AuditService.record(
            db,
            actor=admin,
            actor_role="INSTITUTION_ADMIN",
            action="ISSUE_GUARDIAN_CODE",
            entity="ParentStudentLink",
            entity_id=link_row.id,
            tenant_id=tenant.id,
            new_value={"expires_at": str(link_row.code_expires_at)},
        )
        return (await ParentLinkService._rows_out(db, admin.tenant_id, [link_row]))[0]
