"""Integration coverage for Course-scoped class lifecycle transitions."""

import asyncio
import base64
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database, transaction
from tbd.models.knowledge import LectureSummary
from tbd.models.materials import TranscriptSegment, TranscriptVersion
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession
from tbd.providers.ai import FakeLLMProvider, LLMGenerationRequest
from tbd.services.courses import CourseService
from tbd.services.postprocessing import SessionPostprocessingWorker
from tbd.services.sessions import ActiveSessionExistsError, SessionService

pytestmark = pytest.mark.integration
TRUSTED_ORIGIN = {"Origin": "http://localhost:5173"}


class _CapturingLLMProvider(FakeLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[LLMGenerationRequest] = []

    async def generate(self, request: LLMGenerationRequest, *, timeout: timedelta):
        self.requests.append(request)
        return await super().generate(request, timeout=timeout)


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


async def _append_live_transcript(database_url: str, session_id: UUID, version_id: UUID) -> None:
    database = create_database(_settings(database_url))
    try:
        async with database.session_factory() as session:
            async with session.begin():
                version = await session.get(TranscriptVersion, version_id)
                assert version is not None
                version.last_sequence = 1
                session.add(
                    TranscriptSegment(
                        session_id=session_id,
                        transcript_version_id=version_id,
                        sequence=1,
                        start_ms=0,
                        end_ms=1_000,
                        text="녹음 원본이 없어도 LIVE Transcript로 요약합니다.",
                    )
                )
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
        live_version_id = UUID(started.json()["canonical_transcript_version_id"])

        asyncio.run(
            _append_live_transcript(migrated_database_url, UUID(session_id), live_version_id)
        )

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

    provider = _CapturingLLMProvider()
    worker = SessionPostprocessingWorker(database.session_factory, provider)
    assert asyncio.run(worker.run_once()) is True
    assert asyncio.run(worker.run_once()) is True

    final_summary_request = next(
        request for request in provider.requests if request.purpose == "final-summary-v2"
    )
    assert final_summary_request.prompt_version == "final-summary-v2"
    assert [message.role for message in final_summary_request.messages] == ["system", "user"]
    system_prompt = final_summary_request.messages[0].content
    assert "실제로 다룬 내용만 요약" in system_prompt
    assert "추가 질문을 제안" in system_prompt
    assert "이모지를 사용하지 마세요" in system_prompt
    assert "<transcript>" in final_summary_request.messages[1].content

    async def final_summary_rows() -> tuple[AIJob, LectureSummary]:
        async with database.session_factory() as session:
            job = await session.scalar(
                select(AIJob).where(
                    AIJob.session_id == UUID(session_id),
                    AIJob.job_type == "FINAL_SUMMARY",
                )
            )
            summary = await session.scalar(
                select(LectureSummary).where(
                    LectureSummary.session_id == UUID(session_id),
                    LectureSummary.summary_type == "FINAL",
                )
            )
            assert job is not None
            assert summary is not None
            return job, summary

    summary_job, summary = asyncio.run(final_summary_rows())
    assert summary_job.status == "SUCCEEDED"
    assert summary_job.input_transcript_version_id == live_version_id
    assert summary.source_transcript_version_id == live_version_id

    async def remove_summary_ledger() -> None:
        async with database.session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(LectureSummary).where(LectureSummary.session_id == UUID(session_id))
                )
                await session.execute(
                    delete(AIJob).where(
                        AIJob.session_id == UUID(session_id),
                        AIJob.job_type == "FINAL_SUMMARY",
                    )
                )

    asyncio.run(remove_summary_ledger())
    assert asyncio.run(worker.run_once()) is True
    assert asyncio.run(worker.run_once()) is True
    repaired_job, repaired_summary = asyncio.run(final_summary_rows())
    assert repaired_job.status == "SUCCEEDED"
    assert repaired_job.input_transcript_version_id == live_version_id
    assert repaired_summary.source_transcript_version_id == live_version_id
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


