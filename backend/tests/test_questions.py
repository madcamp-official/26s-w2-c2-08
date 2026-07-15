"""Integration coverage for anonymous LIVE Questions and reactions."""

import asyncio
import base64
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database, transaction
from tbd.models.consistency import OutboxEvent
from tbd.models.questions import Question, QuestionReaction
from tbd.services.questions import QuestionService

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
                        "name": f"question-user-{index}-{uuid4().hex[:8]}",
                        "email": f"question-{index}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                user_ids.append(user_id)
            return user_ids
    finally:
        await database.dispose()


def test_live_questions_are_anonymous_normalized_and_reaction_safe(
    migrated_database_url: str,
) -> None:
    """Questions remain distinct by ID and reactions use a per-user ledger."""

    professor_id, first_student_id, second_student_id, outsider_id = asyncio.run(
        _seed_users(migrated_database_url, 4)
    )
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "question-course-001"},
            json={"title": "질문 수업", "semester": "2026 여름학기"},
        )
        assert course.status_code == 201
        course_id = course.json()["id"]
        join_code = course.json()["join_code"]
        created_session = client.post(
            f"/api/v1/courses/{course_id}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"title": "LIVE 질문", "lecture_date": "2026-07-14"},
        )
        assert created_session.status_code == 201
        session_id = created_session.json()["id"]
        assert (
            client.post(f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN).status_code
            == 200
        )

        current_user["id"] = first_student_id
        assert (
            client.post(
                "/api/v1/courses/join", headers=TRUSTED_ORIGIN, json={"join_code": join_code}
            ).status_code
            == 201
        )
        first = client.post(
            f"/api/v1/sessions/{session_id}/questions",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "question-create-001"},
            json={"content": "  cafe\u0301는 왜 정규화하나요?  "},
        )
        replay = client.post(
            f"/api/v1/sessions/{session_id}/questions",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "question-create-001"},
            json={"content": "  cafe\u0301는 왜 정규화하나요?  "},
        )
        assert first.status_code == 201
        assert replay.status_code == 201
        assert replay.json() == first.json()
        first_question = first.json()["question"]
        assert first_question["content"] == "café는 왜 정규화하나요?"
        assert first_question["reacted_by_me"] is False
        assert "author_user_id" not in first_question
        assert "author" not in first_question
        assert first.json()["clustering_state"]["requested_through_sequence"] == 1
        assert first.json()["clustering_state"]["active_job_id"] is not None

        # The same normalized content submitted with a different request is a
        # second anonymous Question, never a destructive deduplication.
        second = client.post(
            f"/api/v1/sessions/{session_id}/questions",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "question-create-002"},
            json={"content": "café는 왜 정규화하나요?"},
        )
        assert second.status_code == 201
        assert second.json()["question"]["id"] != first_question["id"]
        assert second.json()["question"]["content"] == first_question["content"]

        too_long = client.post(
            f"/api/v1/sessions/{session_id}/questions",
            headers=TRUSTED_ORIGIN,
            json={"content": "가" * 301},
        )
        assert too_long.status_code == 422
        assert too_long.json()["error"]["details"] == {
            "field": "content",
            "reason": "MAX_LENGTH_EXCEEDED",
            "max_length": 300,
            "actual_length": 301,
        }

        page_one = client.get(
            f"/api/v1/sessions/{session_id}/questions",
            params={"sort": "RECENT", "limit": 1},
        )
        assert page_one.status_code == 200
        cursor = page_one.json()["next_cursor"]
        assert cursor is not None
        page_two = client.get(
            f"/api/v1/sessions/{session_id}/questions",
            params={"sort": "RECENT", "limit": 1, "cursor": cursor},
        )
        assert page_two.status_code == 200
        assert page_two.json()["items"][0]["id"] != page_one.json()["items"][0]["id"]
        invalid_scope = client.get(
            f"/api/v1/sessions/{session_id}/questions",
            params={"sort": "POPULAR", "cursor": cursor},
        )
        assert invalid_scope.status_code == 400
        assert invalid_scope.json()["error"]["code"] == "INVALID_CURSOR"

        self_reaction = client.put(
            f"/api/v1/questions/{first_question['id']}/reaction", headers=TRUSTED_ORIGIN
        )
        assert self_reaction.status_code == 409
        assert self_reaction.json()["error"]["code"] == "SELF_REACTION_FORBIDDEN"

        current_user["id"] = second_student_id
        assert (
            client.post(
                "/api/v1/courses/join", headers=TRUSTED_ORIGIN, json={"join_code": join_code}
            ).status_code
            == 201
        )
        added = client.put(
            f"/api/v1/questions/{first_question['id']}/reaction", headers=TRUSTED_ORIGIN
        )
        repeated = client.put(
            f"/api/v1/questions/{first_question['id']}/reaction", headers=TRUSTED_ORIGIN
        )
        assert added.status_code == 200
        assert repeated.status_code == 200
        assert (
            added.json()
            == repeated.json()
            == {
                "question_id": first_question["id"],
                "reaction_count": 1,
                "reacted_by_me": True,
            }
        )
        assert (
            client.delete(
                f"/api/v1/questions/{first_question['id']}/reaction", headers=TRUSTED_ORIGIN
            ).status_code
            == 204
        )
        assert (
            client.delete(
                f"/api/v1/questions/{first_question['id']}/reaction", headers=TRUSTED_ORIGIN
            ).status_code
            == 204
        )

        current_user["id"] = professor_id
        ended = client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "end-question-session"},
        )
        assert ended.status_code == 202

        current_user["id"] = first_student_id
        post_class = client.post(
            f"/api/v1/sessions/{session_id}/questions",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "question-create-after-class"},
            json={"content": "수업 후 복습하다가 생긴 질문입니다."},
        )
        assert post_class.status_code == 201
        assert post_class.json()["question"]["clustering_sequence"] == 3
        assert post_class.json()["clustering_state"]["requested_through_sequence"] == 2

        current_user["id"] = outsider_id
        assert client.get(f"/api/v1/questions/{first_question['id']}").status_code == 404

    async def assert_public_question_event() -> None:
        async with database.session_factory() as session:
            event = await session.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.event_type == "question.created",
                    OutboxEvent.session_id == UUID(session_id),
                )
                .order_by(OutboxEvent.created_at.asc())
            )
            assert event is not None
            assert event.payload["id"] == first_question["id"]
            assert "author_user_id" not in event.payload
            assert "author" not in event.payload

    asyncio.run(assert_public_question_event())

    asyncio.run(database.dispose())


