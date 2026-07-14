"""Integration coverage for ticketed Course event WebSockets and replay recovery."""

import asyncio
import base64
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database, transaction
from tbd.models.consistency import OutboxEvent

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


async def _seed_session(database_url: str) -> tuple[UUID, UUID, UUID]:
    """Insert one durable aggregate without emitting an initial realtime event."""

    suffix = uuid4().hex
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (display_name, primary_email) "
                    "VALUES (:name, :email) RETURNING id"
                ),
                {"name": f"realtime-{suffix}", "email": f"realtime-{suffix}@example.test"},
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
                    "title": f"Realtime {suffix}",
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
                {"course_id": course_id, "user_id": user_id, "title": f"Class {suffix}"},
            )
        assert isinstance(user_id, UUID)
        assert isinstance(course_id, UUID)
        assert isinstance(session_id, UUID)
        return user_id, course_id, session_id
    finally:
        await database.dispose()


async def _enqueue_session_update(
    database_url: str,
    *,
    session_id: UUID,
    version: int,
) -> None:
    database = create_database(_settings(database_url))
    try:
        async with database.session_factory() as session:
            async with transaction(session):
                session.add(
                    OutboxEvent(
                        session_id=session_id,
                        partition_key=f"session:{session_id}",
                        event_type="session.updated",
                        resource_version=version,
                        payload={"id": str(session_id), "version": version},
                        available_at=datetime.now(UTC),
                    )
                )
    finally:
        await database.dispose()


def _ticket(client: TestClient, session_id: UUID, resume_cursor: str | None = None) -> str:
    response = client.post(
        "/api/v1/realtime-tickets",
        headers=TRUSTED_ORIGIN,
        json={
            "session_id": str(session_id),
            "scope": "SESSION_EVENTS_READ",
            "resume_cursor": resume_cursor,
        },
    )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    return response.json()["ticket"]


def test_event_ticket_is_single_use_and_replays_from_a_signed_cursor(
    migrated_database_url: str,
) -> None:
    """An event socket consumes its ticket and recovers missed public invalidations."""

    owner_id, _, session_id = asyncio.run(_seed_session(migrated_database_url))
    settings = _settings(migrated_database_url)
    app = create_app(settings=settings, database=create_database(settings))
    app.dependency_overrides[get_current_user_id] = lambda: owner_id

    with TestClient(app) as client:
        first_ticket = _ticket(client, session_id)
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}?ticket={first_ticket}"
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["type"] == "connection.ready"
            assert ready["data"]["resume_status"] == "FRESH"

            asyncio.run(
                _enqueue_session_update(migrated_database_url, session_id=session_id, version=2)
            )
            event = websocket.receive_json()
            assert event["type"] == "session.updated"
            assert event["data"] == {"id": str(session_id), "version": 2}
            cursor = event["cursor"]
            assert isinstance(cursor, str)

        asyncio.run(
            _enqueue_session_update(migrated_database_url, session_id=session_id, version=3)
        )
        replay_ticket = _ticket(client, session_id, cursor)
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}?ticket={replay_ticket}"
        ) as websocket:
            ready = websocket.receive_json()
            replayed = websocket.receive_json()
            assert ready["data"]["resume_status"] == "REPLAYED"
            assert replayed["type"] == "session.updated"
            assert replayed["data"]["version"] == 3

        with pytest.raises(WebSocketDisconnect) as reused:
            with client.websocket_connect(
                f"/api/v1/ws/sessions/{session_id}?ticket={replay_ticket}"
            ) as websocket:
                websocket.receive_json()
        assert reused.value.code == 4401


def test_unknown_resume_cursor_requires_rest_resync(migrated_database_url: str) -> None:
    """A cursor from a deleted/other server window never fabricates missing events."""

    owner_id, _, session_id = asyncio.run(_seed_session(migrated_database_url))
    settings = _settings(migrated_database_url)
    app = create_app(settings=settings, database=create_database(settings))
    app.dependency_overrides[get_current_user_id] = lambda: owner_id

    with TestClient(app) as client:
        ticket = _ticket(client, session_id, "not-a-valid-signed-cursor")
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}?ticket={ticket}"
        ) as websocket:
            ready = websocket.receive_json()
            resync = websocket.receive_json()
            assert ready["data"]["resume_status"] == "RESYNC_REQUIRED"
            assert resync["type"] == "resync.required"
            assert "SESSION" in resync["data"]["resources"]


def test_ticket_requires_course_membership(migrated_database_url: str) -> None:
    """A session UUID alone never authorizes a non-member to mint a socket ticket."""

    _, _, session_id = asyncio.run(_seed_session(migrated_database_url))
    outsider_id = asyncio.run(_seed_session(migrated_database_url))[0]
    settings = _settings(migrated_database_url)
    app = create_app(settings=settings, database=create_database(settings))
    app.dependency_overrides[get_current_user_id] = lambda: outsider_id

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/realtime-tickets",
            headers=TRUSTED_ORIGIN,
            json={"session_id": str(session_id), "scope": "SESSION_EVENTS_READ"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "COURSE_ACCESS_DENIED"
