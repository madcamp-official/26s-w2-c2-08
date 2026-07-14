"""Integration coverage for synchronous, non-persistent question draft help."""

import asyncio
import base64
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.models.questions import AIJob, Question
from tbd.providers.ai import (
    FakeLLMProvider,
    FakeProviderBehavior,
    LLMGenerationRequest,
    LLMGenerationResult,
    ProviderUnavailableError,
)

pytestmark = pytest.mark.integration
TRUSTED_ORIGIN = {"Origin": "http://localhost:5173"}


class RecordingLLMProvider:
    """Return one valid candidate while preserving the private request for assertions."""

    def __init__(self) -> None:
        self.requests: list[LLMGenerationRequest] = []

    async def generate(
        self, request: LLMGenerationRequest, *, timeout: object
    ) -> LLMGenerationResult:
        del timeout
        self.requests.append(request)
        return LLMGenerationResult(content="  cafe\u0301는 왜 정규화하나요?  ")


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
                        "name": f"draft-{role}-{uuid4().hex[:8]}",
                        "email": f"draft-{role}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                ids.append(user_id)
            return ids[0], ids[1]
    finally:
        await database.dispose()


def test_question_draft_help_is_ephemeral_and_uses_the_versioned_prompt(
    migrated_database_url: str,
) -> None:
    professor_id, student_id = asyncio.run(_seed_users(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    provider = RecordingLLMProvider()
    app = create_app(settings=settings, database=database, llm_provider=provider)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "draft-course-001"},
                json={"title": "질문 초안 수업", "semester": "2026 여름학기"},
            )
            assert course.status_code == 201
            course_id = course.json()["id"]
            join_code = course.json()["join_code"]
            created_session = client.post(
                f"/api/v1/courses/{course_id}/sessions",
                headers=TRUSTED_ORIGIN,
                json={"lecture_date": "2026-07-14"},
            )
            assert created_session.status_code == 201
            session_id = created_session.json()["id"]
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN
                ).status_code
                == 200
            )

            current_user["id"] = student_id
            assert (
                client.post(
                    "/api/v1/courses/join",
                    headers=TRUSTED_ORIGIN,
                    json={"join_code": join_code},
                ).status_code
                == 201
            )
            response = client.post(
                f"/api/v1/sessions/{session_id}/question-drafts",
                json={"draft": "  cafe\u0301는 왜 정규화하나요?  "},
            )
            assert response.status_code == 200
            assert response.json() == {"suggestions": ["café는 왜 정규화하나요?"]}
            assert len(provider.requests) == 1
            request = provider.requests[0]
            assert request.purpose == "QUESTION_DRAFT_HELP"
            assert request.prompt_version == "question-draft-help-v1"
            assert request.messages[-1].content == "café는 왜 정규화하나요?"

            too_long = client.post(
                f"/api/v1/sessions/{session_id}/question-drafts",
                json={"draft": "가" * 501},
            )
            assert too_long.status_code == 422
            assert too_long.json()["error"]["details"] == {
                "field": "draft",
                "reason": "MAX_LENGTH_EXCEEDED",
                "max_length": 500,
                "actual_length": 501,
            }

        async def assert_nothing_was_persisted() -> None:
            async with database.session_factory() as session:
                question_count = await session.scalar(select(func.count()).select_from(Question))
                job_count = await session.scalar(select(func.count()).select_from(AIJob))
                assert question_count == 0
                assert job_count == 0

        asyncio.run(assert_nothing_was_persisted())
    finally:
        asyncio.run(database.dispose())


def test_question_draft_help_hides_provider_failures(migrated_database_url: str) -> None:
    professor_id, student_id = asyncio.run(_seed_users(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    provider = FakeLLMProvider(FakeProviderBehavior(failure=ProviderUnavailableError()))
    app = create_app(settings=settings, database=database, llm_provider=provider)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "draft-course-002"},
                json={"title": "장애 수업", "semester": "2026 여름학기"},
            )
            course_id = course.json()["id"]
            join_code = course.json()["join_code"]
            created_session = client.post(
                f"/api/v1/courses/{course_id}/sessions",
                headers=TRUSTED_ORIGIN,
                json={"lecture_date": "2026-07-14"},
            )
            session_id = created_session.json()["id"]
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN
                ).status_code
                == 200
            )
            current_user["id"] = student_id
            assert (
                client.post(
                    "/api/v1/courses/join",
                    headers=TRUSTED_ORIGIN,
                    json={"join_code": join_code},
                ).status_code
                == 201
            )
            response = client.post(
                f"/api/v1/sessions/{session_id}/question-drafts",
                json={"draft": "질문을 다듬어 주세요"},
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "AI_PROVIDER_UNAVAILABLE"
            assert "provider" not in response.json()["error"]["message"].lower()
    finally:
        asyncio.run(database.dispose())
