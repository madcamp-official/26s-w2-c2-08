"""Integration coverage for resumable Recording upload and protected playback."""

import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.models.consistency import OutboxEvent
from tbd.models.knowledge import LectureSummary
from tbd.models.materials import RecordingUpload, SessionRecording, TranscriptVersion
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession
from tbd.providers.ai import FakeLLMProvider
from tbd.providers.stt import BatchSTTSegment, DeterministicBatchSTTProvider
from tbd.services.postprocessing import SessionPostprocessingWorker
from tbd.services.recording_transcription import RecordingTranscriptionWorker
from tbd.services.recordings import RecordingService
from tbd.storage import InMemoryStorage, Storage, StorageKey, StorageNamespace

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
            ids: list[UUID] = []
            for index in range(count):
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (display_name, primary_email) "
                        "VALUES (:name, :email) RETURNING id"
                    ),
                    {
                        "name": f"recording-user-{index}-{uuid4().hex[:8]}",
                        "email": f"recording-{index}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                ids.append(user_id)
            return ids
    finally:
        await database.dispose()


def _audio_ticket(client: TestClient, session_id: str) -> str:
    response = client.post(
        "/api/v1/realtime-tickets",
        headers=TRUSTED_ORIGIN,
        json={"session_id": session_id, "scope": "SESSION_AUDIO_WRITE"},
    )
    assert response.status_code == 201
    return response.json()["ticket"]


def _audio_start(stream_id: str) -> dict[str, object]:
    return {
        "type": "audio.start",
        "request_id": "recording-audio-start",
        "data": {
            "client_stream_id": stream_id,
            "format": {"encoding": "PCM_S16LE", "sample_rate_hz": 16000, "channels": 1},
            "chunk_duration_ms": 500,
            "resume_from_sequence": None,
        },
    }


async def _recording_rows(
    database_url: str, tmp_path: Path, session_id: UUID
) -> tuple[SessionRecording, RecordingUpload, TranscriptVersion, AIJob, list[str]]:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.session_factory() as session:
            recording = await session.scalar(
                select(SessionRecording).where(SessionRecording.session_id == session_id)
            )
            upload = await session.scalar(
                select(RecordingUpload).where(RecordingUpload.recording_id == recording.id)
            )
            version = await session.scalar(
                select(TranscriptVersion)
                .where(TranscriptVersion.session_id == session_id)
                .where(TranscriptVersion.source == "RECORDING")
            )
            job = await session.scalar(
                select(AIJob)
                .where(AIJob.session_id == session_id)
                .where(AIJob.job_type == "RECORDING_TRANSCRIPTION")
            )
            event_types = list(
                await session.scalars(
                    select(OutboxEvent.event_type).where(OutboxEvent.session_id == session_id)
                )
            )
            assert recording is not None
            assert upload is not None
            assert version is not None
            assert job is not None
            return recording, upload, version, job, event_types
    finally:
        await database.dispose()


async def _expire_upload(database_url: str, tmp_path: Path, upload_id: UUID) -> None:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.session_factory() as session:
            async with session.begin():
                upload = await session.scalar(
                    select(RecordingUpload).where(RecordingUpload.id == upload_id).with_for_update()
                )
                assert upload is not None
                upload.created_at = datetime.now(UTC) - timedelta(days=2)
                upload.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    finally:
        await database.dispose()


async def _recording_orphans(
    database_url: str, tmp_path: Path, storage: Storage
) -> tuple[StorageKey, ...]:
    settings = _settings(database_url, tmp_path)
    database = create_database(settings)
    try:
        async with database.session_factory() as session:
            return await RecordingService(settings).find_storage_orphans(
                session, storage=storage, now=datetime.now(UTC)
            )
    finally:
        await database.dispose()


async def _recording_event_payload(
    database_url: str, tmp_path: Path, session_id: UUID
) -> dict[str, object]:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.session_factory() as session:
            payload = await session.scalar(
                select(OutboxEvent.payload)
                .where(
                    OutboxEvent.session_id == session_id,
                    OutboxEvent.event_type == "recording.updated",
                )
                .order_by(OutboxEvent.created_at.desc())
            )
            assert isinstance(payload, dict)
            return payload
    finally:
        await database.dispose()


def test_recording_upload_replays_completion_and_proxies_member_playback(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    professor_id, student_id, outsider_id = asyncio.run(
        _seed_users(migrated_database_url, tmp_path, 3)
    )
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    storage = InMemoryStorage()
    app = create_app(settings=settings, database=database, storage=storage)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    recording_bytes = b"recording-contents-for-range-test"
    digest = hashlib.sha256(recording_bytes).hexdigest()

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "recording-course-create"},
            json={"title": "녹음 수업", "semester": "2026 여름학기"},
        )
        assert course.status_code == 201
        lecture_session = client.post(
            f"/api/v1/courses/{course.json()['id']}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"title": "녹음 class", "lecture_date": "2026-07-14"},
        )
        assert lecture_session.status_code == 201
        session_id = lecture_session.json()["id"]
        assert (
            client.post(f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN).status_code
            == 200
        )

        ticket = _audio_ticket(client, session_id)
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}/audio?ticket={ticket}"
        ) as socket:
            socket.send_json(_audio_start("recording-publisher-tab"))
            assert socket.receive_json()["type"] == "audio.ready"

        assert (
            client.post(
                f"/api/v1/sessions/{session_id}/end",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "recording-session-end"},
            ).status_code
            == 202
        )
        metadata = client.get(f"/api/v1/sessions/{session_id}/recording")
        assert metadata.status_code == 200
        assert metadata.json()["status"] == "UPLOAD_PENDING"
        assert "storage_key" not in metadata.json()

        create_payload = {
            "client_stream_id": "recording-publisher-tab",
            "content_type": "audio/webm;codecs=opus",
            "total_bytes": len(recording_bytes),
            "duration_ms": 500,
        }
        created = client.post(
            f"/api/v1/sessions/{session_id}/recording/uploads",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "recording-upload-create"},
            json=create_payload,
        )
        replay_created = client.post(
            f"/api/v1/sessions/{session_id}/recording/uploads",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "recording-upload-create"},
            json=create_payload,
        )
        assert created.status_code == 201
        assert replay_created.status_code == 201
        assert replay_created.json() == created.json()
        upload_id = created.json()["id"]
        assert created.json()["offset_bytes"] == 0

        wrong_offset = client.patch(
            f"/api/v1/recording-uploads/{upload_id}",
            headers={
                **TRUSTED_ORIGIN,
                "Content-Type": "application/octet-stream",
                "Upload-Offset": "1",
                "X-Chunk-SHA256": digest,
            },
            content=recording_bytes,
        )
        assert wrong_offset.status_code == 409
        assert wrong_offset.json()["error"]["details"]["offset_bytes"] == 0

        uploaded = client.patch(
            f"/api/v1/recording-uploads/{upload_id}",
            headers={
                **TRUSTED_ORIGIN,
                "Content-Type": "application/octet-stream",
                "Upload-Offset": "0",
                "X-Chunk-SHA256": digest,
            },
            content=recording_bytes,
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["offset_bytes"] == len(recording_bytes)

        complete = client.post(
            f"/api/v1/recording-uploads/{upload_id}/complete",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "recording-complete"},
            json={"sha256": digest},
        )
        replay_complete = client.post(
            f"/api/v1/recording-uploads/{upload_id}/complete",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "recording-complete"},
            json={"sha256": digest},
        )
        assert complete.status_code == 202
        assert replay_complete.status_code == 202
        assert replay_complete.json() == complete.json()
        assert complete.json()["recording"]["status"] == "UPLOADED"
        assert complete.json()["transcript_version"]["source"] == "RECORDING"
        assert complete.json()["job"]["job_type"] == "RECORDING_TRANSCRIPTION"
        assert complete.json()["job"]["blocks_session_completion"] is True

        orphan = StorageKey.new(StorageNamespace.TEMPORARY)
        asyncio.run(storage.create_temporary(orphan))
        assert orphan in asyncio.run(_recording_orphans(migrated_database_url, tmp_path, storage))

        current_user["id"] = student_id
        joined = client.post(
            "/api/v1/courses/join",
            headers=TRUSTED_ORIGIN,
            json={"join_code": course.json()["join_code"]},
        )
        assert joined.status_code == 201
        partial = client.get(
            complete.json()["recording"]["playback_url"], headers={"Range": "bytes=2-7"}
        )
        assert partial.status_code == 206
        assert partial.content == recording_bytes[2:8]
        assert partial.headers["content-range"] == f"bytes 2-7/{len(recording_bytes)}"
        assert partial.headers["content-type"].startswith("audio/webm")

        current_user["id"] = outsider_id
        assert client.get(complete.json()["recording"]["playback_url"]).status_code == 404

    recording, upload, version, job, event_types = asyncio.run(
        _recording_rows(migrated_database_url, tmp_path, UUID(session_id))
    )
    assert recording.status == "UPLOADED"
    assert upload.status == "COMPLETED"
    assert version.status == "FINALIZING"
    assert version.created_by_job_id == job.id
    assert "recording.updated" in event_types
    assert "job.updated" in event_types
    event_payload = asyncio.run(
        _recording_event_payload(migrated_database_url, tmp_path, UUID(session_id))
    )
    assert "storage_key" not in event_payload
    assert "publisher_client_stream_id_hash" not in event_payload

    hq_database = create_database(_settings(migrated_database_url, tmp_path))
    try:
        worker = RecordingTranscriptionWorker(
            hq_database.session_factory,
            storage,
            DeterministicBatchSTTProvider(
                (
                    BatchSTTSegment(
                        start_ms=0,
                        end_ms=500,
                        recording_start_ms=0,
                        recording_end_ms=500,
                        text="녹음 기반 final 문장",
                    ),
                )
            ),
        )
        assert asyncio.run(worker.run_once()) is True
    finally:
        asyncio.run(hq_database.dispose())

    _, _, processed_version, processed_job, processed_event_types = asyncio.run(
        _recording_rows(migrated_database_url, tmp_path, UUID(session_id))
    )
    assert processed_version.status == "FINALIZED"
    assert processed_version.last_sequence == 1
    assert processed_job.status == "SUCCEEDED"
    assert "transcript.version.updated" in processed_event_types

    postprocessing_worker = SessionPostprocessingWorker(database.session_factory, FakeLLMProvider())
    assert asyncio.run(postprocessing_worker.run_once()) is True
    assert asyncio.run(postprocessing_worker.run_once()) is True

    async def final_rows() -> tuple[LectureSession, AIJob, LectureSummary]:
        async with database.session_factory() as session:
            lecture_session = await session.get(LectureSession, UUID(session_id))
            summary_job = await session.scalar(
                select(AIJob).where(
                    AIJob.session_id == UUID(session_id),
                    AIJob.job_type == "FINAL_SUMMARY",
                )
            )
            summary = await session.scalar(
                select(LectureSummary).where(LectureSummary.session_id == UUID(session_id))
            )
            assert lecture_session is not None
            assert summary_job is not None
            assert summary is not None
            return lecture_session, summary_job, summary

    completed_session, summary_job, summary = asyncio.run(final_rows())
    assert completed_session.status == "COMPLETED"
    assert summary_job.status == "SUCCEEDED"
    assert summary.summary_type == "FINAL"
    assert summary.source_transcript_version_id == processed_version.id
    asyncio.run(database.dispose())


