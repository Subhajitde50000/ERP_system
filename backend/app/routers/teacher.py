"""Teacher API — C-TC-01 … C-TC-22.

Every handler resolves the caller's teaching scope in the service before
querying or mutating anything; route ids alone never widen access to another
teacher's classes, exams, assignments or submissions.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_tenant_user_teacher
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.teacher import (
    APIResponseTeacherAssignment,
    APIResponseTeacherAssignmentList,
    APIResponseTeacherAssignments,
    APIResponseTeacherAttempt,
    APIResponseTeacherAttempts,
    APIResponseTeacherAttendanceBoard,
    APIResponseTeacherAttendanceSession,
    APIResponseTeacherAttendanceSessions,
    APIResponseTeacherContent,
    APIResponseTeacherContents,
    APIResponseTeacherDashboard,
    APIResponseTeacherExam,
    APIResponseTeacherExams,
    APIResponseTeacherGroup,
    APIResponseTeacherGroups,
    APIResponseTeacherLeave,
    APIResponseTeacherLeaves,
    APIResponseTeacherNotice,
    APIResponseTeacherNotices,
    APIResponseTeacherNoticeTargets,
    APIResponseTeacherQuestion,
    APIResponseTeacherQuestionBankItem,
    APIResponseTeacherQuestionBankList,
    APIResponseTeacherReply,
    APIResponseTeacherSchedule,
    APIResponseTeacherSubmission,
    APIResponseTeacherSubmissions,
    APIResponseTeacherTeamWorkspace,
    APIResponseTeacherThread,
    APIResponseTeacherThreads,
    AttendanceSessionUpsert,
    TeacherAssignmentCreate,
    TeacherAssignmentReopen,
    TeacherAssignmentUpdate,
    TeacherContentIn,
    TeacherContentUpdate,
    TeacherExamCreate,
    TeacherExamUpdate,
    TeacherGradeSubmission,
    TeacherLeaveReview,
    TeacherMilestoneIn,
    TeacherMilestoneUpdateIn,
    TeacherNoticeCreate,
    TeacherQuestionBankImportIn,
    TeacherQuestionBankItemIn,
    TeacherQuestionBankItemUpdate,
    TeacherQuestionIn,
    TeacherQuestionUpdate,
    TeacherReplyCreate,
    TeacherSubmissionReviewIn,
    TeacherThreadCreate,
    TeacherThreadModeration,
)
from app.services.teacher_service import TeacherService

router = APIRouter(prefix="/teacher", tags=["Teacher"])


# ── C-TC-01 / C-TC-02 ─────────────────────────────────────────────────────────


@router.get("/dashboard", response_model=APIResponseTeacherDashboard)
async def dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.dashboard(db, teacher), message="Teacher dashboard loaded")


@router.get("/schedule", response_model=APIResponseTeacherSchedule)
async def schedule(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.schedule(db, teacher), message="Teaching schedule loaded")


@router.get("/teaching-assignments", response_model=APIResponseTeacherAssignments)
async def teaching_assignments(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.attendance_options(db, teacher),
        message="Teaching assignments loaded",
    )


# ── C-TC-03 … C-TC-05 attendance ──────────────────────────────────────────────


@router.get("/attendance/board", response_model=APIResponseTeacherAttendanceBoard)
async def attendance_board(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    subject_id: uuid.UUID = Query(...),
    class_id: uuid.UUID = Query(...),
    on: date | None = Query(default=None),
    period_label: str | None = Query(default=None, max_length=30),
):
    return APIResponse(
        success=True,
        data=await TeacherService.attendance_board(
            db, teacher, subject_id=subject_id, class_id=class_id, on=on, period_label=period_label
        ),
        message="Attendance board loaded",
    )


@router.put("/attendance/sessions", response_model=APIResponseTeacherAttendanceSession)
async def save_attendance(
    payload: AttendanceSessionUpsert,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.save_attendance(db, teacher, payload),
        message="Attendance saved",
    )


@router.get("/attendance/sessions", response_model=APIResponseTeacherAttendanceSessions)
async def attendance_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    class_id: uuid.UUID | None = Query(default=None),
    subject_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.attendance_sessions(
            db, teacher, from_date=from_date, to_date=to_date, class_id=class_id, subject_id=subject_id,
            limit=limit, offset=offset,
        ),
        message="Attendance sessions loaded",
    )


@router.get("/attendance/sessions/{session_id}", response_model=APIResponseTeacherAttendanceSession)
async def attendance_session_detail(
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.attendance_session_detail(db, teacher, session_id),
        message="Attendance session loaded",
    )


@router.post("/attendance/sessions/{session_id}/lock", response_model=APIResponseTeacherAttendanceSession)
async def lock_attendance_session(
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.lock_attendance_session(db, teacher, session_id),
        message="Attendance session locked",
    )


# ── C-TC-06 student leaves ────────────────────────────────────────────────────


@router.get("/attendance/leaves", response_model=APIResponseTeacherLeaves)
async def leaves(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.leaves(db, teacher, status_filter=status_filter, limit=limit, offset=offset),
        message="Leave requests loaded",
    )


@router.post("/attendance/leaves/{leave_id}/review", response_model=APIResponseTeacherLeave)
async def review_leave(
    leave_id: uuid.UUID,
    payload: TeacherLeaveReview,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.review_leave(db, teacher, leave_id, payload),
        message=f"Leave request {payload.decision.lower()}",
    )


# ── C-TC-07 … C-TC-11 examinations ────────────────────────────────────────────


@router.get("/examinations", response_model=APIResponseTeacherExams)
async def examinations(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.examinations(db, teacher, status_filter=status_filter, limit=limit, offset=offset),
        message="Examinations loaded",
    )


@router.post("/examinations", response_model=APIResponseTeacherExam, status_code=status.HTTP_201_CREATED)
async def create_exam(
    payload: TeacherExamCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.create_exam(db, teacher, payload), message="Exam created")


@router.get("/examinations/{exam_id}", response_model=APIResponseTeacherExam)
async def exam_detail(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.exam_detail(db, teacher, exam_id), message="Exam loaded")


@router.patch("/examinations/{exam_id}", response_model=APIResponseTeacherExam)
async def update_exam(
    exam_id: uuid.UUID,
    payload: TeacherExamUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.update_exam(db, teacher, exam_id, payload), message="Exam updated")


@router.post("/examinations/{exam_id}/publish", response_model=APIResponseTeacherExam)
async def publish_exam(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.publish_exam(db, teacher, exam_id), message="Exam published")


@router.post("/examinations/{exam_id}/questions", response_model=APIResponseTeacherQuestion, status_code=status.HTTP_201_CREATED)
async def add_question(
    exam_id: uuid.UUID,
    payload: TeacherQuestionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.add_question(db, teacher, exam_id, payload), message="Question added")


@router.patch("/examinations/{exam_id}/questions/{question_id}", response_model=APIResponseTeacherQuestion)
async def update_question(
    exam_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: TeacherQuestionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.update_question(db, teacher, exam_id, question_id, payload),
        message="Question updated",
    )


@router.delete("/examinations/{exam_id}/questions/{question_id}", response_model=APIResponseTeacherExam)
async def delete_question(
    exam_id: uuid.UUID,
    question_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.delete_question(db, teacher, exam_id, question_id),
        message="Question deleted",
    )


@router.post("/examinations/{exam_id}/import-questions", response_model=APIResponseTeacherExam)
async def import_questions_from_bank(
    exam_id: uuid.UUID,
    payload: TeacherQuestionBankImportIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.import_questions_from_bank(db, teacher, exam_id, payload),
        message="Questions imported from Question Bank",
    )


@router.get("/question-bank", response_model=APIResponseTeacherQuestionBankList)
async def list_question_bank(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    subject_id: uuid.UUID | None = Query(default=None),
    question_type: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.list_question_bank(
            db,
            teacher,
            subject_id=subject_id,
            question_type=question_type,
            difficulty=difficulty,
            search=search,
            limit=limit,
            offset=offset,
        ),
        message="Question bank loaded",
    )


@router.post("/question-bank", response_model=APIResponseTeacherQuestionBankItem, status_code=status.HTTP_201_CREATED)
async def create_question_bank_item(
    payload: TeacherQuestionBankItemIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.create_question_bank_item(db, teacher, payload),
        message="Question added to Question Bank",
    )


@router.patch("/question-bank/{item_id}", response_model=APIResponseTeacherQuestionBankItem)
async def update_question_bank_item(
    item_id: uuid.UUID,
    payload: TeacherQuestionBankItemUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.update_question_bank_item(db, teacher, item_id, payload),
        message="Question bank item updated",
    )


@router.delete("/question-bank/{item_id}", response_model=APIResponse[dict])
async def delete_question_bank_item(
    item_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    await TeacherService.delete_question_bank_item(db, teacher, item_id)
    return APIResponse(success=True, data={"id": str(item_id)}, message="Question deleted from Question Bank")


@router.get("/question-bank/export")
async def export_question_bank(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    fmt: Literal["csv", "json"] = Query(default="csv"),
    subject_id: uuid.UUID | None = Query(default=None),
    question_type: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    search: str | None = Query(default=None),
):
    """Download the teacher's question bank as a CSV or JSON file."""
    file_bytes, filename, media_type = await TeacherService.export_question_bank(
        db,
        teacher,
        fmt=fmt,
        subject_id=subject_id,
        question_type=question_type,
        difficulty=difficulty,
        search=search,
    )
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/question-bank/import-file", response_model=APIResponse[dict])
async def import_question_bank_file(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    file: UploadFile = File(...),
):
    """Upload a CSV or JSON file to bulk-import questions into the question bank."""
    content = await file.read()
    result = await TeacherService.import_question_bank_file(
        db,
        teacher,
        filename=file.filename or "upload",
        content=content,
    )
    imported = result["imported"]
    return APIResponse(
        success=True,
        data=result,
        message=f"{imported} question{'s' if imported != 1 else ''} imported successfully.",
    )


