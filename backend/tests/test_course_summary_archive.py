"""Integration coverage for the Course-wide public FINAL Summary archive."""

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


async def _seed_users(database_url: str, count: int) -> list[UUID]:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            user_ids: list[UUID] = []
            for index in range(count):
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (display_name, primary_email) "
                        "VALUES (:name, :email) RETURNING id"
                    ),
                    {
                        "name": f"summary-archive-user-{index}",
                        "email": f"summary-archive-{index}-{uuid4().hex[:10]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                user_ids.append(user_id)
            return user_ids
    finally:
        await database.dispose()


async def _seed_completed_states(
    database_url: str,
    *,
    course_id: UUID,
    owner_id: UUID,
) -> tuple[dict[str, UUID], UUID]:
    """Create every public state plus a private LIVE result beside AVAILABLE."""

    database = create_database(_settings(database_url))
    now = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
    session_ids = {state: uuid4() for state in ("available", "empty", "failed", "integrity")}
    recording_ids = {state: uuid4() for state in ("available", "empty", "integrity")}
    recording_job_ids = {state: uuid4() for state in recording_ids}
    version_ids = {state: uuid4() for state in recording_ids}
    segment_ids = {state: uuid4() for state in ("available", "integrity")}
    final_job_id = uuid4()
    failed_coordinator_id = uuid4()
    summary_id = uuid4()
    private_job_id = uuid4()
    private_summary_id = uuid4()
    try:
        async with database.engine.begin() as connection:
            await connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            await connection.execute(
                text(
                    """
                    INSERT INTO lecture_sessions (
                        id, course_id, created_by_user_id, title, lecture_date, status,
                        version, started_at, ended_at, completed_at, created_at, updated_at
                    ) VALUES (
                        :id, :course_id, :owner_id, :title, :lecture_date, 'COMPLETED',
                        1, :started_at, :ended_at, :completed_at, :created_at, :updated_at
                    )
                    """
                ),
                [
                    {
                        "id": session_ids[state],
                        "course_id": course_id,
                        "owner_id": owner_id,
                        "title": f"{state} summary class",
                        "lecture_date": (now - timedelta(days=index)).date(),
                        "started_at": now - timedelta(days=index),
                        "ended_at": now - timedelta(days=index) + timedelta(hours=1),
                        "completed_at": now - timedelta(days=index) + timedelta(hours=2),
                        "created_at": now - timedelta(days=index, hours=1),
                        "updated_at": now - timedelta(days=index) + timedelta(hours=2),
                    }
                    for index, state in enumerate(session_ids, start=1)
                ],
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_jobs (
                        id, session_id, job_type, visibility, status, attempt, version,
                        blocks_session_completion, retryable, error_code, error_message,
                        started_at, finished_at, created_at, updated_at
                    ) VALUES (
                        :id, :session_id, 'SESSION_POSTPROCESSING', 'SHARED', 'FAILED',
                        1, 1, true, true, 'SUMMARY_SOURCE_UNAVAILABLE',
                        'safe terminal source failure', :started_at, :finished_at,
                        :started_at, :finished_at
                    )
                    """
                ),
                {
                    "id": failed_coordinator_id,
                    "session_id": session_ids["failed"],
                    "started_at": now - timedelta(days=3) + timedelta(hours=1),
                    "finished_at": now - timedelta(days=3) + timedelta(hours=1, minutes=1),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO session_recordings (
                        id, session_id, publisher_user_id, publisher_client_stream_id_hash,
                        last_received_sequence, last_processed_sequence,
                        last_captured_offset_ms,
                        status, content_type, byte_size, duration_ms, storage_key,
                        capture_started_at, capture_ended_at, uploaded_at, version,
                        created_at, updated_at
                    ) VALUES (
                        :id, :session_id, :owner_id, :stream_hash, -1, -1, 1000,
                        'UPLOADED',
                        'audio/webm', 128, 1000, :storage_key, :captured_at,
                        :uploaded_at, :uploaded_at, 1, :captured_at, :uploaded_at
                    )
                    """
                ),
                [
                    {
                        "id": recording_ids[state],
                        "session_id": session_ids[state],
                        "owner_id": owner_id,
                        "stream_hash": bytes([index]) * 32,
                        "storage_key": f"final/summary-archive-{recording_ids[state]}",
                        "captured_at": now - timedelta(days=index),
                        "uploaded_at": now - timedelta(days=index) + timedelta(hours=1),
                    }
                    for index, state in enumerate(recording_ids, start=1)
                ],
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_jobs (
                        id, session_id, job_type, visibility, status, attempt, version,
                        target_recording_id, blocks_session_completion, retryable,
                        started_at, finished_at, created_at, updated_at
                    ) VALUES (
                        :id, :session_id, 'RECORDING_TRANSCRIPTION', 'SHARED',
                        'SUCCEEDED', 1, 1, :recording_id, true, true,
                        :started_at, :finished_at, :started_at, :finished_at
                    )
                    """
                ),
                [
                    {
                        "id": recording_job_ids[state],
                        "session_id": session_ids[state],
                        "recording_id": recording_ids[state],
                        "started_at": now - timedelta(days=index) + timedelta(hours=1),
                        "finished_at": now - timedelta(days=index) + timedelta(hours=1, minutes=1),
                    }
                    for index, state in enumerate(recording_job_ids, start=1)
                ],
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO transcript_versions (
                        id, session_id, version, source, status, recording_id,
                        created_by_job_id, created_by_job_attempt, last_sequence,
                        finalized_at, created_at, updated_at
                    ) VALUES (
                        :id, :session_id, 1, 'RECORDING', :status, :recording_id,
                        :job_id, 1, :last_sequence, :finalized_at, :created_at, :finalized_at
                    )
                    """
                ),
                [
                    {
                        "id": version_ids[state],
                        "session_id": session_ids[state],
                        "status": "EMPTY" if state == "empty" else "FINALIZED",
                        "recording_id": recording_ids[state],
                        "job_id": recording_job_ids[state],
                        "last_sequence": 0 if state == "empty" else 1,
                        "created_at": now - timedelta(days=index) + timedelta(hours=1),
                        "finalized_at": now - timedelta(days=index) + timedelta(hours=1, minutes=1),
                    }
                    for index, state in enumerate(version_ids, start=1)
                ],
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO transcript_segments (
                        id, session_id, transcript_version_id, sequence, start_ms,
                        end_ms, text, created_by_job_id, created_by_job_attempt, created_at
                    ) VALUES (
                        :id, :session_id, :version_id, 1, 0, 1000, :content,
                        :job_id, 1, :created_at
                    )
                    """
                ),
                [
                    {
                        "id": segment_ids[state],
                        "session_id": session_ids[state],
                        "version_id": version_ids[state],
                        "content": f"{state} final transcript",
                        "job_id": recording_job_ids[state],
                        "created_at": now,
                    }
                    for state in segment_ids
                ],
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_jobs (
                        id, session_id, job_type, visibility, status, attempt, version,
                        blocks_session_completion, retryable, started_at, finished_at,
                        created_at, updated_at
                    ) VALUES (
                        :id, :session_id, 'FINAL_SUMMARY', 'SHARED', 'SUCCEEDED',
                        1, 1, true, true, :started_at, :finished_at, :started_at, :finished_at
                    )
                    """
                ),
                {
                    "id": final_job_id,
                    "session_id": session_ids["available"],
                    "started_at": now,
                    "finished_at": now + timedelta(seconds=1),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO lecture_summaries (
                        id, session_id, requester_user_id, created_by_job_id,
                        created_by_job_attempt, summary_type, visibility, content,
                        source_transcript_version_id, source_start_segment_id,
                        source_end_segment_id, model_name, prompt_version, created_at
                    ) VALUES (
                        :id, :session_id, NULL, :job_id, 1, 'FINAL', 'COURSE_MEMBERS',
                        :content, :version_id, :segment_id, :segment_id,
                        'summary-fake', 'final-summary-v1', :created_at
                    )
                    """
                ),
                {
                    "id": summary_id,
                    "session_id": session_ids["available"],
                    "job_id": final_job_id,
                    "content": "공용 FINAL 요약",
                    "version_id": version_ids["available"],
                    "segment_id": segment_ids["available"],
                    "created_at": now,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_jobs (
                        id, session_id, requester_user_id, job_type, visibility, status,
                        attempt, version, input_transcript_version_id,
                        input_start_segment_id, input_end_segment_id,
                        blocks_session_completion, retryable, started_at, finished_at,
                        created_at, updated_at
                    ) VALUES (
                        :id, :session_id, :owner_id, 'LIVE_SUMMARY', 'REQUESTER_ONLY',
                        'SUCCEEDED', 1, 1, :version_id, :segment_id, :segment_id,
                        false, false, :started_at, :finished_at, :started_at, :finished_at
                    )
                    """
                ),
                {
                    "id": private_job_id,
                    "session_id": session_ids["available"],
                    "owner_id": owner_id,
                    "version_id": version_ids["available"],
                    "segment_id": segment_ids["available"],
                    "started_at": now,
                    "finished_at": now + timedelta(seconds=1),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO lecture_summaries (
                        id, session_id, requester_user_id, created_by_job_id,
                        created_by_job_attempt, summary_type, visibility, content,
                        source_transcript_version_id, source_start_segment_id,
                        source_end_segment_id, model_name, prompt_version, created_at
                    ) VALUES (
                        :id, :session_id, :owner_id, :job_id, 1, 'LIVE',
                        'REQUESTER_ONLY', :content, :version_id, :segment_id, :segment_id,
                        'private-fake', 'live-summary-v1', :created_at
                    )
                    """
                ),
                {
                    "id": private_summary_id,
                    "session_id": session_ids["available"],
                    "owner_id": owner_id,
                    "job_id": private_job_id,
                    "content": "절대 공개하면 안 되는 LIVE 요약",
                    "version_id": version_ids["available"],
                    "segment_id": segment_ids["available"],
                    "created_at": now + timedelta(seconds=2),
                },
            )
        return session_ids, summary_id
    finally:
        await database.dispose()


async def _complete_session(database_url: str, session_id: UUID) -> None:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE lecture_sessions
                    SET status = 'COMPLETED', completed_at = ended_at,
                        version = version + 1, updated_at = ended_at
                    WHERE id = :session_id
                    """
                ),
                {"session_id": session_id},
            )
    finally:
        await database.dispose()


