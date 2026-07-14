"""Top-level API router composition."""

from fastapi import APIRouter

from tbd.api.routers.auth import router as auth_router
from tbd.api.routers.courses import router as courses_router
from tbd.api.routers.health import router as health_router
from tbd.api.routers.jobs import router as jobs_router
from tbd.api.routers.realtime import router as realtime_router
from tbd.api.routers.sessions import router as sessions_router
from tbd.api.routers.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)

# Feature PRs add business routers to this versioned boundary.
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(courses_router)
v1_router.include_router(jobs_router)
v1_router.include_router(realtime_router)
v1_router.include_router(sessions_router)
v1_router.include_router(users_router)
api_router.include_router(v1_router)