@router.get("/examinations/{exam_id}/attempts", response_model=APIResponseTeacherAttempts)
async def exam_attempts(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.exam_attempts(db, teacher, exam_id, limit=limit, offset=offset),
        message="Exam attempts loaded",
    )


@router.get("/examinations/{exam_id}/attempts/{attempt_id}", response_model=APIResponseTeacherAttempt)
async def attempt_detail(
    exam_id: uuid.UUID,
    attempt_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.attempt_detail(db, teacher, exam_id, attempt_id),
        message="Exam attempt loaded",
    )


@router.post("/examinations/{exam_id}/attempts/{attempt_id}/grade", response_model=APIResponseTeacherAttempt)
async def grade_attempt(
    exam_id: uuid.UUID,
    attempt_id: uuid.UUID,
    payload: TeacherGradeSubmission,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.grade_answers(db, teacher, exam_id, attempt_id, payload),
        message="Answers graded",
    )


@router.post("/examinations/{exam_id}/release", response_model=APIResponseTeacherExam)
async def release_results(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.release_results(db, teacher, exam_id),
        message="Results released",
    )


# ── C-TC-12 … C-TC-16 assignments ─────────────────────────────────────────────


@router.get("/assignments", response_model=APIResponseTeacherAssignmentList)
async def assignments(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.assignments(db, teacher, status_filter=status_filter, limit=limit, offset=offset),
        message="Assignments loaded",
    )