def test_recording_upload_rejects_wrong_publisher_and_checksum(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    professor_id, other_professor_id = asyncio.run(_seed_users(migrated_database_url, tmp_path, 2))
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    app = create_app(settings=settings, database=database, storage=InMemoryStorage())
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "recording-security-course"},
            json={"title": "보안 녹음", "semester": "2026 여름학기"},
        )
        lecture_session = client.post(
            f"/api/v1/courses/{course.json()['id']}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"lecture_date": "2026-07-14"},
        )
        session_id = lecture_session.json()["id"]
        assert (
            client.post(f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN).status_code
            == 200
        )
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}/audio?ticket={_audio_ticket(client, session_id)}"
        ) as socket:
            socket.send_json(_audio_start("original-publisher"))
            assert socket.receive_json()["type"] == "audio.ready"
        assert (
            client.post(
                f"/api/v1/sessions/{session_id}/end",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "recording-security-end"},
            ).status_code
            == 202
        )

        current_user["id"] = other_professor_id
        assert (
            client.post(
                "/api/v1/courses/join",
                headers=TRUSTED_ORIGIN,
                json={"join_code": course.json()["join_code"]},
            ).status_code
            == 201
        )
        forbidden = client.post(
            f"/api/v1/sessions/{session_id}/recording/uploads",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "wrong-publisher"},
            json={
                "client_stream_id": "different-publisher",
                "content_type": "audio/mp4",
                "total_bytes": 3,
                "duration_ms": 1,
            },
        )
        assert forbidden.status_code == 403

        current_user["id"] = professor_id
        created = client.post(
            f"/api/v1/sessions/{session_id}/recording/uploads",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "checksum-create"},
            json={
                "client_stream_id": "original-publisher",
                "content_type": "audio/mp4",
                "total_bytes": 3,
                "duration_ms": 1,
            },
        )
        assert created.status_code == 201
        upload_id = created.json()["id"]
        too_large = client.patch(
            f"/api/v1/recording-uploads/{upload_id}",
            headers={
                **TRUSTED_ORIGIN,
                "Content-Type": "application/octet-stream",
                "Upload-Offset": "0",
                "X-Chunk-SHA256": "0" * 64,
            },
            content=b"x" * (8 * 1024 * 1024 + 1),
        )
        assert too_large.status_code == 413
        assert too_large.json()["error"]["details"]["max_chunk_bytes"] == 8_388_608
        invalid_chunk = client.patch(
            f"/api/v1/recording-uploads/{upload_id}",
            headers={
                **TRUSTED_ORIGIN,
                "Content-Type": "application/octet-stream",
                "Upload-Offset": "0",
                "X-Chunk-SHA256": hashlib.sha256(b"other").hexdigest(),
            },
            content=b"abc",
        )
        assert invalid_chunk.status_code == 422
        assert invalid_chunk.json()["error"]["code"] == "RECORDING_CHECKSUM_MISMATCH"

        asyncio.run(_expire_upload(migrated_database_url, tmp_path, UUID(upload_id)))
        expired = client.get(f"/api/v1/recording-uploads/{upload_id}")
        assert expired.status_code == 410
        recreated = client.post(
            f"/api/v1/sessions/{session_id}/recording/uploads",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "after-expiry-create"},
            json={
                "client_stream_id": "original-publisher",
                "content_type": "audio/mp4",
                "total_bytes": 3,
                "duration_ms": 1,
            },
        )
        assert recreated.status_code == 201

    asyncio.run(database.dispose())