async def _seed_session_cursor_pages(
    database_url: str,
    *,
    owner_id: UUID,
) -> tuple[UUID, UUID, list[UUID], UUID]:
    """Create two Courses and deterministic history rows without running postprocessing."""

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
                    title="페이지 수업",
                    semester="2026 여름학기",
                )
                other_course, _ = await CourseService(codec).create(
                    session,
                    user_id=owner_id,
                    title="다른 수업",
                    semester="2026 여름학기",
                )
                course_id = course.course.id
                completed_specs = [
                    (
                        UUID("00000000-0000-0000-0000-000000000101"),
                        datetime(2026, 7, 15, 9, tzinfo=UTC),
                        date(2026, 7, 1),
                    ),
                    (
                        UUID("00000000-0000-0000-0000-000000000103"),
                        datetime(2026, 7, 14, 9, tzinfo=UTC),
                        date(2026, 7, 31),
                    ),
                    (
                        UUID("00000000-0000-0000-0000-000000000102"),
                        datetime(2026, 7, 14, 9, tzinfo=UTC),
                        date(2026, 7, 30),
                    ),
                    (
                        UUID("00000000-0000-0000-0000-000000000104"),
                        datetime(2026, 7, 13, 9, tzinfo=UTC),
                        date(2026, 7, 29),
                    ),
                ]
                for session_id, started_at, lecture_date in completed_specs:
                    session.add(
                        LectureSession(
                            id=session_id,
                            course_id=course_id,
                            created_by_user_id=owner_id,
                            title=f"완료 {session_id}",
                            lecture_date=lecture_date,
                            status="COMPLETED",
                            started_at=started_at,
                            ended_at=started_at + timedelta(hours=1),
                            completed_at=started_at + timedelta(hours=2),
                            version=1,
                        )
                    )
                ready_id = UUID("00000000-0000-0000-0000-0000000001ff")
                session.add(
                    LectureSession(
                        id=ready_id,
                        course_id=course_id,
                        created_by_user_id=owner_id,
                        title="시작 전 class",
                        lecture_date=date(2026, 8, 1),
                        status="READY",
                        version=1,
                    )
                )
                await session.flush()
                return (
                    course_id,
                    other_course.course.id,
                    [item[0] for item in completed_specs],
                    ready_id,
                )
    finally:
        await database.dispose()


def test_session_list_uses_scoped_signed_keyset_cursor(
    migrated_database_url: str,
) -> None:
    """Completed history is stable while tampered or cross-scope cursors fail closed."""

    owner_id = asyncio.run(_seed_user(migrated_database_url))
    outsider_id = asyncio.run(_seed_user(migrated_database_url))
    course_id, other_course_id, expected_ids, ready_id = asyncio.run(
        _seed_session_cursor_pages(migrated_database_url, owner_id=owner_id)
    )
    current_user = {"id": owner_id}
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]

    with TestClient(app) as client:
        first = client.get(
            f"/api/v1/courses/{course_id}/sessions",
            params={"status": "COMPLETED", "limit": 2},
        )
        assert first.status_code == 200
        assert [UUID(item["id"]) for item in first.json()["items"]] == expected_ids[:2]
        cursor = first.json()["next_cursor"]
        assert isinstance(cursor, str)

        second = client.get(
            f"/api/v1/courses/{course_id}/sessions",
            params={"status": "COMPLETED", "limit": 2, "cursor": cursor},
        )
        assert second.status_code == 200
        assert [UUID(item["id"]) for item in second.json()["items"]] == expected_ids[2:]
        assert second.json()["next_cursor"] is None

        all_statuses = client.get(f"/api/v1/courses/{course_id}/sessions", params={"limit": 10})
        assert all_statuses.status_code == 200
        assert UUID(all_statuses.json()["items"][-1]["id"]) == ready_id

        replacement = "A" if cursor[-1] != "A" else "B"
        invalid_requests = [
            (
                f"/api/v1/courses/{course_id}/sessions",
                {"status": "COMPLETED", "cursor": f"{cursor[:-1]}{replacement}"},
            ),
            (
                f"/api/v1/courses/{other_course_id}/sessions",
                {"status": "COMPLETED", "cursor": cursor},
            ),
            (
                f"/api/v1/courses/{course_id}/sessions",
                {"status": "LIVE", "cursor": cursor},
            ),
            (
                f"/api/v1/courses/{course_id}/sessions",
                {"cursor": cursor},
            ),
        ]
        for path, params in invalid_requests:
            response = client.get(path, params=params)
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "INVALID_CURSOR"

        current_user["id"] = outsider_id
        forbidden = client.get(f"/api/v1/courses/{course_id}/sessions")
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "COURSE_ACCESS_DENIED"

        missing = client.get(f"/api/v1/courses/{uuid4()}/sessions")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
