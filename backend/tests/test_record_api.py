"""Integration coverage for the compact completed-class record manifest."""

import asyncio
import base64
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database

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
                    "name": "record-manifest-owner",
                    "email": f"record-manifest-{uuid4().hex[:12]}@example.test",
                },
            )
            assert isinstance(user_id, UUID)
            return user_id
    finally:
        await database.dispose()


def test_record_manifest_is_bounded_and_available_while_processing(
    migrated_database_url: str,
) -> None:
    owner_id = asyncio.run(_seed_user(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    app.dependency_overrides[get_current_user_id] = lambda: owner_id
    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "record-manifest-course"},
                json={"title": "기록 API", "semester": "2026 여름학기"},
            )
            assert course.status_code == 201, course.text
            created = client.post(
                f"/api/v1/courses/{course.json()['id']}/sessions",
                headers=TRUSTED_ORIGIN,
                json={"lecture_date": "2026-07-14"},
            )
            assert created.status_code == 201, created.text
            session_id = created.json()["id"]

            not_ready = client.get(f"/api/v1/sessions/{session_id}/record")
            assert not_ready.status_code == 409
            assert not_ready.json()["error"]["code"] == "SESSION_STATE_CONFLICT"

            assert (
                client.post(f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN).status_code
                == 200
            )
            ended = client.post(
                f"/api/v1/sessions/{session_id}/end",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "record-manifest-end"},
            )
            assert ended.status_code == 202, ended.text

            response = client.get(f"/api/v1/sessions/{session_id}/record")
            assert response.status_code == 200, response.text
            record = response.json()
            assert record["session"]["status"] == "PROCESSING"
            assert record["recording"] is None
            assert record["recording_url"] == f"/api/v1/sessions/{session_id}/recording"
            assert record["materials"] == {
                "total_count": 0,
                "list_url": f"/api/v1/sessions/{session_id}/materials",
            }
            assert record["questions"] == {
                "total_count": 0,
                "list_url": f"/api/v1/sessions/{session_id}/questions?sort=RECENT",
            }
            assert record["answers"] == {
                "total_count": 0,
                "list_url": f"/api/v1/sessions/{session_id}/answers",
            }
            assert record["jobs"]["total_count"] >= 1
            assert record["jobs"]["list_url"] == f"/api/v1/sessions/{session_id}/jobs"
            assert record["transcript"]["state"] is not None
            assert record["transcript"]["selected_version_id"] is not None
            assert record["transcript"]["timeline_url"] == (
                f"/api/v1/sessions/{session_id}/transcript?transcript_version_id="
                f"{record['transcript']['selected_version_id']}"
            )
            assert record["summary"]["state"]["status"] == "PENDING"

            # The manifest intentionally never embeds pageable record arrays.
            for key in ("materials", "transcript", "questions", "answers", "jobs"):
                assert "items" not in record[key]
                assert "storage_key" not in str(record[key])
    finally:
        asyncio.run(database.dispose())
