"""Mentor console (``/mentor/*``) — everything a mentor sees about their mentees.

Scope is *derived*, never supplied: ``MentorScopeService.resolve`` turns the
caller's ACTIVE ``mentor_assignments`` for the current academic year into the
distinct set of students they may read (direct students ∪ members of their
teams ∪ active roster of their classes).  Every read below is fenced by that
set, so revoking an assignment removes access immediately.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.academic import AcademicYear, Department, SchoolClass, Subject
from app.models.billing import TenantSetting
from app.models.enrollment import Enrollment
from app.models.hod import (
    Assignment,
    AssignmentStatus,
    AttendanceRecord,
    MentorAssignment,
    MentorNote,
    MentorScopeType,
    Submission,
)
from app.models.lms import AttendanceLeave, ProjectGroup, ProjectGroupMember, ProjectGroupMessage, ProjectGroupResource, ProjectGroupTask
from app.models.parent import LinkStatus, ParentStudentLink
from app.models.principal import (
    AttendanceSession,
    AttendanceStatus,
    Exam,
    ExamStatus,
    LeaveStatus,
    Notice,
    NoticeScope,
    ResultPublication,
    StudentResult,
)
from app.models.user import User
from app.schemas.mentor import (
    MenteeSource,
    MentorAttendanceSummary,
    MentorClassRow,
    MentorDashboard,
    MentorExamRow,
    MentorMenteeCoursework,
    MentorMenteeDetail,
    MentorMenteeGuardian,
    MentorMenteeLeave,
    MentorMenteeList,
    MentorMenteeResult,
    MentorMenteeRow,
    MentorNoteCreate,
    MentorNotePage,
    MentorNoteRow,
    MentorNoteUpdate,
    MentorNoticePage,
    MentorSubjectAttendance,
    MentorTeamDetail,
    MentorTeamMember,
    MentorTeamMessage,
    MentorTeamResource,
    MentorTeamRow,
    MentorTeamTask,
)
from app.schemas.principal import LeadershipNoticeRow
from app.services.mentor_assignment_service import MentorAssignmentService, active_enrollment_clause
from app.services.principal_service import PrincipalService, _value

_UPCOMING_EXAM_STATUSES = (ExamStatus.PUBLISHED, ExamStatus.ONGOING)
_VISIBLE_COURSEWORK = (AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED)
_SCOPE_PRIORITY = {MentorScopeType.STUDENT.value: 0, MentorScopeType.TEAM.value: 1, MentorScopeType.CLASS.value: 2}


@dataclass
class AttendanceCounts:
    present: int = 0
    absent: int = 0
    late: int = 0
    excused: int = 0

    @property
    def total(self) -> int:
        return self.present + self.absent + self.late + self.excused

    @property
    def percentage(self) -> float | None:
        # Late and excused still count as attended — matches the HOD/teacher boards.
        return round((self.total - self.absent) * 100 / self.total, 2) if self.total else None

    def summary(self) -> MentorAttendanceSummary:
        return MentorAttendanceSummary(present=self.present, absent=self.absent, late=self.late, excused=self.excused, total=self.total, percentage=self.percentage)


@dataclass
class MenteeInfo:
    student: User
    roll_number: str | None
    class_id: uuid.UUID | None
    class_name: str | None
    department_id: uuid.UUID | None
    department_name: str | None
    sources: list[MenteeSource] = field(default_factory=list)


@dataclass
class MentorScopeState:
    year: AcademicYear | None
    threshold: int | None
    assignments: list[MentorAssignment] = field(default_factory=list)
    students: dict[uuid.UUID, MenteeInfo] = field(default_factory=dict)
    attendance: dict[uuid.UUID, float] = field(default_factory=dict)
    class_names: dict[uuid.UUID, str] = field(default_factory=dict)
    team_names: dict[uuid.UUID, str] = field(default_factory=dict)

    @property
    def class_ids(self) -> list[uuid.UUID]:
        return [a.class_id for a in self.assignments if a.scope_type == MentorScopeType.CLASS.value]

    @property
    def team_ids(self) -> list[uuid.UUID]:
        return [a.team_id for a in self.assignments if a.scope_type == MentorScopeType.TEAM.value]

    @property
    def direct_ids(self) -> list[uuid.UUID]:
        return [a.student_id for a in self.assignments if a.scope_type == MentorScopeType.STUDENT.value]

    @property
    def mentee_class_ids(self) -> set[uuid.UUID]:
        return {info.class_id for info in self.students.values() if info.class_id}

    def is_at_risk(self, student_id: uuid.UUID) -> bool:
        pct = self.attendance.get(student_id)
        return self.threshold is not None and pct is not None and pct < self.threshold

    def require(self, student_id: uuid.UUID) -> MenteeInfo:
        info = self.students.get(student_id)
        if info is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mentee not found in your mentoring scope")
        return info


class MentorScopeService:
    @staticmethod
    async def resolve(
        db: AsyncSession, tenant_id: uuid.UUID, mentor_id: uuid.UUID, year: AcademicYear | None = None, *, threshold: int | None = None
    ) -> MentorScopeState:
        year = year or await MentorAssignmentService.current_year(db, tenant_id)
        if threshold is None:
            threshold = await MentorScopeService._attendance_threshold(db, tenant_id)
        state = MentorScopeState(year=year, threshold=threshold)
        if year is None:
            return state

        state.assignments = list(
            (
                await db.execute(
                    select(MentorAssignment)
                    .where(MentorAssignment.tenant_id == tenant_id, MentorAssignment.mentor_id == mentor_id, MentorAssignment.academic_year_id == year.id, MentorAssignment.is_active.is_(True))
                    .order_by(MentorAssignment.assigned_at.desc())
                )
            ).scalars().all()
        )
        if not state.assignments:
            return state

        sources: dict[uuid.UUID, list[MenteeSource]] = defaultdict(list)
        class_ids, team_ids = state.class_ids, state.team_ids

        if class_ids:
            rows = await db.execute(select(SchoolClass.id, SchoolClass.name).where(SchoolClass.id.in_(class_ids), SchoolClass.tenant_id == tenant_id))
            state.class_names = dict(rows.all())
            roster = await db.execute(
                select(Enrollment.student_id, Enrollment.class_id).where(
                    Enrollment.tenant_id == tenant_id, Enrollment.class_id.in_(class_ids), Enrollment.academic_year_id == year.id, active_enrollment_clause()
                )
            )
            by_class = {a.class_id: a for a in state.assignments if a.scope_type == MentorScopeType.CLASS.value}
            for student_id, class_id in roster.all():
                sources[student_id].append(MenteeSource(assignment_id=by_class[class_id].id, scope_type="CLASS", label=f"Class {state.class_names.get(class_id, '')}".strip()))
        if team_ids:
            rows = await db.execute(select(ProjectGroup.id, ProjectGroup.name).where(ProjectGroup.id.in_(team_ids), ProjectGroup.tenant_id == tenant_id))
            state.team_names = dict(rows.all())
            members = await db.execute(select(ProjectGroupMember.student_id, ProjectGroupMember.group_id).where(ProjectGroupMember.tenant_id == tenant_id, ProjectGroupMember.group_id.in_(team_ids)))
            by_team = {a.team_id: a for a in state.assignments if a.scope_type == MentorScopeType.TEAM.value}
            for student_id, team_id in members.all():
                sources[student_id].append(MenteeSource(assignment_id=by_team[team_id].id, scope_type="TEAM", label=f"Team {state.team_names.get(team_id, '')}".strip()))
        for assignment in state.assignments:
            if assignment.scope_type == MentorScopeType.STUDENT.value:
                sources[assignment.student_id].append(MenteeSource(assignment_id=assignment.id, scope_type="STUDENT", label="Direct mentee"))
        if not sources:
            return state

        people = await db.execute(
            select(User, Enrollment.roll_number, SchoolClass.id, SchoolClass.name, Department.id, Department.name)
            .outerjoin(Enrollment, and_(Enrollment.student_id == User.id, Enrollment.tenant_id == tenant_id, Enrollment.academic_year_id == year.id, active_enrollment_clause()))
            .outerjoin(SchoolClass, SchoolClass.id == Enrollment.class_id)
            .outerjoin(Department, Department.id == SchoolClass.department_id)
            .where(User.id.in_(list(sources)), User.tenant_id == tenant_id, User.deleted_at.is_(None), User.is_active.is_(True))
            .order_by(User.name)
        )
        for user, roll, class_id, class_name, department_id, department_name in people.all():
            if user.id in state.students:
                continue  # a student with two active enrolments keeps the first
            state.students[user.id] = MenteeInfo(
                student=user, roll_number=roll or user.student_roll_no, class_id=class_id, class_name=class_name,
                department_id=department_id, department_name=department_name,
                sources=sorted(sources[user.id], key=lambda s: _SCOPE_PRIORITY[s.scope_type]),
            )
        state.attendance = {sid: pct for sid, counts in (await MentorScopeService.attendance_counts(db, tenant_id, year.id, list(state.students))).items() if (pct := counts.percentage) is not None}
        return state

    @staticmethod
    async def _attendance_threshold(db: AsyncSession, tenant_id: uuid.UUID) -> int | None:
        value = (await db.execute(select(TenantSetting.value).where(TenantSetting.tenant_id == tenant_id, TenantSetting.key == "attendance_threshold"))).scalar_one_or_none()
        try:
            return int(str(value)) if value is not None else None
        except ValueError:
            return None

    @staticmethod
    async def attendance_counts(db: AsyncSession, tenant_id: uuid.UUID, year_id: uuid.UUID, student_ids: list[uuid.UUID], *, subject_id_column=None) -> dict:
        """Per-student (or per student+subject) attendance tallies for the year."""
        if not student_ids:
            return {}
        group_cols = [AttendanceRecord.student_id] + ([subject_id_column] if subject_id_column is not None else [])
        rows = await db.execute(
            select(
                *group_cols,
                func.sum(case((AttendanceRecord.status == AttendanceStatus.PRESENT, 1), else_=0)),
                func.sum(case((AttendanceRecord.status == AttendanceStatus.ABSENT, 1), else_=0)),
                func.sum(case((AttendanceRecord.status == AttendanceStatus.LATE, 1), else_=0)),
                func.sum(case((AttendanceRecord.status == AttendanceStatus.EXCUSED, 1), else_=0)),
            )
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .where(AttendanceRecord.tenant_id == tenant_id, AttendanceSession.academic_year_id == year_id, AttendanceRecord.student_id.in_(student_ids))
            .group_by(*group_cols)
        )
        result: dict = {}
        for row in rows.all():
            key = row[0] if subject_id_column is None else (row[0], row[1])
            offset = 1 if subject_id_column is None else 2
            result[key] = AttendanceCounts(*(int(v or 0) for v in row[offset : offset + 4]))
        return result


class MentorService:
    # ── Row builders ────────────────────────────────────────────────────────

    @staticmethod
    async def _mentee_rows(db: AsyncSession, tenant_id: uuid.UUID, mentor_id: uuid.UUID, state: MentorScopeState, student_ids: list[uuid.UUID]) -> list[MentorMenteeRow]:
        if not student_ids:
            return []
        leaves = dict(
            (
                await db.execute(
                    select(AttendanceLeave.student_id, func.count(AttendanceLeave.id))
                    .where(AttendanceLeave.tenant_id == tenant_id, AttendanceLeave.student_id.in_(student_ids), AttendanceLeave.status == LeaveStatus.PENDING)
                    .group_by(AttendanceLeave.student_id)
                )
            ).all()
        )
        notes = {
            sid: (int(count), last)
            for sid, count, last in (
                await db.execute(
                    select(MentorNote.student_id, func.count(MentorNote.id), func.max(MentorNote.created_at))
                    .where(MentorNote.tenant_id == tenant_id, MentorNote.student_id.in_(student_ids), or_(MentorNote.mentor_id == mentor_id, MentorNote.is_private.is_(False)))
                    .group_by(MentorNote.student_id)
                )
            ).all()
        }
        rows = []
        for sid in student_ids:
            info = state.students[sid]
            note_count, last_note = notes.get(sid, (0, None))
            rows.append(
                MentorMenteeRow(
                    student_id=sid, student_name=info.student.name, roll_number=info.roll_number, email=info.student.email, phone=info.student.phone,
                    avatar_url=info.student.avatar_url, class_id=info.class_id, class_name=info.class_name, department_name=info.department_name,
                    sources=info.sources, attendance_percentage=state.attendance.get(sid), is_at_risk=state.is_at_risk(sid),
                    pending_leave_count=int(leaves.get(sid, 0)), note_count=note_count, last_note_at=last_note,
                )
            )
        return rows

    @staticmethod
    def _note_row(note: MentorNote, author_name: str | None, info: MenteeInfo | None, mentor_id: uuid.UUID) -> MentorNoteRow:
        return MentorNoteRow(
            id=note.id, student_id=note.student_id, student_name=info.student.name if info else "Former mentee", class_name=info.class_name if info else None,
            author_id=note.mentor_id, author_name=author_name, is_own=note.mentor_id == mentor_id, body=note.body, is_private=note.is_private,
            note_date=note.note_date, created_at=note.created_at, updated_at=note.updated_at,
        )

    @staticmethod
    def _visible_notes_clause(mentor_id: uuid.UUID):
        return or_(MentorNote.mentor_id == mentor_id, MentorNote.is_private.is_(False))

    @staticmethod
    async def _notes(db: AsyncSession, tenant_id: uuid.UUID, mentor_id: uuid.UUID, state: MentorScopeState, *, student_ids: list[uuid.UUID], query: str | None = None, limit: int = 20, offset: int = 0) -> tuple[int, list[MentorNoteRow]]:
        if not student_ids:
            return 0, []
        clauses = [MentorNote.tenant_id == tenant_id, MentorNote.student_id.in_(student_ids), MentorService._visible_notes_clause(mentor_id)]
        if query and query.strip():
            clauses.append(func.lower(MentorNote.body).like(f"%{query.strip().lower()}%"))
        total = (await db.execute(select(func.count(MentorNote.id)).where(*clauses))).scalar() or 0
        rows = await db.execute(
            select(MentorNote, User.name).outerjoin(User, User.id == MentorNote.mentor_id).where(*clauses)
            .order_by(MentorNote.note_date.desc(), MentorNote.created_at.desc()).limit(limit).offset(offset)
        )
        return int(total), [MentorService._note_row(note, author, state.students.get(note.student_id), mentor_id) for note, author in rows.all()]

    @staticmethod
    async def _class_rows(db: AsyncSession, tenant_id: uuid.UUID, state: MentorScopeState) -> list[MentorClassRow]:
        class_ids = state.class_ids
        if not class_ids:
            return []
        teacher = aliased(User)
        rows = await db.execute(
            select(SchoolClass, Department.name, teacher.name)
            .join(Department, Department.id == SchoolClass.department_id)
            .outerjoin(teacher, teacher.id == SchoolClass.class_teacher_id)
            .where(SchoolClass.id.in_(class_ids), SchoolClass.tenant_id == tenant_id)
            .order_by(Department.name, SchoolClass.name)
        )
        by_class = {a.class_id: a for a in state.assignments if a.scope_type == MentorScopeType.CLASS.value}
        out = []
        for school_class, department_name, teacher_name in rows.all():
            roster = [sid for sid, info in state.students.items() if any(s.scope_type == "CLASS" and s.assignment_id == by_class[school_class.id].id for s in info.sources)]
            pcts = [state.attendance[sid] for sid in roster if sid in state.attendance]
            out.append(
                MentorClassRow(
                    assignment_id=by_class[school_class.id].id, class_id=school_class.id, class_name=school_class.name, class_code=school_class.code,
                    department_name=department_name, room_no=school_class.room_no, class_teacher_name=teacher_name, student_count=len(roster),
                    average_attendance=round(sum(pcts) / len(pcts), 2) if pcts else None, at_risk_count=sum(1 for sid in roster if state.is_at_risk(sid)),
                    assigned_at=by_class[school_class.id].assigned_at,
                )
            )
        return out

    @staticmethod
    async def _team_rows(db: AsyncSession, tenant_id: uuid.UUID, state: MentorScopeState, *, team_id: uuid.UUID | None = None) -> list[MentorTeamRow]:
        team_ids = [team_id] if team_id else state.team_ids
        if not team_ids or (team_id and team_id not in state.team_ids):
            return []
        rows = (
            await db.execute(
                select(ProjectGroup, Assignment, SchoolClass.name, Subject.name)
                .join(Assignment, Assignment.id == ProjectGroup.assignment_id)
                .join(SchoolClass, SchoolClass.id == Assignment.class_id)
                .outerjoin(Subject, Subject.id == Assignment.subject_id)
                .where(ProjectGroup.id.in_(team_ids), ProjectGroup.tenant_id == tenant_id)
                .order_by(Assignment.due_date.asc())
            )
        ).all()
        sizes = await MentorAssignmentService.team_member_counts(db, tenant_id, team_ids)
        open_tasks = dict(
            (await db.execute(select(ProjectGroupTask.group_id, func.count(ProjectGroupTask.id)).where(ProjectGroupTask.tenant_id == tenant_id, ProjectGroupTask.group_id.in_(team_ids), ProjectGroupTask.status != "DONE").group_by(ProjectGroupTask.group_id))).all()
        )
        latest = {}
        for group_id, sub_status in (
            await db.execute(select(Submission.group_id, Submission.status).where(Submission.tenant_id == tenant_id, Submission.group_id.in_(team_ids)).order_by(Submission.submitted_at.desc()))
        ).all():
            latest.setdefault(group_id, _value(sub_status))
        by_team = {a.team_id: a for a in state.assignments if a.scope_type == MentorScopeType.TEAM.value}
        return [
            MentorTeamRow(
                assignment_id=by_team[group.id].id, team_id=group.id, team_name=group.name, coursework_id=coursework.id, coursework_title=coursework.title,
                coursework_status=_value(coursework.status) or "DRAFT", due_date=coursework.due_date, class_id=coursework.class_id, class_name=class_name,
                subject_name=subject_name, member_count=sizes.get(group.id, 0), submission_status=latest.get(group.id), open_task_count=int(open_tasks.get(group.id, 0)),
                assigned_at=by_team[group.id].assigned_at,
            )
            for group, coursework, class_name, subject_name in rows
        ]

    @staticmethod
    async def _upcoming_exams(db: AsyncSession, tenant_id: uuid.UUID, state: MentorScopeState, class_ids: set[uuid.UUID], *, limit: int = 8) -> list[MentorExamRow]:
        if not class_ids or state.year is None:
            return []
        rows = await db.execute(
            select(Exam, SchoolClass.name, Subject.name)
            .join(SchoolClass, SchoolClass.id == Exam.class_id)
            .outerjoin(Subject, Subject.id == Exam.subject_id)
            .where(Exam.tenant_id == tenant_id, Exam.class_id.in_(list(class_ids)), Exam.academic_year_id == state.year.id, Exam.status.in_(_UPCOMING_EXAM_STATUSES), Exam.scheduled_at >= datetime.now(timezone.utc) - timedelta(hours=6))
            .order_by(Exam.scheduled_at.asc()).limit(limit)
        )
        return [MentorExamRow(id=exam.id, title=exam.title, class_name=class_name, subject_name=subject_name, scheduled_at=exam.scheduled_at, status=_value(exam.status) or "PUBLISHED") for exam, class_name, subject_name in rows.all()]

    # ── Pages ───────────────────────────────────────────────────────────────

    @staticmethod
    async def dashboard(db: AsyncSession, mentor: User) -> MentorDashboard:
        tenant_id = mentor.tenant_id
        state = await MentorScopeService.resolve(db, tenant_id, mentor.id)
        ids = list(state.students)
        pcts = list(state.attendance.values())
        at_risk_ids = sorted((sid for sid in ids if state.is_at_risk(sid)), key=lambda sid: state.attendance[sid])
        month_start = date.today().replace(day=1)
        notes_this_month = 0
        pending_leaves = 0
        if ids:
            notes_this_month = (await db.execute(select(func.count(MentorNote.id)).where(MentorNote.tenant_id == tenant_id, MentorNote.mentor_id == mentor.id, MentorNote.note_date >= month_start))).scalar() or 0
            pending_leaves = (await db.execute(select(func.count(AttendanceLeave.id)).where(AttendanceLeave.tenant_id == tenant_id, AttendanceLeave.student_id.in_(ids), AttendanceLeave.status == LeaveStatus.PENDING))).scalar() or 0
        exams = await MentorService._upcoming_exams(db, tenant_id, state, state.mentee_class_ids)
        _total, recent_notes = await MentorService._notes(db, tenant_id, mentor.id, state, student_ids=ids, limit=5)
        return MentorDashboard(
            academic_year=state.year.name if state.year else None, attendance_threshold=state.threshold,
            mentee_count=len(ids), direct_count=len(state.direct_ids), team_count=len(state.team_ids), class_count=len(state.class_ids),
            average_attendance=round(sum(pcts) / len(pcts), 2) if pcts else None, at_risk_count=len(at_risk_ids), pending_leave_count=int(pending_leaves),
            upcoming_exam_count=len(exams), notes_this_month=int(notes_this_month),
            at_risk_mentees=await MentorService._mentee_rows(db, tenant_id, mentor.id, state, at_risk_ids[:8]),
            recent_notes=recent_notes, upcoming_exams=exams,
            classes=await MentorService._class_rows(db, tenant_id, state), teams=await MentorService._team_rows(db, tenant_id, state),
        )

    @staticmethod
    async def mentees(db: AsyncSession, mentor: User, *, query: str | None = None, class_id: uuid.UUID | None = None, scope: str | None = None, at_risk_only: bool = False) -> MentorMenteeList:
        state = await MentorScopeService.resolve(db, mentor.tenant_id, mentor.id)
        needle = query.strip().casefold() if query else ""
        ids = [
            sid
            for sid, info in state.students.items()
            if (not class_id or info.class_id == class_id)
            and (not scope or any(s.scope_type == scope for s in info.sources))
            and (not at_risk_only or state.is_at_risk(sid))
            and (not needle or needle in info.student.name.casefold() or needle in (info.roll_number or "").casefold() or needle in (info.student.email or "").casefold())
        ]
        rows = await MentorService._mentee_rows(db, mentor.tenant_id, mentor.id, state, ids)
        rows.sort(key=lambda r: (not r.is_at_risk, r.student_name.casefold()))
        return MentorMenteeList(academic_year=state.year.name if state.year else None, attendance_threshold=state.threshold, total=len(rows), items=rows)

    @staticmethod
    async def mentee_detail(db: AsyncSession, mentor: User, student_id: uuid.UUID) -> MentorMenteeDetail:
        tenant_id = mentor.tenant_id
        state = await MentorScopeService.resolve(db, tenant_id, mentor.id)
        info = state.require(student_id)
        year_id = state.year.id
        now = datetime.now(timezone.utc)

        profile = (await MentorService._mentee_rows(db, tenant_id, mentor.id, state, [student_id]))[0]
        overall = (await MentorScopeService.attendance_counts(db, tenant_id, year_id, [student_id])).get(student_id, AttendanceCounts())
        per_subject = await MentorScopeService.attendance_counts(db, tenant_id, year_id, [student_id], subject_id_column=AttendanceSession.subject_id)
        subject_ids = [subject_id for (_sid, subject_id) in per_subject]
        subjects = {s.id: s for s in (await db.execute(select(Subject).where(Subject.id.in_(subject_ids)))).scalars().all()} if subject_ids else {}

        guardian = aliased(User)
        guardians = [
            MentorMenteeGuardian(name=guardian_name, relation=link.relation, phone=guardian_phone, email=guardian_email or link.parent_email, is_primary=link.is_primary)
            for link, guardian_name, guardian_phone, guardian_email in (
                await db.execute(
                    select(ParentStudentLink, guardian.name, guardian.phone, guardian.email)
                    .outerjoin(guardian, guardian.id == ParentStudentLink.parent_id)
                    .where(ParentStudentLink.tenant_id == tenant_id, ParentStudentLink.student_id == student_id, ParentStudentLink.status != LinkStatus.SUSPENDED.value)
                    .order_by(ParentStudentLink.is_primary.desc())
                )
            ).all()
        ]

        results = [
            MentorMenteeResult(
                publication_id=publication.id, title=publication.title, published_at=publication.published_at,
                total_marks_obtained=float(result.total_marks_obtained), total_marks_possible=float(result.total_marks_possible),
                percentage=float(result.percentage), grade=result.grade, rank=result.rank, result=_value(result.result) or "PASS",
            )
            for result, publication in (
                await db.execute(
                    select(StudentResult, ResultPublication)
                    .join(ResultPublication, ResultPublication.id == StudentResult.publication_id)
                    .where(StudentResult.tenant_id == tenant_id, StudentResult.student_id == student_id, or_(ResultPublication.is_visible_to_students.is_(True), ResultPublication.approval_status == "APPROVED"))
                    .order_by(ResultPublication.published_at.desc()).limit(10)
                )
            ).all()
        ]

        coursework: list[MentorMenteeCoursework] = []
        if info.class_id:
            latest_submission = (
                select(Submission.assignment_id, func.max(Submission.submitted_at).label("submitted_at"))
                .where(Submission.tenant_id == tenant_id, Submission.student_id == student_id)
                .group_by(Submission.assignment_id).subquery()
            )
            rows = await db.execute(
                select(Assignment, Subject.name, Submission.status, Submission.score)
                .outerjoin(Subject, Subject.id == Assignment.subject_id)
                .outerjoin(latest_submission, latest_submission.c.assignment_id == Assignment.id)
                .outerjoin(Submission, and_(Submission.assignment_id == Assignment.id, Submission.student_id == student_id, Submission.submitted_at == latest_submission.c.submitted_at))
                .where(Assignment.tenant_id == tenant_id, Assignment.class_id == info.class_id, Assignment.academic_year_id == year_id, Assignment.status.in_(_VISIBLE_COURSEWORK))
                .order_by(Assignment.due_date.desc()).limit(15)
            )
            coursework = [
                MentorMenteeCoursework(
                    id=a.id, title=a.title, subject_name=subject_name, due_date=a.due_date, status=_value(a.status) or "PUBLISHED",
                    submission_status=_value(sub_status), score=float(score) if score is not None else None, is_overdue=sub_status is None and a.due_date < now,
                )
                for a, subject_name, sub_status, score in rows.all()
            ]

        leaves = [
            MentorMenteeLeave(id=leave.id, from_date=leave.from_date, to_date=leave.to_date, reason=leave.reason, status=_value(leave.status) or "PENDING")
            for leave in (
                await db.execute(select(AttendanceLeave).where(AttendanceLeave.tenant_id == tenant_id, AttendanceLeave.student_id == student_id).order_by(AttendanceLeave.from_date.desc()).limit(10))
            ).scalars().all()
        ]
        _total, notes = await MentorService._notes(db, tenant_id, mentor.id, state, student_ids=[student_id], limit=50)
        return MentorMenteeDetail(
            profile=profile, gender=_value(info.student.gender), date_of_birth=info.student.date_of_birth, address=info.student.address, guardians=guardians,
            attendance=overall.summary(),
            subjects=sorted(
                (
                    MentorSubjectAttendance(subject_id=subject_id, subject_code=subjects[subject_id].code, subject_name=subjects[subject_id].name, **counts.summary().model_dump())
                    for (_sid, subject_id), counts in per_subject.items() if subject_id in subjects
                ),
                key=lambda s: s.subject_name.casefold(),
            ),
            results=results, coursework=coursework,
            upcoming_exams=await MentorService._upcoming_exams(db, tenant_id, state, {info.class_id} if info.class_id else set()),
            leaves=leaves, notes=notes,
        )

    @staticmethod
    async def classes(db: AsyncSession, mentor: User) -> list[MentorClassRow]:
        state = await MentorScopeService.resolve(db, mentor.tenant_id, mentor.id)
        return await MentorService._class_rows(db, mentor.tenant_id, state)

    @staticmethod
    async def teams(db: AsyncSession, mentor: User) -> list[MentorTeamRow]:
        state = await MentorScopeService.resolve(db, mentor.tenant_id, mentor.id)
        return await MentorService._team_rows(db, mentor.tenant_id, state)

    @staticmethod
    async def team_detail(db: AsyncSession, mentor: User, team_id: uuid.UUID) -> MentorTeamDetail:
        tenant_id = mentor.tenant_id
        state = await MentorScopeService.resolve(db, tenant_id, mentor.id)
        rows = await MentorService._team_rows(db, tenant_id, state, team_id=team_id)
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project team not found in your mentoring scope")
        team = rows[0]
        members = [
            MentorTeamMember(student_id=user.id, student_name=user.name, roll_number=(state.students[user.id].roll_number if user.id in state.students else user.student_roll_no), attendance_percentage=state.attendance.get(user.id), joined_at=member.joined_at)
            for member, user in (
                await db.execute(select(ProjectGroupMember, User).join(User, User.id == ProjectGroupMember.student_id).where(ProjectGroupMember.group_id == team_id, ProjectGroupMember.tenant_id == tenant_id).order_by(ProjectGroupMember.joined_at.asc()))
            ).all()
        ]
        assignee = aliased(User)
        tasks = [
            MentorTeamTask(id=task.id, title=task.title, status=task.status, assigned_to_name=name, due_date=task.due_date)
            for task, name in (
                await db.execute(select(ProjectGroupTask, assignee.name).outerjoin(assignee, assignee.id == ProjectGroupTask.assigned_to).where(ProjectGroupTask.group_id == team_id, ProjectGroupTask.tenant_id == tenant_id).order_by(ProjectGroupTask.created_at.asc()))
            ).all()
        ]
        resources = [
            MentorTeamResource(id=r.id, title=r.title, url=r.url, resource_type=r.resource_type)
            for r in (await db.execute(select(ProjectGroupResource).where(ProjectGroupResource.group_id == team_id, ProjectGroupResource.tenant_id == tenant_id).order_by(ProjectGroupResource.created_at.desc()))).scalars().all()
        ]
        sender = aliased(User)
        messages = [
            MentorTeamMessage(id=m.id, sender_name=name, message=m.message, created_at=m.created_at)
            for m, name in (
                await db.execute(select(ProjectGroupMessage, sender.name).outerjoin(sender, sender.id == ProjectGroupMessage.sender_id).where(ProjectGroupMessage.group_id == team_id, ProjectGroupMessage.tenant_id == tenant_id).order_by(ProjectGroupMessage.created_at.desc()).limit(20))
            ).all()
        ]
        return MentorTeamDetail(**team.model_dump(), members=members, tasks=tasks, resources=resources, recent_messages=list(reversed(messages)))

    # ── Notes ───────────────────────────────────────────────────────────────

    @staticmethod
    async def notes(db: AsyncSession, mentor: User, *, student_id: uuid.UUID | None = None, query: str | None = None, limit: int = 20, offset: int = 0) -> MentorNotePage:
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid pagination")
        state = await MentorScopeService.resolve(db, mentor.tenant_id, mentor.id)
        ids = [state.require(student_id).student.id] if student_id else list(state.students)
        total, items = await MentorService._notes(db, mentor.tenant_id, mentor.id, state, student_ids=ids, query=query, limit=limit, offset=offset)
        return MentorNotePage(total=total, limit=limit, offset=offset, items=items)

    @staticmethod
    async def create_note(db: AsyncSession, mentor: User, student_id: uuid.UUID, payload: MentorNoteCreate) -> MentorNoteRow:
        state = await MentorScopeService.resolve(db, mentor.tenant_id, mentor.id)
        info = state.require(student_id)
        now = datetime.now(timezone.utc)
        note = MentorNote(
            id=uuid.uuid4(), tenant_id=mentor.tenant_id, mentor_id=mentor.id, student_id=student_id,
            assignment_id=info.sources[0].assignment_id,  # most specific scope: direct → team → class
            body=payload.body.strip(), is_private=payload.is_private, note_date=payload.note_date or date.today(),
            created_at=now, updated_at=now,
        )
        db.add(note)
        await db.flush()
        return MentorService._note_row(note, mentor.name, info, mentor.id)

    @staticmethod
    async def _own_note(db: AsyncSession, mentor: User, note_id: uuid.UUID) -> MentorNote:
        note = (await db.execute(select(MentorNote).where(MentorNote.id == note_id, MentorNote.tenant_id == mentor.tenant_id, MentorNote.mentor_id == mentor.id).with_for_update())).scalar_one_or_none()
        if note is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Note not found")
        return note

    @staticmethod
    async def update_note(db: AsyncSession, mentor: User, note_id: uuid.UUID, payload: MentorNoteUpdate) -> MentorNoteRow:
        note = await MentorService._own_note(db, mentor, note_id)
        if payload.body is not None:
            note.body = payload.body.strip()
        if payload.is_private is not None:
            note.is_private = payload.is_private
        if payload.note_date is not None:
            note.note_date = payload.note_date
        note.updated_at = datetime.now(timezone.utc)
        await db.flush()
        state = await MentorScopeService.resolve(db, mentor.tenant_id, mentor.id)
        return MentorService._note_row(note, mentor.name, state.students.get(note.student_id), mentor.id)

    @staticmethod
    async def delete_note(db: AsyncSession, mentor: User, note_id: uuid.UUID) -> None:
        note = await MentorService._own_note(db, mentor, note_id)
        await db.delete(note)
        await db.flush()

    # ── Notices ─────────────────────────────────────────────────────────────

    @staticmethod
    def _notice_visibility(state: MentorScopeState, tenant_id: uuid.UUID) -> list:
        """Institution-wide ∪ departments of mentee classes ∪ mentee classes; live only."""
        class_ids = list(state.mentee_class_ids)
        department_ids = list({info.department_id for info in state.students.values() if info.department_id})
        now = datetime.now(timezone.utc)
        return [
            Notice.tenant_id == tenant_id, Notice.deleted_at.is_(None), Notice.published_at <= now,
            or_(Notice.expires_at.is_(None), Notice.expires_at > now),
            or_(
                Notice.target_scope == NoticeScope.INSTITUTION,
                and_(Notice.target_scope == NoticeScope.DEPARTMENT, Notice.target_id.in_(department_ids)) if department_ids else false(),
                and_(Notice.target_scope == NoticeScope.CLASS, Notice.target_id.in_(class_ids)) if class_ids else false(),
            ),
        ]

    @staticmethod
    async def notices(db: AsyncSession, mentor: User, *, query: str | None = None, scope: str | None = None, limit: int = 20, offset: int = 0) -> MentorNoticePage:
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid pagination")
        tenant_id = mentor.tenant_id
        state = await MentorScopeService.resolve(db, tenant_id, mentor.id)
        clauses = MentorService._notice_visibility(state, tenant_id)
        if scope:
            clauses.append(Notice.target_scope == NoticeScope(scope))
        if query and query.strip():
            needle = f"%{query.strip().lower()}%"
            clauses.append(or_(func.lower(Notice.title).like(needle), func.lower(Notice.body).like(needle)))
        total = (await db.execute(select(func.count(Notice.id)).where(*clauses))).scalar() or 0
        rows = (
            await db.execute(
                select(Notice, User.name).outerjoin(User, and_(User.id == Notice.author_id, User.tenant_id == tenant_id)).where(*clauses)
                .order_by(Notice.is_pinned.desc(), Notice.published_at.desc()).limit(limit).offset(offset)
            )
        ).all()
        target_names = await PrincipalService._notice_target_names(db, tenant_id, [notice for notice, _ in rows])
        return MentorNoticePage(
            total=int(total), limit=limit, offset=offset,
            items=[MentorService._leadership_row(notice, author, target_names) for notice, author in rows],
        )

    @staticmethod
    def _leadership_row(notice: Notice, author: str | None, target_names: dict) -> LeadershipNoticeRow:
        row = PrincipalService._notice_row(notice, author, 0, target_names.get((_value(notice.target_scope), notice.target_id)))
        return LeadershipNoticeRow.model_validate(row.model_dump(exclude={"read_count"}))

    @staticmethod
    async def notice_detail(db: AsyncSession, mentor: User, notice_id: uuid.UUID) -> LeadershipNoticeRow:
        tenant_id = mentor.tenant_id
        state = await MentorScopeService.resolve(db, tenant_id, mentor.id)
        row = (
            await db.execute(
                select(Notice, User.name).outerjoin(User, and_(User.id == Notice.author_id, User.tenant_id == tenant_id))
                .where(Notice.id == notice_id, *MentorService._notice_visibility(state, tenant_id))
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notice not found")
        notice, author = row
        target_names = await PrincipalService._notice_target_names(db, tenant_id, [notice])
        base = MentorService._leadership_row(notice, author, target_names)
        return LeadershipNoticeRow(**base.model_dump(exclude={"attachments"}), attachments=await PrincipalService._notice_attachments(db, notice.id))
