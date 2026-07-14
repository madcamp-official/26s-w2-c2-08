"""Integration coverage for ticketed publisher claim, PCM ACK, and final storage."""

import asyncio
import base64
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from tbd.api.dependencies import get_current_user_id
from tbd.api.routers import realtime as realtime_router
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.models.consistency import OutboxEvent
from tbd.models.materials import (
    SessionRecording,
    TranscriptGap,
    TranscriptSegment,
    TranscriptVersion,
)
from tbd.providers.stt import (
    DeterministicStreamingSTTProvider,
    STTFinal,
    STTPartial,
    UnavailableStreamingSTTProvider,
)
from tbd.realtime.audio import FRAME_HEADER, PCM_CHUNK_BYTES
from tbd.services.courses import CourseService
from tbd.services.sessions import SessionService

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


async def _seed_live_session(database_url: str) -> tuple[UUID, UUID]:
    settings = _settings(database_url)
    codec = settings.course_join_code_codec
    assert codec is not None
    database = create_database(settings)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                user_id = uuid4()
                from tbd.models.users import User

                session.add(
                    User(
                        id=user_id,
                        display_name="audio professor",
                        primary_email=f"audio-{uuid4().hex[:12]}@example.test",
                    )
                )
                await session.flush()
                course, _ = await CourseService(codec).create(
                    session,
                    user_id=user_id,
                    title="음성 수업",
                    semester="2026 여름학기",
                )
                lecture_session = await SessionService().create(
                    session,
                    course_id=course.course.id,
                    user_id=user_id,
                    title="실시간 음성",
                    lecture_date=date(2026, 7, 14),
                )
                await SessionService().start(
                    session,
                    session_id=lecture_session.id,
                    user_id=user_id,
                )
                return user_id, lecture_session.id
    finally:
        await database.dispose()


def _audio_ticket(client: TestClient, session_id: UUID) -> str:
    response = client.post(
        "/api/v1/realtime-tickets",
        headers=TRUSTED_ORIGIN,
        json={"session_id": str(session_id), "scope": "SESSION_AUDIO_WRITE"},
    )
    assert response.status_code == 201
    return response.json()["ticket"]


def _start(stream_id: str, resume_from_sequence: int | None = None) -> dict[str, object]:
    return {
        "type": "audio.start",
        "request_id": "audio-start-test",
        "data": {
            "client_stream_id": stream_id,
            "format": {"encoding": "PCM_S16LE", "sample_rate_hz": 16000, "channels": 1},
            "chunk_duration_ms": 500,
            "resume_from_sequence": resume_from_sequence,
        },
    }


def _frame(sequence: int, offset_ms: int) -> bytes:
    return FRAME_HEADER.pack(1, 0, sequence, offset_ms) + (b"\x00" * PCM_CHUNK_BYTES)


async def _add_live_versions(database_url: str, session_id: UUID) -> None:
    database = create_database(_settings(database_url))
    try:
        async with database.session_factory() as session:
            async with session.begin():
                first = await session.scalar(
                    select(TranscriptVersion).where(
                        TranscriptVersion.session_id == session_id,
                        TranscriptVersion.source == "LIVE",
                    )
                )
                assert first is not None
                first.status = "FINALIZED"
                first.finalized_at = datetime.now(UTC)
                session.add_all(
                    [
                        TranscriptVersion(
                            id=uuid4(),
                            session_id=session_id,
                            version=2,
                            source="LIVE",
                            status="FINALIZED",
                            last_sequence=0,
                            finalized_at=datetime.now(UTC),
                        ),
                        TranscriptVersion(
                            id=uuid4(),
                            session_id=session_id,
                            version=3,
                            source="LIVE",
                            status="FINALIZING",
                            last_sequence=0,
                        ),
                    ]
                )
    finally:
        await database.dispose()


