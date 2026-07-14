"""Integration coverage for requester-only Summary and private RAG Chat."""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.models.materials import TranscriptSegment, TranscriptVersion
from tbd.models.sessions import LectureSession
from tbd.providers.ai import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeProviderBehavior,
    ProviderUnavailableError,
)
from tbd.services.personal_ai import PersonalAIWorker

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


async def _seed_users(database_url: str) -> tuple[UUID, UUID]:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            ids: list[UUID] = []
            for role in ("professor", "student"):
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (display_name, primary_email) "
                        "VALUES (:name, :email) RETURNING id"
                    ),
                    {
                        "name": f"personal-ai-{role}",
                        "email": f"personal-ai-{role}-{uuid4().hex[:10]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                ids.append(user_id)
            return ids[0], ids[1]
    finally:
        await database.dispose()


async def _add_live_segment(database_url: str, session_id: str) -> None:
    database = create_database(_settings(database_url))
    try:
        async with database.session_factory() as session:
            async with session.begin():
                lecture_session = await session.get(LectureSession, UUID(session_id))
                assert lecture_session is not None
                version = await session.scalar(
                    select(TranscriptVersion).where(
                        TranscriptVersion.id == lecture_session.canonical_transcript_version_id
                    )
                )
                assert version is not None
                session.add(
                    TranscriptSegment(
                        session_id=lecture_session.id,
                        transcript_version_id=version.id,
                        sequence=1,
                        start_ms=0,
                        end_ms=1200,
                        text="LIVE 수업에서 확정된 첫 번째 강의 문장입니다.",
                    )
                )
                version.last_sequence = 1
    finally:
        await database.dispose()


def _create_live_session(client: TestClient) -> tuple[str, str]:
    course = client.post(
        "/api/v1/courses",
        headers={**TRUSTED_ORIGIN, "Idempotency-Key": "personal-ai-course-001"},
        json={"title": "개인 AI 수업", "semester": "2026 여름학기"},
    )
    assert course.status_code == 201
    created = client.post(
        f"/api/v1/courses/{course.json()['id']}/sessions",
        headers=TRUSTED_ORIGIN,
        json={"lecture_date": "2026-07-14"},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert (
        client.post(f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN).status_code
        == 200
    )
    return session_id, course.json()["join_code"]


def test_personal_live_resources_are_polled_then_purged_at_class_end(
    migrated_database_url: str,
) -> None:
    professor_id, student_id = asyncio.run(_seed_users(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    try:
        with TestClient(app) as client:
            session_id, join_code = _create_live_session(client)
            asyncio.run(_add_live_segment(migrated_database_url, session_id))

            current_user["id"] = student_id
            assert (
                client.post(
                    "/api/v1/courses/join",
                    headers=TRUSTED_ORIGIN,
                    json={"join_code": join_code},
                ).status_code
                == 201
            )
            summary_created = client.post(
                f"/api/v1/sessions/{session_id}/summaries",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "personal-ai-summary-001"},
                json={"summary_type": "LIVE", "range": None},
            )
            assert summary_created.status_code == 202, summary_created.text
            summary_job_id = summary_created.json()["job"]["id"]

            worker = PersonalAIWorker(
                database.session_factory,
                FakeLLMProvider(),
                FakeEmbeddingProvider(),
            )
            assert (
                asyncio.run(worker.run_once(now=datetime.now(UTC) + timedelta(seconds=1))) is True
            )
            summary_job = client.get(f"/api/v1/jobs/{summary_job_id}")
            assert summary_job.status_code == 200
            assert summary_job.json()["status"] == "SUCCEEDED"
            assert summary_job.json()["result"]["resource_type"] == "SUMMARY"
            summaries = client.get(f"/api/v1/sessions/{session_id}/summaries?summary_type=LIVE")
            assert summaries.status_code == 200
            summary_id = summaries.json()["items"][0]["id"]

            chat_created = client.post(
                f"/api/v1/sessions/{session_id}/chats",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "personal-ai-chat-001"},
                json={"mode": "LIVE"},
            )
            assert chat_created.status_code == 201
            chat_id = chat_created.json()["id"]
            chat_turn = client.post(
                f"/api/v1/chats/{chat_id}/messages",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "personal-ai-chat-turn-001"},
                json={"content": "강의 내용을 요약해 주세요."},
            )
            assert chat_turn.status_code == 202
            chat_job_id = chat_turn.json()["job"]["id"]
            assert (
                asyncio.run(worker.run_once(now=datetime.now(UTC) + timedelta(seconds=1))) is True
            )
            messages = client.get(f"/api/v1/chats/{chat_id}/messages")
            assert messages.status_code == 200
            assert [item["role"] for item in messages.json()["items"]] == ["USER", "ASSISTANT"]
            assert (
                messages.json()["items"][1]["content"] == "저장된 강의 근거에서 확인할 수 없습니다."
            )

            current_user["id"] = professor_id
            assert client.get(f"/api/v1/chats/{chat_id}").status_code == 404
            ended = client.post(
                f"/api/v1/sessions/{session_id}/end",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "personal-ai-end-001"},
            )
            assert ended.status_code == 202, ended.text

            current_user["id"] = student_id
            assert client.get(f"/api/v1/summaries/{summary_id}").status_code == 404
            assert client.get(f"/api/v1/chats/{chat_id}").status_code == 404
            assert client.get(f"/api/v1/jobs/{summary_job_id}").status_code == 404
            assert client.get(f"/api/v1/jobs/{chat_job_id}").status_code == 404
            replay = client.post(
                f"/api/v1/sessions/{session_id}/summaries",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "personal-ai-summary-001"},
                json={"summary_type": "LIVE", "range": None},
            )
            assert replay.status_code == 410
            assert replay.json()["error"]["code"] == "LIVE_AI_RESULT_PURGED"
    finally:
        asyncio.run(database.dispose())


def test_personal_summary_provider_failure_is_private_and_retryable(
    migrated_database_url: str,
) -> None:
    professor_id, _ = asyncio.run(_seed_users(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    app.dependency_overrides[get_current_user_id] = lambda: professor_id
    try:
        with TestClient(app) as client:
            session_id, _ = _create_live_session(client)
            asyncio.run(_add_live_segment(migrated_database_url, session_id))
            created = client.post(
                f"/api/v1/sessions/{session_id}/summaries",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "personal-ai-summary-fail-001"},
                json={"summary_type": "LIVE", "range": None},
            )
            assert created.status_code == 202
            job_id = created.json()["job"]["id"]
            worker = PersonalAIWorker(
                database.session_factory,
                FakeLLMProvider(FakeProviderBehavior(failure=ProviderUnavailableError())),
                FakeEmbeddingProvider(),
            )
            assert (
                asyncio.run(worker.run_once(now=datetime.now(UTC) + timedelta(seconds=1))) is True
            )
            job = client.get(f"/api/v1/jobs/{job_id}")
            assert job.status_code == 200
            assert job.json()["status"] == "FAILED"
            assert job.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
            assert job.json()["retryable"] is True
            assert "provider" not in job.json()["error"]["message"].lower()
    finally:
        asyncio.run(database.dispose())
