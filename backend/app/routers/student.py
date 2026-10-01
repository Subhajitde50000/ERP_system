"""Student API — C-ST-01 … C-ST-20.

The caller is the scope: no route accepts a student id.  Every response is
filtered through the signed-in student's active enrollment, resolved in the
service on each request.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_tenant_user_student
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.student import (
    APIResponseStudentAssignment,
    APIResponseStudentAssignments,
    APIResponseStudentAttempt,
    APIResponseStudentAttendance,
    APIResponseStudentAttendanceCalendar,
    APIResponseStudentContent,
    APIResponseStudentContents,
    APIResponseStudentDashboard,
    APIResponseStudentEligibleClassmates,
    APIResponseStudentExam,
    APIResponseStudentExamResult,
    APIResponseStudentExams,
    APIResponseStudentFees,
    APIResponseStudentGroup,
    APIResponseStudentGroupInvite,
    APIResponseStudentGroupInvites,
    APIResponseStudentGroupMessage,
    APIResponseStudentGroupResource,
    APIResponseStudentGroupTask,
    APIResponseStudentGroups,
    APIResponseStudentLeave,
    APIResponseStudentLeaves,
    APIResponseStudentNotice,
    APIResponseStudentNotices,
    APIResponseStudentPaper,
    APIResponseStudentProfile,
    APIResponseStudentResult,
    APIResponseStudentResults,
    APIResponseStudentScopes,
    APIResponseStudentSubmission,
    APIResponseStudentTabSwitch,
    APIResponseStudentTeamDetail,
    APIResponseStudentTeams,
    APIResponseStudentThread,
    APIResponseStudentThreads,
    APIResponseStudentTimetable,
    StudentAnswerSave,
    StudentGroupCreate,
    StudentGroupInviteIn,
    StudentGroupInviteResponseIn,
    StudentGroupMessageIn,
    StudentGroupResourceIn,
    StudentGroupReuseIn,
    StudentGroupTaskIn,
    StudentGroupTaskUpdateIn,
    StudentLeaveCreate,
    StudentProfileUpdate,
    StudentReplyCreate,
    StudentSubmissionCreate,
    StudentThreadCreate,
    StudentVoteToggle,
)
from app.services.student_service import StudentService

router = APIRouter(prefix="/student", tags=["Student"])


# ── C-ST-01 / C-ST-02 ─────────────────────────────────────────────────────────


@router.get("/dashboard", response_model=APIResponseStudentDashboard)
async def dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.dashboard(db, student), message="Student dashboard loaded")


@router.get("/profile", response_model=APIResponseStudentProfile)
async def profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.profile(db, student), message="Profile loaded")


@router.patch("/profile", response_model=APIResponseStudentProfile)
async def update_profile(
    payload: StudentProfileUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.update_profile(db, student, payload), message="Profile updated")


# ── C-ST-03 … C-ST-05 attendance & leave ──────────────────────────────────────


@router.get("/attendance", response_model=APIResponseStudentAttendance)
async def attendance(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.attendance(db, student), message="Attendance loaded")


@router.get("/attendance/calendar", response_model=APIResponseStudentAttendanceCalendar)
async def attendance_calendar(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    return APIResponse(
        success=True,
        data=await StudentService.attendance_calendar(db, student, month=month),
        message="Attendance calendar loaded",
    )


@router.get("/attendance/leaves", response_model=APIResponseStudentLeaves)
async def leaves(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await StudentService.leaves(db, student, limit=limit, offset=offset),
        message="Leave requests loaded",
    )


@router.post("/attendance/leaves", response_model=APIResponseStudentLeave, status_code=status.HTTP_201_CREATED)
async def apply_leave(
    payload: StudentLeaveCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.apply_leave(db, student, payload), message="Leave request submitted")


@router.post("/attendance/leaves/{leave_id}/cancel", response_model=APIResponseStudentLeave)
async def cancel_leave(
    leave_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.cancel_leave(db, student, leave_id), message="Leave request cancelled")


# ── C-ST-06 timetable ─────────────────────────────────────────────────────────


@router.get("/timetable", response_model=APIResponseStudentTimetable)
async def timetable(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.timetable(db, student), message="Timetable loaded")


# ── C-ST-07 … C-ST-09 examinations ────────────────────────────────────────────


@router.get("/examinations", response_model=APIResponseStudentExams)
async def examinations(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
    when: Literal["upcoming", "completed", "all"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await StudentService.examinations(db, student, when=when, limit=limit, offset=offset),
        message="Examinations loaded",
    )


@router.get("/examinations/{exam_id}", response_model=APIResponseStudentExam)
async def exam_detail(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.exam_detail(db, student, exam_id), message="Exam loaded")


@router.post("/examinations/{exam_id}/attempt", response_model=APIResponseStudentAttempt, status_code=status.HTTP_201_CREATED)
async def start_attempt(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.start_attempt(db, student, exam_id), message="Exam attempt started")


@router.get("/examinations/{exam_id}/attempt/paper", response_model=APIResponseStudentPaper)
async def attempt_paper(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.attempt_paper(db, student, exam_id), message="Exam paper loaded")


@router.put("/examinations/{exam_id}/attempt/answers", response_model=APIResponseStudentPaper)
async def save_answer(
    exam_id: uuid.UUID,
    payload: StudentAnswerSave,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.save_answer(db, student, exam_id, payload), message="Answer saved")


@router.post("/examinations/{exam_id}/attempt/tab-switch", response_model=APIResponseStudentTabSwitch)
async def record_tab_switch(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.record_tab_switch(db, student, exam_id),
        message="Tab switch recorded",
    )


@router.post("/examinations/{exam_id}/attempt/submit", response_model=APIResponseStudentAttempt)
async def submit_attempt(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.submit_attempt(db, student, exam_id), message="Exam submitted")


@router.get("/examinations/{exam_id}/result", response_model=APIResponseStudentExamResult)
async def exam_result(
    exam_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.exam_result(db, student, exam_id), message="Exam result loaded")


# ── C-ST-10 … C-ST-12 assignments ─────────────────────────────────────────────


@router.get("/assignments", response_model=APIResponseStudentAssignments)
async def assignments(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await StudentService.assignments(db, student, status_filter=status_filter, limit=limit, offset=offset),
        message="Assignments loaded",
    )


@router.get("/assignments/{assignment_id}", response_model=APIResponseStudentAssignment)
async def assignment_detail(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.assignment_detail(db, student, assignment_id),
        message="Assignment loaded",
    )


@router.post("/assignments/{assignment_id}/submit", response_model=APIResponseStudentSubmission, status_code=status.HTTP_201_CREATED)
async def submit_assignment(
    assignment_id: uuid.UUID,
    payload: StudentSubmissionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.submit_assignment(db, student, assignment_id, payload),
        message="Assignment submitted",
    )


# ── Group project workflows (Student) ───────────────────────────────────


@router.get("/assignments/{assignment_id}/groups", response_model=APIResponseStudentGroups)
async def assignment_groups(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.assignment_groups(db, student, assignment_id),
        message="Assignment groups loaded",
    )


@router.post("/assignments/{assignment_id}/groups", response_model=APIResponseStudentGroup, status_code=status.HTTP_201_CREATED)
async def create_group(
    assignment_id: uuid.UUID,
    payload: StudentGroupCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.create_group(db, student, assignment_id, payload),
        message="Group created",
    )


@router.post("/assignments/{assignment_id}/groups/reuse", response_model=APIResponseStudentGroup, status_code=status.HTTP_201_CREATED)
async def reuse_group(
    assignment_id: uuid.UUID,
    payload: StudentGroupReuseIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.reuse_previous_group(db, student, assignment_id, payload),
        message="Previous group reused",
    )


@router.post("/assignments/{assignment_id}/groups/{group_id}/join", response_model=APIResponseStudentGroup)
async def join_group(
    assignment_id: uuid.UUID,
    group_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.join_group(db, student, assignment_id, group_id),
        message="Joined group",
    )


@router.post("/assignments/{assignment_id}/groups/leave")
async def leave_group(
    assignment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    await StudentService.leave_group(db, student, assignment_id)
    return APIResponse(success=True, data={"message": "Left group"}, message="Left group")


# ── Team Workspace & Collaboration Facilities ───────────────────────────────

@router.get("/teams", response_model=APIResponseStudentTeams)
async def list_my_teams(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.list_my_teams(db, student),
        message="My teams loaded",
    )


@router.get("/teams/{group_id}", response_model=APIResponseStudentTeamDetail)
async def get_team_workspace(
    group_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.get_team_workspace(db, student, group_id),
        message="Team workspace loaded",
    )


@router.post("/teams/{group_id}/tasks", response_model=APIResponseStudentGroupTask, status_code=status.HTTP_201_CREATED)
async def create_team_task(
    group_id: uuid.UUID,
    payload: StudentGroupTaskIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.create_team_task(db, student, group_id, payload),
        message="Task created",
    )


@router.patch("/teams/{group_id}/tasks/{task_id}", response_model=APIResponseStudentGroupTask)
async def update_team_task(
    group_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: StudentGroupTaskUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.update_team_task(db, student, group_id, task_id, payload),
        message="Task updated",
    )


@router.delete("/teams/{group_id}/tasks/{task_id}", response_model=APIResponse)
async def delete_team_task(
    group_id: uuid.UUID,
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    await StudentService.delete_team_task(db, student, group_id, task_id)
    return APIResponse(success=True, data=None, message="Task deleted")


@router.post("/teams/{group_id}/messages", response_model=APIResponseStudentGroupMessage, status_code=status.HTTP_201_CREATED)
async def post_team_message(
    group_id: uuid.UUID,
    payload: StudentGroupMessageIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.post_team_message(db, student, group_id, payload),
        message="Message posted",
    )


@router.post("/teams/{group_id}/resources", response_model=APIResponseStudentGroupResource, status_code=status.HTTP_201_CREATED)
async def add_team_resource(
    group_id: uuid.UUID,
    payload: StudentGroupResourceIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.add_team_resource(db, student, group_id, payload),
        message="Resource added",
    )


@router.delete("/teams/{group_id}/resources/{resource_id}", response_model=APIResponse)
async def delete_team_resource(
    group_id: uuid.UUID,
    resource_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    await StudentService.delete_team_resource(db, student, group_id, resource_id)
    return APIResponse(success=True, data=None, message="Resource deleted")


@router.get("/teams/{group_id}/eligible-members", response_model=APIResponseStudentEligibleClassmates)
async def list_eligible_classmates_to_invite(
    group_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.list_eligible_classmates_to_invite(db, student, group_id),
        message="Eligible classmates loaded",
    )


@router.post("/teams/{group_id}/invitations", response_model=APIResponseStudentGroupInvite, status_code=status.HTTP_201_CREATED)
async def invite_team_member(
    group_id: uuid.UUID,
    payload: StudentGroupInviteIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.invite_team_member(db, student, group_id, payload),
        message="Invitation sent",
    )


@router.delete("/teams/{group_id}/invitations/{invite_id}", response_model=APIResponse)
async def cancel_team_invitation(
    group_id: uuid.UUID,
    invite_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    await StudentService.cancel_team_invitation(db, student, group_id, invite_id)
    return APIResponse(success=True, data=None, message="Invitation cancelled")


@router.get("/invitations", response_model=APIResponseStudentGroupInvites)
async def list_my_team_invitations(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.list_my_team_invitations(db, student),
        message="My invitations loaded",
    )


@router.post("/invitations/{invite_id}/respond", response_model=APIResponse)
async def respond_to_team_invitation(
    invite_id: uuid.UUID,
    payload: StudentGroupInviteResponseIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    msg = await StudentService.respond_to_team_invitation(db, student, invite_id, payload)
    return APIResponse(success=True, data=None, message=msg)


# ── C-ST-13 / C-ST-14 content ─────────────────────────────────────────────────


@router.get("/content", response_model=APIResponseStudentContents)
async def content(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
    subject_id: uuid.UUID | None = Query(default=None),
    chapter: str | None = Query(default=None, max_length=100),
    content_type: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await StudentService.content(
            db, student, subject_id=subject_id, chapter=chapter,
            content_type=content_type, query=query, limit=limit, offset=offset,
        ),
        message="Content loaded",
    )


@router.get("/content/{content_id}", response_model=APIResponseStudentContent)
async def content_detail(
    content_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.content_detail(db, student, content_id), message="Content loaded")


# ── C-ST-15 … C-ST-17 results ─────────────────────────────────────────────────


@router.get("/results", response_model=APIResponseStudentResults)
async def results(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.results(db, student), message="Results loaded")


@router.get("/results/{publication_id}", response_model=APIResponseStudentResult)
async def result_detail(
    publication_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.result_detail(db, student, publication_id),
        message="Result loaded",
    )


@router.get("/results/{publication_id}/grade-card", response_model=APIResponseStudentResult)
async def grade_card(
    publication_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    """C-ST-17 — the printable grade card payload for a published result."""
    return APIResponse(
        success=True,
        data=await StudentService.result_detail(db, student, publication_id),
        message="Grade card loaded",
    )


# ── C-ST-18 notices ───────────────────────────────────────────────────────────


@router.get("/notices", response_model=APIResponseStudentNotices)
async def notices(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await StudentService.notices(db, student, query=query, limit=limit, offset=offset),
        message="Notices loaded",
    )


@router.post("/notices/{notice_id}/read", response_model=APIResponseStudentNotice)
async def mark_notice_read(
    notice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.mark_notice_read(db, student, notice_id), message="Notice marked as read")


# ── C-ST-19 discussion ────────────────────────────────────────────────────────


@router.get("/discussion/scopes", response_model=APIResponseStudentScopes)
async def discussion_scopes(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.discussion_scopes(db, student), message="Discussion scopes loaded")


@router.get("/discussion", response_model=APIResponseStudentThreads)
async def discussion(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
    scope_id: uuid.UUID | None = Query(default=None),
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse(
        success=True,
        data=await StudentService.discussion(db, student, scope_id=scope_id, query=query, limit=limit, offset=offset),
        message="Discussions loaded",
    )


@router.post("/discussion", response_model=APIResponseStudentThread, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: StudentThreadCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.create_thread(db, student, payload), message="Thread created")


@router.get("/discussion/{thread_id}", response_model=APIResponseStudentThread)
async def discussion_detail(
    thread_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(
        success=True,
        data=await StudentService.discussion_detail(db, student, thread_id),
        message="Thread loaded",
    )


@router.post("/discussion/{thread_id}/replies", response_model=APIResponseStudentThread, status_code=status.HTTP_201_CREATED)
async def reply_thread(
    thread_id: uuid.UUID,
    payload: StudentReplyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.reply_thread(db, student, thread_id, payload), message="Reply posted")


@router.post("/discussion/vote", response_model=APIResponseStudentThread)
async def toggle_vote(
    payload: StudentVoteToggle,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.toggle_vote(db, student, payload), message="Vote updated")


# ── C-ST-20 fees ──────────────────────────────────────────────────────────────


@router.get("/fees", response_model=APIResponseStudentFees)
async def fees(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    return APIResponse(success=True, data=await StudentService.fees(db, student), message="Fee account loaded")


# ── Feedback campaigns ─────────────────────────────────────────────────────────

from app.schemas.feedback import APIResponseStudentCampaigns, FeedbackSubmit  # noqa: E402
from app.services.feedback_service import FeedbackService  # noqa: E402


@router.get("/feedback", response_model=APIResponseStudentCampaigns)
async def student_feedback_campaigns(
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    """List all active feedback campaigns with only the teachers the student studies under."""
    data = await FeedbackService.list_active_campaigns_for_student(
        db, student.tenant_id, student.id
    )
    return APIResponse(success=True, data=data, message="Feedback campaigns loaded")


@router.post("/feedback/{campaign_id}/submit", status_code=status.HTTP_201_CREATED)
async def student_submit_feedback(
    campaign_id: uuid.UUID,
    payload: FeedbackSubmit,
    db: Annotated[AsyncSession, Depends(get_db)],
    student: Annotated[User, Depends(get_current_tenant_user_student)],
):
    """Submit feedback for one teacher in a campaign. One submission per teacher per campaign."""
    await FeedbackService.submit_feedback(db, student.tenant_id, student.id, campaign_id, payload)
    return APIResponse(success=True, data=None, message="Feedback submitted successfully")