async def _audio_rows(
    database_url: str, session_id: UUID
) -> tuple[SessionRecording, list[TranscriptSegment], list[TranscriptGap]]:
    database = create_database(_settings(database_url))
    try:
        async with database.session_factory() as session:
            recording = await session.scalar(
                select(SessionRecording).where(SessionRecording.session_id == session_id)
            )
            segments = list(
                await session.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.session_id == session_id)
                    .order_by(TranscriptSegment.sequence)
                )
            )
            gaps = list(
                await session.scalars(
                    select(TranscriptGap)
                    .where(TranscriptGap.session_id == session_id)
                    .order_by(TranscriptGap.start_ms)
                )
            )
            assert recording is not None
            return recording, segments, gaps
    finally:
        await database.dispose()


async def _event_types(database_url: str, session_id: UUID) -> list[str]:
    database = create_database(_settings(database_url))
    try:
        async with database.session_factory() as session:
            return list(
                await session.scalars(
                    select(OutboxEvent.event_type).where(OutboxEvent.session_id == session_id)
                )
            )
    finally:
        await database.dispose()


def test_audio_socket_claims_one_publisher_and_persists_only_final_results(
    migrated_database_url: str,
) -> None:
    user_id, session_id = asyncio.run(_seed_live_session(migrated_database_url))
    final = STTFinal(
        utterance_id="utt-live-0",
        audio_sequence_start=0,
        audio_sequence_end=0,
        start_ms=0,
        end_ms=500,
        text="저장되는 최종 문장",
    )
    settings = _settings(migrated_database_url)
    app = create_app(
        settings=settings,
        database=create_database(settings),
        streaming_stt_provider=DeterministicStreamingSTTProvider({0: [final]}),
    )
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    with TestClient(app) as client:
        ticket = _audio_ticket(client, session_id)
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}/audio?ticket={ticket}"
        ) as websocket:
            websocket.send_json(_start("publisher-tab"))
            ready = websocket.receive_json()
            assert ready["type"] == "audio.ready"
            assert ready["publisher_status"] == "CLAIMED"
            assert ready["last_received_sequence"] is None

            websocket.send_bytes(_frame(0, 0))
            ack = websocket.receive_json()
            assert ack == {
                "type": "audio.ack",
                "received_through": 0,
                "processed_through": 0,
                "queue_depth_ms": 0,
            }

            websocket.send_bytes(_frame(0, 0))
            duplicate_ack = websocket.receive_json()
            assert duplicate_ack["received_through"] == 0
            assert duplicate_ack["processed_through"] == 0

            conflict_ticket = _audio_ticket(client, session_id)
            with pytest.raises(WebSocketDisconnect) as conflict:
                with client.websocket_connect(
                    f"/api/v1/ws/sessions/{session_id}/audio?ticket={conflict_ticket}"
                ) as other_socket:
                    other_socket.send_json(_start("another-tab"))
                    error = other_socket.receive_json()
                    assert error["code"] == "AUDIO_PUBLISHER_CONFLICT"
                    other_socket.receive_json()
            assert conflict.value.code == 4409

            websocket.send_json({"type": "audio.stop", "request_id": "audio-stop-test"})
            stopped = websocket.receive_json()
            assert stopped == {
                "type": "audio.stopped",
                "last_received_sequence": 0,
                "last_processed_sequence": 0,
                "last_final_transcript_sequence": 1,
            }

        timeline = client.get(f"/api/v1/sessions/{session_id}/transcript")
        assert timeline.status_code == 200
        assert timeline.json()["selected_version"]["source"] == "LIVE"
        assert [item["text"] for item in timeline.json()["segments"]] == ["저장되는 최종 문장"]
        assert timeline.json()["gaps"] == []
        segment_id = timeline.json()["segments"][0]["id"]
        assert client.get(f"/api/v1/transcript-segments/{segment_id}").status_code == 200
        assert (
            client.get(
                f"/api/v1/sessions/{session_id}/transcript?start_sequence=1&end_sequence=1"
            ).status_code
            == 400
        )
        assert (
            client.get(
                f"/api/v1/sessions/{session_id}/transcript?transcript_version_id="
                f"{timeline.json()['selected_version']['id']}&start_sequence=1&end_sequence=1"
            ).status_code
            == 200
        )
        asyncio.run(_add_live_versions(migrated_database_url, session_id))
        versions = client.get(f"/api/v1/sessions/{session_id}/transcript/versions?limit=1")
        assert versions.status_code == 200
        assert versions.json()["items"][0]["version"] == 3
        assert versions.json()["next_cursor"] is not None
        next_versions = client.get(
            f"/api/v1/sessions/{session_id}/transcript/versions?limit=1&cursor="
            f"{versions.json()['next_cursor']}"
        )
        assert next_versions.status_code == 200
        assert next_versions.json()["items"][0]["version"] == 2

    recording, segments, gaps = asyncio.run(_audio_rows(migrated_database_url, session_id))
    assert recording.last_received_sequence == 0
    assert recording.last_processed_sequence == 0
    assert len(segments) == 1
    assert segments[0].utterance_id == "utt-live-0"
    assert gaps == []
    assert "transcript.final" in asyncio.run(_event_types(migrated_database_url, session_id))


