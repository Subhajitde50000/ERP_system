"""Platform owner (customer account) routers — the shikshasync.me account-holder API.

Aggregates the five owner-facing concerns into one mounted router under
/api/v1/owner: auth, the dashboard (My Institutions + billing summary), billing
records (subscriptions / invoices / payments), support tickets and profile.
"""

from fastapi import APIRouter

from app.routers.owner.auth import router as auth_router
from app.routers.owner.dashboard import router as dashboard_router
from app.routers.owner.billing import router as billing_router
from app.routers.owner.tickets import router as tickets_router
from app.routers.owner.profile import router as profile_router

router = APIRouter(prefix="/owner", tags=["Platform Owner"])
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(billing_router)
router.include_router(tickets_router)
router.include_router(profile_router)

__all__ = ["router"]
