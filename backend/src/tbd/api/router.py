"""Top-level API router composition."""

from fastapi import APIRouter

from tbd.api.routers.health import router as health_router
from tbd.api.routers.jobs import router as jobs_router

api_router = APIRouter()
api_router.include_router(health_router)

# Feature PRs add business routers to this versioned boundary.
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(jobs_router)
api_router.include_router(v1_router)