def test_partial_stt_never_creates_a_transcript_row_or_outbox_event(
    migrated_database_url: str,
) -> None:
    user_id, session_id = asyncio.run(_seed_live_session(migrated_database_url))
    partial = STTPartial(
        utterance_id="utt-partial-0",
        revision=1,
        audio_sequence_start=0,
        audio_sequence_end=0,
        start_ms=0,
        end_ms=500,
        text="아직 확정 전 문장",
    )
    settings = _settings(migrated_database_url)
    app = create_app(
        settings=settings,
        database=create_database(settings),
        streaming_stt_provider=DeterministicStreamingSTTProvider({0: [partial]}),
    )
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}/audio?ticket={_audio_ticket(client, session_id)}"
        ) as websocket:
            websocket.send_json(_start("partial-publisher"))
            websocket.receive_json()
            websocket.send_bytes(_frame(0, 0))
            assert websocket.receive_json()["type"] == "audio.ack"

    _, segments, _ = asyncio.run(_audio_rows(migrated_database_url, session_id))
    event_types = asyncio.run(_event_types(migrated_database_url, session_id))
    assert segments == []
    assert "transcript.partial" not in event_types


def test_sequence_gap_is_recorded_without_fabricating_transcript_text(
    migrated_database_url: str,
) -> None:
    user_id, session_id = asyncio.run(_seed_live_session(migrated_database_url))
    settings = _settings(migrated_database_url)
    app = create_app(
        settings=settings,
        database=create_database(settings),
        streaming_stt_provider=DeterministicStreamingSTTProvider(),
    )
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}/audio?ticket={_audio_ticket(client, session_id)}"
        ) as websocket:
            websocket.send_json(_start("gap-publisher"))
            websocket.receive_json()
            websocket.send_bytes(_frame(0, 0))
            websocket.receive_json()
            websocket.send_bytes(_frame(2, 1_000))
            error = websocket.receive_json()
            ack = websocket.receive_json()
            assert error["code"] == "AUDIO_SEQUENCE_GAP"
            assert ack["received_through"] == 2

    _, segments, gaps = asyncio.run(_audio_rows(migrated_database_url, session_id))
    assert segments == []
    assert len(gaps) == 1
    assert gaps[0].reason == "SEQUENCE_GAP"
    assert gaps[0].start_ms == 500
    assert gaps[0].end_ms == 1_000