@router.post("/assignments", response_model=APIResponseTeacherAssignment, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    payload: TeacherAssignmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.create_assignment(db, teacher, payload), message="Assignment created")


@router.get("/assignments/{assignment_id}", response_model=APIResponseTeacherAssignment)
async def assignment_detail(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.assignment_detail(db, teacher, assignment_id), message="Assignment loaded")


@router.patch("/assignments/{assignment_id}", response_model=APIResponseTeacherAssignment)
async def update_assignment(
    assignment_id: uuid.UUID,
    payload: TeacherAssignmentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.update_assignment(db, teacher, assignment_id, payload),
        message="Assignment updated",
    )


@router.post("/assignments/{assignment_id}/publish", response_model=APIResponseTeacherAssignment)
async def publish_assignment(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.transition_assignment(db, teacher, assignment_id, "publish"),
        message="Assignment published",
    )


@router.post("/assignments/{assignment_id}/close", response_model=APIResponseTeacherAssignment)
async def close_assignment(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.transition_assignment(db, teacher, assignment_id, "close"),
        message="Assignment closed",
    )


@router.post("/assignments/{assignment_id}/reopen", response_model=APIResponseTeacherAssignment)
async def reopen_assignment(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    payload: TeacherAssignmentReopen | None = None,
):
    """Reopen a closed assignment.

    By default the reopen also asks students with un-reviewed submissions to
    review and resubmit (their latest submission becomes RESUBMIT_REQUESTED).
    Send ``{"request_resubmission": false}`` to reopen only for students who
    never submitted.
    """
    request_resubmission = True if payload is None else payload.request_resubmission
    return APIResponse(
        success=True,
        data=await TeacherService.transition_assignment(
            db, teacher, assignment_id, "reopen", request_resubmission=request_resubmission
        ),
        message="Assignment reopened",
    )


