"""Routers — institution admin: people (staff, students, enrollments)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import (
    get_current_tenant_user_admin,
    get_current_tenant_user_student_records_manager,
)
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.institution import (
    APIResponseBulk,
    APIResponseEnrollment,
    APIResponseEnrollments,
    APIResponseStaff,
    APIResponseStaffOne,
    APIResponseStudent,
    APIResponseStudents,
    AssignRoleRequest,
    EnrollmentCreate,
    StaffInvite,
    StaffUpdate,
    StudentCreate,
    StudentUpdate,
)
from app.services.institution_service import BULK_MAX_FILE_BYTES, InstitutionService

router = APIRouter()


async def _tenant(db: AsyncSession, admin: User):
    return await InstitutionService._tenant(db, admin.tenant_id)


# ── Staff / users ────────────────────────────────────────────────────────────

@router.get("/staff", response_model=APIResponseStaff)
async def list_staff(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    return APIResponse(success=True, data=await InstitutionService.list_staff(db, admin.tenant_id), message="Staff loaded")


@router.post("/users/{user_id}/password-reset", response_model=APIResponse[None])
async def resend_password_reset(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    """Send a fresh password-reset link to an active student or staff member."""
    tenant = await _tenant(db, admin)
    await InstitutionService.resend_password_reset(db, tenant, user_id, actor=admin)
    return APIResponse(success=True, data=None, message="Password reset link sent")


@router.post("/staff", response_model=APIResponseStaffOne, status_code=201)
async def invite_staff(
    payload: StaffInvite,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    tenant = await _tenant(db, admin)
    data = await InstitutionService.invite_staff(db, tenant, payload, actor=admin)
    return APIResponse(success=True, data=data, message="Staff invited")


@router.post("/staff/bulk", response_model=APIResponseBulk)
async def bulk_create_staff(
    file: Annotated[UploadFile, File(description="CSV with headers: name, email, phone, role, department_code")],
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    content = await file.read(BULK_MAX_FILE_BYTES + 1)
    if len(content) > BULK_MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large — max 2 MB")
    tenant = await _tenant(db, admin)
    result = await InstitutionService.bulk_create_staff(db, tenant, content)
    return APIResponse(
        success=True,
        data=result,
        message=f"Bulk import finished: {result.created} created, {len(result.errors)} failed",
    )


@router.put("/staff/{user_id}/roles", response_model=APIResponseStaffOne)
async def assign_role(
    user_id: uuid.UUID,
    payload: AssignRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    data = await InstitutionService.assign_role(
        db,
        admin.tenant_id,
        user_id,
        payload.role_name,
        admin,
        department_id=payload.department_id,
    )
    return APIResponse(success=True, data=data, message="Role assigned")


@router.delete("/staff/{user_id}/roles/{role_name}", response_model=APIResponseStaffOne)
async def revoke_role(
    user_id: uuid.UUID,
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
    department_id: uuid.UUID | None = None,
):
    data = await InstitutionService.revoke_role(
        db,
        admin.tenant_id,
        user_id,
        role_name,
        admin,
        department_id=department_id,
    )
    return APIResponse(success=True, data=data, message="Role assignment revoked")


@router.put("/staff/{user_id}/active", response_model=APIResponseStaffOne)
async def set_staff_active(
    user_id: uuid.UUID,
    active: bool,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    data = await InstitutionService.set_user_active(db, admin.tenant_id, user_id, active)
    return APIResponse(success=True, data=data, message="Staff status updated")


@router.put("/staff/{user_id}", response_model=APIResponseStaffOne)
async def update_staff(
    user_id: uuid.UUID,
    payload: StaffUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    data = await InstitutionService.update_staff(db, admin.tenant_id, user_id, payload, actor=admin)
    return APIResponse(success=True, data=data, message="Staff details updated")


@router.delete("/staff/{user_id}", response_model=APIResponse[None])
async def delete_staff(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    await InstitutionService.delete_staff(db, admin.tenant_id, user_id, actor=admin)
    return APIResponse(success=True, data=None, message="Staff deleted")


# ── People: students ─────────────────────────────────────────────────────────

@router.get("/students", response_model=APIResponseStudents)
async def list_students(
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    return APIResponse(success=True, data=await InstitutionService.list_students(db, manager.tenant_id), message="Students loaded")


@router.post("/students", response_model=APIResponseStudent, status_code=201)
async def create_student(
    payload: StudentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    tenant = await _tenant(db, manager)
    data = await InstitutionService.create_student(db, tenant, payload)
    return APIResponse(success=True, data=data, message="Student created")


@router.post("/students/{student_id}/password-reset", response_model=APIResponse[None])
async def resend_student_password_reset(
    student_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    """Allow Academic Coordinators to send a reset link to a student only."""
    tenant = await _tenant(db, manager)
    await InstitutionService.resend_password_reset(
        db,
        tenant,
        student_id,
        actor=manager,
        student_only=True,
        actor_role="ACADEMIC_COORDINATOR",
    )
    return APIResponse(success=True, data=None, message="Password reset link sent")


@router.put("/students/{student_id}", response_model=APIResponseStudent)
async def update_student(
    student_id: uuid.UUID,
    payload: StudentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    return APIResponse(
        success=True,
        data=await InstitutionService.update_student(db, manager.tenant_id, student_id, payload),
        message="Student updated",
    )


@router.delete("/students/{student_id}", response_model=APIResponse[None])
async def delete_student(
    student_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    await InstitutionService.delete_student(db, manager.tenant_id, student_id)
    return APIResponse(success=True, data=None, message="Student deleted")


@router.post("/students/bulk", response_model=APIResponseBulk)
async def bulk_create_students(
    file: Annotated[UploadFile, File(description="CSV with headers: name, roll_no, email, gender, date_of_birth, class_code")],
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_tenant_user_admin)],
):
    content = await file.read(BULK_MAX_FILE_BYTES + 1)
    if len(content) > BULK_MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large — max 2 MB")
    tenant = await _tenant(db, admin)
    result = await InstitutionService.bulk_create_students(db, tenant, content)
    return APIResponse(
        success=True,
        data=result,
        message=f"Bulk import finished: {result.created} created, {len(result.errors)} failed",
    )


# ── Enrollments ──────────────────────────────────────────────────────────────

@router.get("/enrollments", response_model=APIResponseEnrollments)
async def list_enrollments(
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    return APIResponse(success=True, data=await InstitutionService.list_enrollments(db, manager.tenant_id), message="Enrollments loaded")


@router.post("/enrollments", response_model=APIResponseEnrollment, status_code=201)
async def create_enrollment(
    payload: EnrollmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    manager: Annotated[User, Depends(get_current_tenant_user_student_records_manager)],
):
    data = await InstitutionService.create_enrollment(db, manager.tenant_id, payload)
    return APIResponse(success=True, data=data, message="Student enrolled")
