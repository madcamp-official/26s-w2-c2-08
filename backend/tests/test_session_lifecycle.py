"""Integration coverage for Course-scoped class lifecycle transitions."""

import asyncio
import base64
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database, transaction
from tbd.models.sessions import LectureSession
from tbd.providers.ai import FakeLLMProvider
from tbd.services.courses import CourseService
from tbd.services.postprocessing import SessionPostprocessingWorker
from tbd.services.sessions import ActiveSessionExistsError, SessionService

pytestmark = pytest.mark.integration
TRUSTED_ORIGIN = {"Origin": "http://localhost:5173"}


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
        auth_allowed_origins="http://localhost:5173",
        idempotency_response_encryption_key=base64.b64encode(b"i" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"e" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"h" * 32).decode(),
    )


async def _seed_user(database_url: str) -> UUID:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (display_name, primary_email) "
                    "VALUES (:name, :email) RETURNING id"
                ),
                {
                    "name": f"session-user-{uuid4().hex[:8]}",
                    "email": f"session-{uuid4().hex[:8]}@example.test",
                },
            )
            assert isinstance(user_id, UUID)
            return user_id
    finally:
        await database.dispose()


def test_session_api_persists_lifecycle_and_never_uses_job_count_as_completion(
    migrated_database_url: str,
) -> None:
    """Only the explicit stored lifecycle state controls class visibility and completion."""

    owner_id = asyncio.run(_seed_user(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    app.dependency_overrides[get_current_user_id] = lambda: owner_id

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "course-for-session-flow"},
            json={"title": "알고리즘", "semester": "2026 여름학기"},
        )
        assert course.status_code == 201
        course_id = course.json()["id"]

        created = client.post(
            f"/api/v1/courses/{course_id}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"title": "   ", "lecture_date": "2026-07-14"},
        )
        assert created.status_code == 201
        session_data = created.json()
        session_id = session_data["id"]
        assert session_data["status"] == "READY"
        assert session_data["title"].startswith("알고리즘 · 2026.07.14 ")
        assert session_data["started_at"] is None

        duplicate = client.post(
            f"/api/v1/courses/{course_id}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"lecture_date": "2026-07-21"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "ACTIVE_SESSION_EXISTS"

        started = client.post(f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN)
        assert started.status_code == 200
        assert started.json()["status"] == "LIVE"
        assert started.json()["canonical_transcript_version_id"] is not None

        ended = client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "end-session-flow-001"},
        )
        replay = client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "end-session-flow-001"},
        )
        assert ended.status_code == 202
        assert replay.json() == ended.json()
        assert ended.json()["session"]["status"] == "PROCESSING"
        assert ended.json()["jobs"][0]["job_type"] == "SESSION_POSTPROCESSING"
        assert ended.json()["jobs"][0]["blocks_session_completion"] is True

        current = client.get(f"/api/v1/courses/{course_id}")
        assert current.json()["current_session"]["status"] == "PROCESSING"
        assert (
            client.delete(
                f"/api/v1/sessions/{session_id}",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "delete-processing-session"},
            ).status_code
            == 409
        )

    worker = SessionPostprocessingWorker(database.session_factory, FakeLLMProvider())
    assert asyncio.run(worker.run_once()) is True
    with TestClient(app) as client:
        detail = client.get(f"/api/v1/sessions/{session_id}")
        assert detail.json()["status"] == "COMPLETED"
        assert detail.json()["completed_at"] is not None
        assert (
            client.delete(
                f"/api/v1/sessions/{session_id}",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "delete-completed-session"},
            ).status_code
            == 204
        )


async def _exercise_concurrent_session_creation(database_url: str) -> None:
    """Course row locking and partial UNIQUE must leave exactly one active class."""

    owner_id = await _seed_user(database_url)
    settings = _settings(database_url)
    codec = settings.course_join_code_codec
    assert codec is not None
    database = create_database(settings)
    try:
        async with database.session_factory() as session:
            async with transaction(session):
                course, _ = await CourseService(codec).create(
                    session,
                    user_id=owner_id,
                    title="동시성 수업",
                    semester="2026 여름학기",
                )
                course_id = course.course.id

        async def create_once() -> str:
            async with database.session_factory() as session:
                try:
                    async with transaction(session):
                        created = await SessionService().create(
                            session,
                            course_id=course_id,
                            user_id=owner_id,
                            title=None,
                            lecture_date=date(2026, 7, 14),
                        )
                        return str(created.id)
                except ActiveSessionExistsError:
                    return "conflict"

        results = await asyncio.gather(create_once(), create_once())
        assert results.count("conflict") == 1
        async with database.session_factory() as session:
            active_count = await session.scalar(
                select(func.count())
                .select_from(LectureSession)
                .where(
                    LectureSession.course_id == course_id,
                    LectureSession.status.in_(("READY", "LIVE", "PROCESSING")),
                )
            )
            assert active_count == 1
    finally:
        await database.dispose()


def test_concurrent_session_creation_keeps_one_active_class(
    migrated_database_url: str,
) -> None:
    asyncio.run(_exercise_concurrent_session_creation(migrated_database_url))