@router.post("/assignments/{assignment_id}/milestones", response_model=APIResponseTeacherAssignment, status_code=status.HTTP_201_CREATED)
async def add_milestone(
    assignment_id: uuid.UUID,
    payload: TeacherMilestoneIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.add_milestone(db, teacher, assignment_id, payload),
        message="Milestone added",
    )


@router.delete("/assignments/{assignment_id}/milestones/{milestone_id}", response_model=APIResponseTeacherAssignment)
async def delete_milestone(
    assignment_id: uuid.UUID,
    milestone_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.delete_milestone(db, teacher, assignment_id, milestone_id),
        message="Milestone removed",
    )


@router.patch("/assignments/{assignment_id}/milestones/{milestone_id}", response_model=APIResponseTeacherAssignment)
async def update_milestone(
    assignment_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: TeacherMilestoneUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.update_milestone(db, teacher, assignment_id, milestone_id, payload),
        message="Milestone updated",
    )


# ── Group project management ─────────────────────────────────────────────


@router.get("/assignments/{assignment_id}/groups", response_model=APIResponseTeacherGroups)
async def list_assignment_groups(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.list_assignment_groups(db, teacher, assignment_id, limit=limit, offset=offset),
        message="Assignment groups loaded",
    )


@router.get("/assignments/{assignment_id}/groups/{group_id}", response_model=APIResponseTeacherGroup)
async def get_assignment_group(
    assignment_id: uuid.UUID,
    group_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.get_assignment_group(db, teacher, assignment_id, group_id),
        message="Assignment group loaded",
    )


@router.delete("/assignments/{assignment_id}/groups/{group_id}/members/{student_id}", response_model=APIResponseTeacherGroup)
async def remove_student_from_group(
    assignment_id: uuid.UUID,
    group_id: uuid.UUID,
    student_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.remove_student_from_group(db, teacher, assignment_id, group_id, student_id),
        message="Student removed from group",
    )


@router.get("/teams/{group_id}", response_model=APIResponseTeacherTeamWorkspace)
async def get_teacher_team_workspace(
    group_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.get_teacher_team_workspace(db, teacher, group_id),
        message="Teacher team workspace loaded",
    )


@router.get("/submissions", response_model=APIResponseTeacherSubmissions)
async def submissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    assignment_id: uuid.UUID | None = Query(default=None),
    milestone_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.submissions(
            db, teacher, assignment_id=assignment_id, milestone_id=milestone_id,
            status_filter=status_filter, limit=limit, offset=offset,
        ),
        message="Submissions loaded",
    )


@router.get("/submissions/{submission_id}", response_model=APIResponseTeacherSubmission)
async def submission_detail(
    submission_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.submission_detail(db, teacher, submission_id),
        message="Submission loaded",
    )


