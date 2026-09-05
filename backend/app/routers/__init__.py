"""
Routers Package Init
"""

from app.routers.platform import (
    platform_admin_router,
    platform_auth_router,
    platform_support_router,
)
from app.routers.tenant import tenant_auth_router
from app.routers.service_requests import router as service_requests_router
from app.routers.public.signup import router as public_signup_router
from app.routers.owner import router as owner_router
from app.routers.institution import router as institution_router
from app.routers.setup import router as setup_router
from app.routers.email import router as email_router
from app.routers.principal import router as principal_router
from app.routers.vice_principal import router as vice_principal_router
from app.routers.hod import router as hod_router
from app.routers.coordinator import router as coordinator_router
from app.routers.exam_controller import router as exam_controller_router
from app.routers.teacher import router as teacher_router
from app.routers.student import router as student_router
from app.routers.parent import router as parent_router
from app.routers.library import router as library_router
from app.routers.hostel import router as hostel_router
from app.routers.online_class import router as online_class_router
from app.routers.notifications import router as notifications_router, push_token_router as push_tokens_router
from app.routers.files import router as files_router

__all__ = [
    "platform_auth_router",
    "platform_admin_router",
    "platform_support_router",
    "tenant_auth_router",
    "service_requests_router",
    "public_signup_router",
    "owner_router",
    "institution_router",
    "setup_router",
    "email_router",
    "principal_router",
    "vice_principal_router",
    "hod_router",
    "coordinator_router",
    "exam_controller_router",
    "teacher_router",
    "student_router",
    "parent_router",
    "library_router",
    "hostel_router",
    "online_class_router",
    "notifications_router",
    "push_tokens_router",
]
