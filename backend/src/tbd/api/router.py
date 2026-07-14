"""Top-level API router composition."""

from fastapi import APIRouter

from tbd.api.routers.answers import router as answers_router
from tbd.api.routers.auth import router as auth_router
from tbd.api.routers.courses import router as courses_router
from tbd.api.routers.health import router as health_router
from tbd.api.routers.jobs import router as jobs_router
from tbd.api.routers.jobs import session_jobs_router
from tbd.api.routers.materials import router as materials_router
from tbd.api.routers.personal_ai import router as personal_ai_router
from tbd.api.routers.questions import router as questions_router
from tbd.api.routers.realtime import router as realtime_router
from tbd.api.routers.recordings import router as recordings_router
from tbd.api.routers.records import router as records_router
from tbd.api.routers.sessions import router as sessions_router
from tbd.api.routers.transcripts import router as transcripts_router
from tbd.api.routers.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)

# Feature PRs add business routers to this versioned boundary.
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(answers_router)
v1_router.include_router(courses_router)
v1_router.include_router(jobs_router)
v1_router.include_router(session_jobs_router)
v1_router.include_router(materials_router)
v1_router.include_router(personal_ai_router)
v1_router.include_router(questions_router)
v1_router.include_router(recordings_router)
v1_router.include_router(records_router)
v1_router.include_router(realtime_router)
v1_router.include_router(sessions_router)
v1_router.include_router(transcripts_router)
v1_router.include_router(users_router)
api_router.include_router(v1_router)