async def _exercise_concurrent_reaction(database_url: str) -> None:
    """The Session/question locks make concurrent same-user votes idempotent."""

    professor_id, author_id, reactor_id = await _seed_users(database_url, 3)
    settings = _settings(database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "question-concurrency-course"},
                json={"title": "반응 동시성", "semester": "2026 여름학기"},
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
            current_user["id"] = author_id
            assert (
                client.post(
                    "/api/v1/courses/join", headers=TRUSTED_ORIGIN, json={"join_code": join_code}
                ).status_code
                == 201
            )
            question = client.post(
                f"/api/v1/sessions/{session_id}/questions",
                headers=TRUSTED_ORIGIN,
                json={"content": "동시 반응은 한 번만 저장됩니다."},
            )
            assert question.status_code == 201
            question_id = UUID(question.json()["question"]["id"])
            current_user["id"] = reactor_id
            assert (
                client.post(
                    "/api/v1/courses/join", headers=TRUSTED_ORIGIN, json={"join_code": join_code}
                ).status_code
                == 201
            )

        async def react_once() -> bool:
            async with database.session_factory() as session:
                async with transaction(session):
                    _, reacted = await QuestionService(
                        auth_secret=settings.auth_secret_key.get_secret_value()
                    ).add_reaction(session, question_id=question_id, user_id=reactor_id)
                    return reacted

        results = await asyncio.gather(react_once(), react_once())
        assert results == [True, True]
        async with database.session_factory() as session:
            reaction_count = await session.scalar(
                select(func.count())
                .select_from(QuestionReaction)
                .where(
                    QuestionReaction.question_id == question_id,
                    QuestionReaction.user_id == reactor_id,
                )
            )
            question = await session.get(Question, question_id)
            assert reaction_count == 1
            assert question is not None
            assert question.reaction_count == 1
    finally:
        await database.dispose()


def test_concurrent_question_reaction_uses_one_ledger_row(
    migrated_database_url: str,
) -> None:
    asyncio.run(_exercise_concurrent_reaction(migrated_database_url))