@router.post("/submissions/{submission_id}/review", response_model=APIResponseTeacherSubmission)
async def review_submission(
    submission_id: uuid.UUID,
    payload: TeacherSubmissionReviewIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.review_submission(db, teacher, submission_id, payload),
        message="Submission reviewed",
    )


# ── C-TC-17 / C-TC-18 content ─────────────────────────────────────────────────


@router.get("/content", response_model=APIResponseTeacherContents)
async def content(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    subject_id: uuid.UUID | None = Query(default=None),
    class_id: uuid.UUID | None = Query(default=None),
    content_type: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.content(
            db, teacher, subject_id=subject_id, class_id=class_id,
            content_type=content_type, query=query, limit=limit, offset=offset,
        ),
        message="Content loaded",
    )


@router.post("/content", response_model=APIResponseTeacherContent, status_code=status.HTTP_201_CREATED)
async def create_content(
    payload: TeacherContentIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.create_content(db, teacher, payload), message="Content uploaded")


@router.patch("/content/{content_id}", response_model=APIResponseTeacherContent)
async def update_content(
    content_id: uuid.UUID,
    payload: TeacherContentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.update_content(db, teacher, content_id, payload),
        message="Content updated",
    )


@router.delete("/content/{content_id}", response_model=APIResponse[None])
async def delete_content(
    content_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    await TeacherService.delete_content(db, teacher, content_id)
    return APIResponse(success=True, data=None, message="Content deleted")


# ── C-TC-19 / C-TC-20 notices ─────────────────────────────────────────────────


@router.get("/notices/targets", response_model=APIResponseTeacherNoticeTargets)
async def notice_targets(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.notice_targets(db, teacher), message="Notice targets loaded")


@router.get("/notices", response_model=APIResponseTeacherNotices)
async def notices(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.notices(db, teacher, query=query, limit=limit, offset=offset),
        message="Notices loaded",
    )


@router.post("/notices", response_model=APIResponseTeacherNotice, status_code=status.HTTP_201_CREATED)
async def create_notice(
    payload: TeacherNoticeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.create_notice(db, teacher, payload), message="Notice published")


@router.get("/notices/{notice_id}", response_model=APIResponseTeacherNotice)
async def notice_detail(
    notice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.notice_detail(db, teacher, notice_id), message="Notice loaded")


# ── C-TC-21 / C-TC-22 discussion ──────────────────────────────────────────────


@router.get("/discussion", response_model=APIResponseTeacherThreads)
async def discussion(
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
    query: str | None = Query(default=None, max_length=100),
    scope_type: Literal["CLASS", "SUBJECT", "DEPARTMENT"] | None = Query(default=None),
    scope_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await TeacherService.discussion(
            db, teacher, query=query, scope_type=scope_type, scope_id=scope_id, limit=limit, offset=offset
        ),
        message="Discussions loaded",
    )


@router.post("/discussion", response_model=APIResponseTeacherThread, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: TeacherThreadCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.create_thread(db, teacher, payload), message="Thread created")


@router.get("/discussion/{thread_id}", response_model=APIResponseTeacherThread)
async def discussion_detail(
    thread_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.discussion_detail(db, teacher, thread_id),
        message="Thread loaded",
    )


@router.post("/discussion/{thread_id}/replies", response_model=APIResponseTeacherReply, status_code=status.HTTP_201_CREATED)
async def reply_thread(
    thread_id: uuid.UUID,
    payload: TeacherReplyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.reply_thread(db, teacher, thread_id, payload), message="Reply posted")


@router.patch("/discussion/{thread_id}", response_model=APIResponseTeacherThread)
async def moderate_thread(
    thread_id: uuid.UUID,
    payload: TeacherThreadModeration,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(
        success=True,
        data=await TeacherService.moderate_thread(db, teacher, thread_id, payload),
        message="Discussion moderation applied",
    )


@router.post("/discussion/replies/{reply_id}/accept", response_model=APIResponseTeacherThread)
async def accept_reply(
    reply_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    teacher: Annotated[User, Depends(get_current_tenant_user_teacher)],
):
    return APIResponse(success=True, data=await TeacherService.accept_reply(db, teacher, reply_id), message="Answer accepted")