async def _delete_course(database_url: str, course_id: UUID) -> None:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("UPDATE courses SET deleted_at = now() WHERE id = :course_id"),
                {"course_id": course_id},
            )
    finally:
        await database.dispose()


def test_course_summary_archive_is_stable_private_and_state_complete(
    migrated_database_url: str,
) -> None:
    owner_id, outsider_id = asyncio.run(_seed_users(migrated_database_url, 2))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": owner_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "summary-archive-course"},
                json={"title": "Course AI 요약", "semester": "2026 여름학기"},
            )
            assert course.status_code == 201, course.text
            course_id = UUID(course.json()["id"])
            processing = client.post(
                f"/api/v1/courses/{course_id}/sessions",
                headers=TRUSTED_ORIGIN,
                json={"title": "현재 정리 class", "lecture_date": "2026-07-15"},
            )
            assert processing.status_code == 201, processing.text
            processing_id = UUID(processing.json()["id"])
            assert (
                client.post(
                    f"/api/v1/sessions/{processing_id}/start", headers=TRUSTED_ORIGIN
                ).status_code
                == 200
            )
            ended = client.post(
                f"/api/v1/sessions/{processing_id}/end",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "summary-archive-end"},
            )
            assert ended.status_code == 202, ended.text

            state_sessions, public_summary_id = asyncio.run(
                _seed_completed_states(
                    migrated_database_url,
                    course_id=course_id,
                    owner_id=owner_id,
                )
            )

            first = client.get(
                f"/api/v1/courses/{course_id}/summaries",
                params={"limit": 1},
            )
            assert first.status_code == 200, first.text
            assert len(first.json()["items"]) == 1
            assert first.json()["items"][0]["session"]["id"] == str(processing_id)
            assert first.json()["items"][0]["state"] == {"status": "PENDING", "reason": None}
            assert first.json()["items"][0]["summary"] is None
            assert first.json()["items"][0]["summary_url"] is None
            cursor = first.json()["next_cursor"]
            assert isinstance(cursor, str)

            # The first active class must not repeat after it becomes completed.
            asyncio.run(_complete_session(migrated_database_url, processing_id))
            rest = client.get(
                f"/api/v1/courses/{course_id}/summaries",
                params={"cursor": cursor, "limit": 100},
            )
            assert rest.status_code == 200, rest.text
            assert rest.json()["next_cursor"] is None
            assert str(processing_id) not in {
                item["session"]["id"] for item in rest.json()["items"]
            }
            by_session = {item["session"]["id"]: item for item in rest.json()["items"]}
            available = by_session[str(state_sessions["available"])]
            assert available["state"] == {"status": "AVAILABLE", "reason": None}
            assert available["summary"]["id"] == str(public_summary_id)
            assert available["summary"]["summary_type"] == "FINAL"
            assert available["summary"]["visibility"] == "COURSE_MEMBERS"
            assert available["summary_url"] == f"/api/v1/summaries/{public_summary_id}"
            assert "절대 공개하면 안 되는 LIVE 요약" not in rest.text
            assert "requester_user_id" not in rest.text

            empty = by_session[str(state_sessions["empty"])]
            assert empty["state"]["status"] == "NOT_APPLICABLE"
            assert empty["state"]["reason"]["code"] == "NO_FINAL_TRANSCRIPT"
            assert empty["summary"] is None and empty["summary_url"] is None

            failed = by_session[str(state_sessions["failed"])]
            assert failed["state"]["status"] == "FAILED"
            assert failed["state"]["reason"]["code"] == "SUMMARY_SOURCE_UNAVAILABLE"
            assert failed["summary"] is None and failed["summary_url"] is None

            integrity = by_session[str(state_sessions["integrity"])]
            assert integrity["state"] == {"status": "DATA_INTEGRITY_ERROR", "reason": None}
            assert integrity["summary"] is None and integrity["summary_url"] is None

            replacement = "A" if cursor[-1] != "A" else "B"
            tampered = client.get(
                f"/api/v1/courses/{course_id}/summaries",
                params={"cursor": f"{cursor[:-1]}{replacement}"},
            )
            assert tampered.status_code == 400
            assert tampered.json()["error"]["code"] == "INVALID_CURSOR"

            wrong_archive = client.get(
                f"/api/v1/courses/{course_id}/materials",
                params={"cursor": cursor},
            )
            assert wrong_archive.status_code == 400
            assert wrong_archive.json()["error"]["code"] == "INVALID_CURSOR"

            other_course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "summary-other-course"},
                json={"title": "다른 Course", "semester": "2026 여름학기"},
            )
            assert other_course.status_code == 201
            cross_course = client.get(
                f"/api/v1/courses/{other_course.json()['id']}/summaries",
                params={"cursor": cursor},
            )
            assert cross_course.status_code == 400
            assert cross_course.json()["error"]["code"] == "INVALID_CURSOR"

            current_user["id"] = outsider_id
            forbidden = client.get(f"/api/v1/courses/{course_id}/summaries")
            assert forbidden.status_code == 403
            assert forbidden.json()["error"]["code"] == "COURSE_ACCESS_DENIED"

            current_user["id"] = owner_id
            asyncio.run(_delete_course(migrated_database_url, course_id))
            deleted = client.get(f"/api/v1/courses/{course_id}/summaries")
            missing = client.get(f"/api/v1/courses/{uuid4()}/summaries")
            assert deleted.status_code == 404
            assert missing.status_code == 404
    finally:
        asyncio.run(database.dispose())