def test_reconnect_rejects_unprocessed_audio_after_stt_state_is_lost(
    migrated_database_url: str,
) -> None:
    user_id, session_id = asyncio.run(_seed_live_session(migrated_database_url))
    settings = _settings(migrated_database_url)
    app = create_app(
        settings=settings,
        database=create_database(settings),
        streaming_stt_provider=UnavailableStreamingSTTProvider(),
    )
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}/audio?ticket={_audio_ticket(client, session_id)}"
        ) as websocket:
            websocket.send_json(_start("interrupted-publisher"))
            websocket.receive_json()
            websocket.send_bytes(_frame(0, 0))
            assert websocket.receive_json()["code"] == "STT_UNAVAILABLE"
            assert websocket.receive_json()["processed_through"] is None

        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(
                f"/api/v1/ws/sessions/{session_id}/audio?ticket={_audio_ticket(client, session_id)}"
            ) as websocket:
                websocket.send_json(_start("interrupted-publisher", resume_from_sequence=0))
                assert websocket.receive_json() == {
                    "type": "audio.resume_rejected",
                    "reason": "SERVER_STATE_LOST",
                }
                websocket.receive_json()
        assert closed.value.code == 4409

    recording, segments, gaps = asyncio.run(_audio_rows(migrated_database_url, session_id))
    assert recording.last_received_sequence == 0
    assert recording.last_processed_sequence == -1
    assert segments == []
    assert [(gap.reason, gap.start_ms, gap.end_ms) for gap in gaps] == [("SERVER_STATE_LOST", 0, 0)]


def test_stt_timeout_returns_a_safe_error_without_advancing_processed_ack(
    migrated_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SlowStreamingSTTProvider:
        async def transcribe(self, _frame: object) -> tuple[object, ...]:
            await asyncio.sleep(0.1)
            return ()

    monkeypatch.setattr(realtime_router, "LIVE_STT_TIMEOUT_SECONDS", 0.001)
    user_id, session_id = asyncio.run(_seed_live_session(migrated_database_url))
    settings = _settings(migrated_database_url)
    app = create_app(
        settings=settings,
        database=create_database(settings),
        streaming_stt_provider=SlowStreamingSTTProvider(),
    )
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}/audio?ticket={_audio_ticket(client, session_id)}"
        ) as websocket:
            websocket.send_json(_start("timeout-publisher"))
            websocket.receive_json()
            websocket.send_bytes(_frame(0, 0))
            assert websocket.receive_json()["code"] == "STT_UNAVAILABLE"
            assert websocket.receive_json() == {
                "type": "audio.ack",
                "received_through": 0,
                "processed_through": None,
                "queue_depth_ms": 0,
            }


def test_session_end_fences_live_pcm_and_hands_the_logical_recording_to_upload(
    migrated_database_url: str,
) -> None:
    user_id, session_id = asyncio.run(_seed_live_session(migrated_database_url))
    settings = _settings(migrated_database_url)
    app = create_app(
        settings=settings,
        database=create_database(settings),
        streaming_stt_provider=DeterministicStreamingSTTProvider(),
    )
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/api/v1/ws/sessions/{session_id}/audio?ticket={_audio_ticket(client, session_id)}"
        ) as websocket:
            websocket.send_json(_start("ending-publisher"))
            websocket.receive_json()
            websocket.send_bytes(_frame(0, 0))
            websocket.receive_json()

            ended = client.post(
                f"/api/v1/sessions/{session_id}/end",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "end-live-audio"},
            )
            assert ended.status_code == 202
            websocket.send_bytes(_frame(1, 500))
            rejected = websocket.receive_json()
            assert rejected == {"type": "audio.resume_rejected", "reason": "SESSION_CLOSING"}
            with pytest.raises(WebSocketDisconnect) as closed:
                websocket.receive_json()
            assert closed.value.code == 4409

    recording, _, _ = asyncio.run(_audio_rows(migrated_database_url, session_id))
    assert recording.status == "UPLOAD_PENDING"
    assert recording.capture_ended_at is not None
    assert recording.live_audio_lease_expires_at is None
