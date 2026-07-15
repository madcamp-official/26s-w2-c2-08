"""Integration coverage for the Course-wide compact Transcript archive."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.models.materials import (
    SessionRecording,
    TranscriptGap,
    TranscriptSegment,
    TranscriptVersion,
)
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession

pytestmark = pytest.mark.integration
TRUSTED_ORIGIN = {"Origin": "http://localhost:5173"}


def _settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
        storage_root=tmp_path / "uploads",
        auth_allowed_origins="http://localhost:5173",
        idempotency_response_encryption_key=base64.b64encode(b"i" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"e" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"h" * 32).decode(),
    )


async def _seed_users(database_url: str, tmp_path: Path, count: int) -> list[UUID]:
    database = create_database(_settings(database_url, tmp_path))
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
                        "name": f"transcript-archive-user-{index}",
                        "email": f"transcript-archive-{index}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                user_ids.append(user_id)
            return user_ids
    finally:
        await database.dispose()


@dataclass(frozen=True, slots=True)
class _ArchiveSeed:
    failed_session_id: UUID
    failed_live_version_id: UUID
    failed_hq_version_id: UUID
    staging_session_id: UUID
    staging_live_version_id: UUID
    staging_hq_version_id: UUID
    staging_private_segment_id: UUID
    empty_session_id: UUID
    empty_version_id: UUID
    no_transcript_session_id: UUID


def _completed_session(
    *,
    course_id: UUID,
    owner_id: UUID,
    title: str,
    started_at: datetime,
) -> LectureSession:
    return LectureSession(
        course_id=course_id,
        created_by_user_id=owner_id,
        title=title,
        lecture_date=started_at.date(),
        status="COMPLETED",
        started_at=started_at,
        ended_at=started_at + timedelta(hours=1),
        completed_at=started_at + timedelta(hours=2),
        version=1,
    )


async def _recording_job(
    session: AsyncSession,
    *,
    lecture_session: LectureSession,
    owner_id: UUID,
    now: datetime,
    status: str,
) -> tuple[SessionRecording, AIJob]:
    recording = SessionRecording(
        session_id=lecture_session.id,
        publisher_user_id=owner_id,
        publisher_client_stream_id_hash=b"r" * 32,
        last_received_sequence=-1,
        last_processed_sequence=-1,
        last_captured_offset_ms=0,
        status="CAPTURING",
        capture_started_at=now - timedelta(hours=1),
        version=1,
    )
    session.add(recording)
    await session.flush()
    job = AIJob(
        session_id=lecture_session.id,
        job_type="RECORDING_TRANSCRIPTION",
        visibility="SHARED",
        status=status,
        attempt=1,
        target_recording_id=recording.id,
        blocks_session_completion=True,
        retryable=status == "FAILED",
        error_code="HQ_STT_FAILED" if status == "FAILED" else None,
        error_message="HQ Transcript를 만들지 못했습니다." if status == "FAILED" else None,
        started_at=now - timedelta(minutes=1) if status == "FAILED" else None,
        finished_at=now if status == "FAILED" else None,
        version=1,
    )
    session.add(job)
    await session.flush()
    return recording, job


async def _seed_archive(
    database_url: str,
    tmp_path: Path,
    *,
    course_id: UUID,
    owner_id: UUID,
) -> _ArchiveSeed:
    database = create_database(_settings(database_url, tmp_path))
    now = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                failed_session = _completed_session(
                    course_id=course_id,
                    owner_id=owner_id,
                    title="HQ 실패 class",
                    started_at=now - timedelta(days=1),
                )
                staging_session = _completed_session(
                    course_id=course_id,
                    owner_id=owner_id,
                    title="HQ 처리 중 class",
                    started_at=now - timedelta(days=2),
                )
                empty_session = _completed_session(
                    course_id=course_id,
                    owner_id=owner_id,
                    title="빈 Transcript class",
                    started_at=now - timedelta(days=3),
                )
                no_transcript_session = _completed_session(
                    course_id=course_id,
                    owner_id=owner_id,
                    title="Transcript 없는 class",
                    started_at=now - timedelta(days=4),
                )
                session.add_all(
                    [failed_session, staging_session, empty_session, no_transcript_session]
                )
                await session.flush()

                failed_live = TranscriptVersion(
                    session_id=failed_session.id,
                    version=1,
                    source="LIVE",
                    status="FINALIZED",
                    last_sequence=1,
                    finalized_at=now - timedelta(days=1, hours=-1),
                )
                staging_live = TranscriptVersion(
                    session_id=staging_session.id,
                    version=1,
                    source="LIVE",
                    status="FINALIZED",
                    last_sequence=1,
                    finalized_at=now - timedelta(days=2, hours=-1),
                )
                empty_version = TranscriptVersion(
                    session_id=empty_session.id,
                    version=1,
                    source="LIVE",
                    status="EMPTY",
                    last_sequence=0,
                    finalized_at=now - timedelta(days=3, hours=-1),
                )
                session.add_all([failed_live, staging_live, empty_version])
                await session.flush()
                failed_session.canonical_transcript_version_id = failed_live.id
                staging_session.canonical_transcript_version_id = staging_live.id
                empty_session.canonical_transcript_version_id = empty_version.id

                session.add_all(
                    [
                        TranscriptSegment(
                            session_id=failed_session.id,
                            transcript_version_id=failed_live.id,
                            sequence=1,
                            start_ms=0,
                            end_ms=800,
                            text="실패 뒤에도 유지되는 LIVE canonical",
                        ),
                        TranscriptGap(
                            session_id=failed_session.id,
                            transcript_version_id=failed_live.id,
                            start_ms=0,
                            end_ms=1200,
                            is_final=True,
                            reason="CLIENT_DISCONNECTED",
                            details={},
                        ),
                        TranscriptSegment(
                            session_id=staging_session.id,
                            transcript_version_id=staging_live.id,
                            sequence=1,
                            start_ms=0,
                            end_ms=500,
                            text="공개 LIVE canonical",
                        ),
                        TranscriptGap(
                            session_id=empty_session.id,
                            transcript_version_id=empty_version.id,
                            start_ms=0,
                            end_ms=500,
                            is_final=True,
                            reason="SERVER_STATE_LOST",
                            details={},
                        ),
                    ]
                )

                failed_recording, failed_job = await _recording_job(
                    session,
                    lecture_session=failed_session,
                    owner_id=owner_id,
                    now=now,
                    status="FAILED",
                )
                failed_hq = TranscriptVersion(
                    session_id=failed_session.id,
                    version=2,
                    source="RECORDING",
                    status="FAILED",
                    recording_id=failed_recording.id,
                    created_by_job_id=failed_job.id,
                    created_by_job_attempt=1,
                    last_sequence=0,
                    failed_at=now,
                )
                session.add(failed_hq)

                staging_recording, staging_job = await _recording_job(
                    session,
                    lecture_session=staging_session,
                    owner_id=owner_id,
                    now=now,
                    status="PENDING",
                )
                staging_hq = TranscriptVersion(
                    session_id=staging_session.id,
                    version=2,
                    source="RECORDING",
                    status="FINALIZING",
                    recording_id=staging_recording.id,
                    created_by_job_id=staging_job.id,
                    created_by_job_attempt=1,
                    last_sequence=2,
                )
                session.add(staging_hq)
                await session.flush()
                staging_private_segment = TranscriptSegment(
                    session_id=staging_session.id,
                    transcript_version_id=staging_hq.id,
                    sequence=1,
                    start_ms=0,
                    end_ms=400,
                    recording_start_ms=0,
                    recording_end_ms=400,
                    text="STAGING_PRIVATE_SENTENCE_ONE",
                    created_by_job_id=staging_job.id,
                    created_by_job_attempt=1,
                )
                session.add_all(
                    [
                        staging_private_segment,
                        TranscriptSegment(
                            session_id=staging_session.id,
                            transcript_version_id=staging_hq.id,
                            sequence=2,
                            start_ms=500,
                            end_ms=900,
                            recording_start_ms=500,
                            recording_end_ms=900,
                            text="STAGING_PRIVATE_SENTENCE_TWO",
                            created_by_job_id=staging_job.id,
                            created_by_job_attempt=1,
                        ),
                    ]
                )
                await session.flush()

            return _ArchiveSeed(
                failed_session_id=failed_session.id,
                failed_live_version_id=failed_live.id,
                failed_hq_version_id=failed_hq.id,
                staging_session_id=staging_session.id,
                staging_live_version_id=staging_live.id,
                staging_hq_version_id=staging_hq.id,
                staging_private_segment_id=staging_private_segment.id,
                empty_session_id=empty_session.id,
                empty_version_id=empty_version.id,
                no_transcript_session_id=no_transcript_session.id,
            )
    finally:
        await database.dispose()


async def _complete_session(database_url: str, tmp_path: Path, session_id: UUID) -> None:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE lecture_sessions
                    SET status = 'COMPLETED', ended_at = started_at + interval '1 second',
                        completed_at = started_at + interval '1 second', version = version + 1,
                        updated_at = started_at + interval '1 second'
                    WHERE id = :session_id
                    """
                ),
                {"session_id": session_id},
            )
    finally:
        await database.dispose()


