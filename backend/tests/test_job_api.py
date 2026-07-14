"""Integration coverage for the common AIJob polling and retry API."""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.jobs.kernel import JobKernel
from tbd.models.enums import AIJobVisibility
from tbd.models.questions import AIJob

pytestmark = pytest.mark.integration


def _database(database_url: str):
    return create_database(
        Settings(
            _env_file=None,
            app_env=AppEnvironment.TEST,
            database_url=database_url,
        )
    )


async def _create_failed_shared_job(database_url: str) -> tuple[UUID, UUID]:
    """Create a professor-owned FINAL_SUMMARY Job that a user may retry."""

    suffix = uuid4().hex
    database = _database(database_url)
    try:
        async with database.engine.begin() as connection:
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (display_name, primary_email) "
                    "VALUES (:name, :email) RETURNING id"
                ),
                {"name": f"job-api-{suffix}", "email": f"job-api-{suffix}@example.test"},
            )
            course_id = await connection.scalar(
                text(
                    "INSERT INTO courses (title, semester, created_by_user_id, "
                    "join_code_lookup_hash, join_code_lookup_key_version, "
                    "join_code_ciphertext, join_code_nonce, join_code_key_version) "
                    "VALUES (:title, '2026-2', :user_id, digest(:lookup, 'sha256'), 1, "
                    "decode('01', 'hex'), substring(digest(:nonce, 'sha256') FROM 1 FOR 12), 1) "
                    "RETURNING id"
                ),
                {
                    "title": f"Job API {suffix}",
                    "user_id": user_id,
                    "lookup": suffix,
                    "nonce": suffix,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO course_members (course_id, user_id, role) "
                    "VALUES (:course_id, :user_id, 'PROFESSOR')"
                ),
                {"course_id": course_id, "user_id": user_id},
            )
            session_id = await connection.scalar(
                text(
                    "INSERT INTO lecture_sessions (course_id, created_by_user_id, title, lecture_date) "
                    "VALUES (:course_id, :user_id, :title, CURRENT_DATE) RETURNING id"
                ),
                {"course_id": course_id, "user_id": user_id, "title": f"Session {suffix}"},
            )
        assert isinstance(user_id, UUID)
        assert isinstance(session_id, UUID)

        kernel = JobKernel()
        async with database.session_factory() as session:
            async with session.begin():
                job = AIJob(
                    session_id=session_id,
                    job_type="FINAL_SUMMARY",
                    visibility=AIJobVisibility.SHARED,
                    blocks_session_completion=True,
                )
                await kernel.enqueue(session, job)
                now = datetime.now(UTC) + timedelta(seconds=1)
                run = await kernel.claim_next_shared(
                    session,
                    now=now,
                    lease_duration=timedelta(seconds=60),
                )
                assert run is not None
                assert await kernel.fail(
                    session,
                    run,
                    error_code="MODEL_UNAVAILABLE",
                    error_message="모델을 사용할 수 없습니다.",
                    retryable=True,
                    now=now + timedelta(seconds=1),
                )
                assert job.id is not None
                return user_id, job.id
    finally:
        await database.dispose()


def test_job_retry_is_authorized_atomic_and_replayable(migrated_database_url: str) -> None:
    """A professor gets the same encrypted 202 response on a duplicate retry request."""

    user_id, job_id = asyncio.run(_create_failed_shared_job(migrated_database_url))
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=migrated_database_url,
        idempotency_response_encryption_key=base64.b64encode(b"r" * 32).decode(),
    )
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        with TestClient(app) as client:
            before = client.get(f"/api/v1/jobs/{job_id}")
            assert before.status_code == 200
            assert before.json()["status"] == "FAILED"
            assert before.json()["target"] == {
                "resource_type": "SESSION",
                "resource_id": before.json()["session_id"],
                "resource_url": f"/api/v1/sessions/{before.json()['session_id']}",
            }

            forbidden = client.post(
                f"/api/v1/jobs/{job_id}/retry",
                headers={"Idempotency-Key": "retry-final-summary-001"},
            )
            headers = {
                "Idempotency-Key": "retry-final-summary-001",
                "Origin": "http://localhost:5173",
            }
            first = client.post(f"/api/v1/jobs/{job_id}/retry", headers=headers)
            replay = client.post(f"/api/v1/jobs/{job_id}/retry", headers=headers)

        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
        assert first.status_code == 202
        assert replay.status_code == 202
        assert replay.json() == first.json()
        assert first.json()["job"]["id"] == str(job_id)
        assert first.json()["job"]["attempt"] == 2
        assert first.json()["job"]["status"] == "PENDING"
        assert first.json()["job"]["retryable"] is False
        assert first.headers["X-Request-ID"]
    finally:
        asyncio.run(database.dispose())


def test_job_polling_hides_a_job_from_nonmembers(
    migrated_database_url: str,
) -> None:
    """A non-member cannot distinguish any Job from a missing resource."""

    owner_id, job_id = asyncio.run(_create_failed_shared_job(migrated_database_url))
    outsider_id = uuid4()
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=migrated_database_url,
        idempotency_response_encryption_key=base64.b64encode(b"s" * 32).decode(),
    )
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    app.dependency_overrides[get_current_user_id] = lambda: outsider_id

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/jobs/{job_id}")

        assert owner_id != outsider_id
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    finally:
        asyncio.run(database.dispose())
