"""Institution admin API — mounted under /api/v1/institution.

Aggregates the three admin-facing concerns: academic structure, people, and
configuration (modules, settings, profile). Every route is tenant-scoped and
requires the INSTITUTION_ADMIN role.
"""

from fastapi import APIRouter

from app.routers.institution.structure import router as structure_router
from app.routers.institution.people import router as people_router
from app.routers.institution.config import router as config_router
from app.routers.institution.links import router as links_router
from app.routers.institution.mentors import router as mentors_router

router = APIRouter(prefix="/institution", tags=["Institution Admin"])
router.include_router(structure_router)
router.include_router(people_router)
router.include_router(config_router)
router.include_router(links_router)
router.include_router(mentors_router)

__all__ = ["router"]