async def _delete_course(database_url: str, tmp_path: Path, course_id: UUID) -> None:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("UPDATE courses SET deleted_at = now() WHERE id = :course_id"),
                {"course_id": course_id},
            )
    finally:
        await database.dispose()


async def _clear_canonical_version(
    database_url: str,
    tmp_path: Path,
    session_id: UUID,
) -> None:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE lecture_sessions "
                    "SET canonical_transcript_version_id = NULL WHERE id = :session_id"
                ),
                {"session_id": session_id},
            )
    finally:
        await database.dispose()


def test_course_transcript_archive_is_scoped_stable_and_canonical_safe(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    owner_id, outsider_id = asyncio.run(_seed_users(migrated_database_url, tmp_path, 2))
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": owner_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "transcript-archive-course"},
            json={"title": "Course Transcript 모음", "semester": "2026 여름학기"},
        )
        assert course.status_code == 201, course.text
        course_id = UUID(course.json()["id"])
        seed = asyncio.run(
            _seed_archive(
                migrated_database_url,
                tmp_path,
                course_id=course_id,
                owner_id=owner_id,
            )
        )

        ready = client.post(
            f"/api/v1/courses/{course_id}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"title": "현재 class", "lecture_date": "2026-07-15"},
        )
        assert ready.status_code == 201, ready.text
        active_session_id = UUID(ready.json()["id"])
        before_start = client.get(f"/api/v1/courses/{course_id}/transcripts")
        assert before_start.status_code == 200
        assert str(active_session_id) not in {
            item["session"]["id"] for item in before_start.json()["items"]
        }

        started = client.post(
            f"/api/v1/sessions/{active_session_id}/start",
            headers=TRUSTED_ORIGIN,
        )
        assert started.status_code == 200, started.text
        first = client.get(
            f"/api/v1/courses/{course_id}/transcripts",
            params={"limit": 1},
        )
        assert first.status_code == 200, first.text
        first_item = first.json()["items"][0]
        assert first_item["session"]["id"] == str(active_session_id)
        assert first_item["session"]["status"] == "LIVE"
        assert set(first_item["transcript"]) == {
            "state",
            "selected_version_id",
            "segment_count",
            "gap_count",
            "timeline_url",
            "versions_url",
        }
        first_cursor = first.json()["next_cursor"]
        assert isinstance(first_cursor, str)

        # A cursor issued after the active class must not repeat that class if
        # it transitions to COMPLETED before the next page is read.
        asyncio.run(
            _complete_session(
                migrated_database_url,
                tmp_path,
                active_session_id,
            )
        )
        second = client.get(
            f"/api/v1/courses/{course_id}/transcripts",
            params={"limit": 1, "cursor": first_cursor},
        )
        assert second.status_code == 200, second.text
        failed = second.json()["items"][0]
        assert failed["session"]["id"] == str(seed.failed_session_id)
        failed_index = failed["transcript"]
        assert failed_index["state"]["status"] == "FAILED"
        assert failed_index["state"]["current_version"]["id"] == str(seed.failed_hq_version_id)
        assert failed_index["state"]["canonical_version_id"] == str(seed.failed_live_version_id)
        assert failed_index["selected_version_id"] == str(seed.failed_live_version_id)
        assert failed_index["segment_count"] == 1
        assert failed_index["gap_count"] == 1
        assert failed_index["timeline_url"] == (
            f"/api/v1/sessions/{seed.failed_session_id}/transcript"
            f"?transcript_version_id={seed.failed_live_version_id}"
        )
        timeline_first = client.get(f"{failed_index['timeline_url']}&limit=1")
        assert timeline_first.status_code == 200, timeline_first.text
        assert len(timeline_first.json()["segments"]) == 1
        public_segment_id = timeline_first.json()["segments"][0]["id"]
        assert timeline_first.json()["gaps"] == []
        assert isinstance(timeline_first.json()["next_cursor"], str)
        timeline_second = client.get(
            f"{failed_index['timeline_url']}&limit=1&cursor={timeline_first.json()['next_cursor']}"
        )
        assert timeline_second.status_code == 200, timeline_second.text
        assert timeline_second.json()["segments"] == []
        assert len(timeline_second.json()["gaps"]) == 1
        assert timeline_second.json()["next_cursor"] is None

        third = client.get(
            f"/api/v1/courses/{course_id}/transcripts",
            params={"limit": 1, "cursor": second.json()["next_cursor"]},
        )
        assert third.status_code == 200, third.text
        staging = third.json()["items"][0]
        assert staging["session"]["id"] == str(seed.staging_session_id)
        assert staging["transcript"]["state"]["status"] == "FINALIZING"
        assert staging["transcript"]["selected_version_id"] == str(seed.staging_live_version_id)
        assert staging["transcript"]["segment_count"] == 1
        assert "STAGING_PRIVATE_SENTENCE" not in third.text
        versions = client.get(f"/api/v1/sessions/{seed.staging_session_id}/transcript/versions")
        assert versions.status_code == 200, versions.text
        assert str(seed.staging_hq_version_id) not in {
            item["id"] for item in versions.json()["items"]
        }
        staging_segment = client.get(
            f"/api/v1/transcript-segments/{seed.staging_private_segment_id}"
        )
        assert staging_segment.status_code == 404

        fourth = client.get(
            f"/api/v1/courses/{course_id}/transcripts",
            params={"limit": 1, "cursor": third.json()["next_cursor"]},
        )
        assert fourth.status_code == 200, fourth.text
        empty = fourth.json()["items"][0]
        assert empty["session"]["id"] == str(seed.empty_session_id)
        assert empty["transcript"]["state"]["status"] == "EMPTY"
        assert empty["transcript"]["selected_version_id"] == str(seed.empty_version_id)
        assert empty["transcript"]["segment_count"] == 0
        assert empty["transcript"]["gap_count"] == 1

        fifth = client.get(
            f"/api/v1/courses/{course_id}/transcripts",
            params={"limit": 1, "cursor": fourth.json()["next_cursor"]},
        )
        assert fifth.status_code == 200, fifth.text
        missing_transcript = fifth.json()["items"][0]
        assert missing_transcript["session"]["id"] == str(seed.no_transcript_session_id)
        assert missing_transcript["transcript"] == {
            "state": None,
            "selected_version_id": None,
            "segment_count": 0,
            "gap_count": 0,
            "timeline_url": f"/api/v1/sessions/{seed.no_transcript_session_id}/transcript",
            "versions_url": (
                f"/api/v1/sessions/{seed.no_transcript_session_id}/transcript/versions"
            ),
        }
        assert fifth.json()["next_cursor"] is None

        # A RECORDING/FINALIZING version without any canonical fallback is
        # internal staging, not a readable transcript or stable timeline.
        asyncio.run(
            _clear_canonical_version(
                migrated_database_url,
                tmp_path,
                seed.staging_session_id,
            )
        )
        canonical_missing = client.get(
            f"/api/v1/courses/{course_id}/transcripts",
            params={"limit": 100},
        )
        assert canonical_missing.status_code == 200
        canonical_missing_item = next(
            item
            for item in canonical_missing.json()["items"]
            if item["session"]["id"] == str(seed.staging_session_id)
        )
        assert canonical_missing_item["transcript"] == {
            "state": None,
            "selected_version_id": None,
            "segment_count": 0,
            "gap_count": 0,
            "timeline_url": f"/api/v1/sessions/{seed.staging_session_id}/transcript",
            "versions_url": (f"/api/v1/sessions/{seed.staging_session_id}/transcript/versions"),
        }

        replacement = "A" if first_cursor[-1] != "A" else "B"
        tampered = client.get(
            f"/api/v1/courses/{course_id}/transcripts",
            params={"cursor": f"{first_cursor[:-1]}{replacement}"},
        )
        assert tampered.status_code == 400
        assert tampered.json()["error"]["code"] == "INVALID_CURSOR"

        other_course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "other-transcript-archive-course"},
            json={"title": "다른 Course", "semester": "2026 여름학기"},
        )
        assert other_course.status_code == 201
        wrong_course = client.get(
            f"/api/v1/courses/{other_course.json()['id']}/transcripts",
            params={"cursor": first_cursor},
        )
        assert wrong_course.status_code == 400
        assert wrong_course.json()["error"]["code"] == "INVALID_CURSOR"

        current_user["id"] = outsider_id
        forbidden = client.get(f"/api/v1/courses/{course_id}/transcripts")
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "COURSE_ACCESS_DENIED"

        current_user["id"] = owner_id
        asyncio.run(_delete_course(migrated_database_url, tmp_path, course_id))
        deleted = client.get(f"/api/v1/courses/{course_id}/transcripts")
        deleted_timeline = client.get(failed_index["timeline_url"])
        deleted_versions = client.get(
            f"/api/v1/sessions/{seed.failed_session_id}/transcript/versions"
        )
        deleted_segment = client.get(f"/api/v1/transcript-segments/{public_segment_id}")
        missing = client.get(f"/api/v1/courses/{uuid4()}/transcripts")
        assert deleted.status_code == 404
        assert deleted.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert deleted_timeline.status_code == 404
        assert deleted_versions.status_code == 404
        assert deleted_segment.status_code == 404
        assert missing.status_code == 404

    asyncio.run(database.dispose())
