"""Integration coverage for professor Answer capture and record text policies."""

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
from tbd.providers.ai.fake import FakeQuestionClusteringProvider
from tbd.services.clustering import QuestionClusteringWorker

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
            user_ids: list[UUID] = []
            for role in ("professor", "student"):
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (display_name, primary_email) "
                        "VALUES (:name, :email) RETURNING id"
                    ),
                    {
                        "name": f"answer-{role}-{uuid4().hex[:8]}",
                        "email": f"answer-{role}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                user_ids.append(user_id)
            return user_ids[0], user_ids[1]
    finally:
        await database.dispose()


async def _add_final_segment(database_url: str, session_id: str) -> None:
    database = create_database(_settings(database_url))
    try:
        async with database.session_factory() as session:
            async with session.begin():
                version = await session.scalar(
                    select(TranscriptVersion).where(
                        TranscriptVersion.session_id == UUID(session_id),
                        TranscriptVersion.source == "LIVE",
                    )
                )
                assert version is not None
                session.add(
                    TranscriptSegment(
                        session_id=UUID(session_id),
                        transcript_version_id=version.id,
                        sequence=1,
                        start_ms=0,
                        end_ms=1200,
                        text="교수자의 답변 구간입니다.",
                    )
                )
                version.last_sequence = 1
    finally:
        await database.dispose()


async def _move_answer_start_forward(database_url: str, answer_id: str) -> datetime:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            started_at = await connection.scalar(
                text(
                    "UPDATE answers SET started_at = started_at + :offset "
                    "WHERE id = :answer_id RETURNING started_at"
                ),
                {"answer_id": UUID(answer_id), "offset": timedelta(seconds=1)},
            )
            assert isinstance(started_at, datetime)
            return started_at
    finally:
        await database.dispose()


async def _mark_completed(database_url: str, session_id: str) -> None:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE lecture_sessions "
                    "SET status = 'COMPLETED', ended_at = now(), completed_at = now() "
                    "WHERE id = :session_id"
                ),
                {"session_id": UUID(session_id)},
            )
    finally:
        await database.dispose()


def test_answer_capture_completion_cancellation_and_record_text_conflict(
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
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-course-001"},
                json={"title": "Answer 수업", "semester": "2026 여름학기"},
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
            first_question = client.post(
                f"/api/v1/sessions/{session_id}/questions",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-question-001"},
                json={"content": "왜 이 알고리즘을 사용하나요?"},
            )
            second_question = client.post(
                f"/api/v1/sessions/{session_id}/questions",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-question-002"},
                json={"content": "시간 복잡도는 어떻게 계산하나요?"},
            )
            assert first_question.status_code == second_question.status_code == 201

            current_user["id"] = professor_id
            worker = QuestionClusteringWorker(
                database.session_factory, FakeQuestionClusteringProvider()
            )
            assert (
                asyncio.run(worker.run_once(now=datetime.now(UTC) + timedelta(seconds=6))) is True
            )
            clusters = client.get(f"/api/v1/sessions/{session_id}/question-clusters")
            assert clusters.status_code == 200
            representative = clusters.json()["items"][0]["representative_question"]
            representative_capture = client.post(
                f"/api/v1/sessions/{session_id}/answers",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-representative-001"},
                json={
                    "answer_type": "VOICE",
                    "target": {
                        "type": "AI_REPRESENTATIVE_QUESTION",
                        "representative_question_id": representative["id"],
                    },
                },
            )
            assert representative_capture.status_code == 201
            assert (
                representative_capture.json()["target_text_snapshot"] == representative["content"]
            )
            assert (
                client.post(
                    f"/api/v1/answers/{representative_capture.json()['id']}/cancel",
                    headers={
                        **TRUSTED_ORIGIN,
                        "Idempotency-Key": "answer-representative-cancel-001",
                    },
                ).status_code
                == 204
            )
            voice = client.post(
                f"/api/v1/sessions/{session_id}/answers",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-voice-001"},
                json={
                    "answer_type": "VOICE",
                    "target": {
                        "type": "STUDENT_QUESTION",
                        "question_id": first_question.json()["question"]["id"],
                    },
                },
            )
            assert voice.status_code == 201
            assert voice.json()["status"] == "CAPTURING"
            assert voice.json()["target_text_snapshot"] == "왜 이 알고리즘을 사용하나요?"

            another_capture = client.post(
                f"/api/v1/sessions/{session_id}/answers",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-voice-002"},
                json={
                    "answer_type": "VOICE",
                    "target": {
                        "type": "STUDENT_QUESTION",
                        "question_id": second_question.json()["question"]["id"],
                    },
                },
            )
            assert another_capture.status_code == 409
            assert another_capture.json()["error"]["code"] == "ANSWER_CAPTURE_ACTIVE"

            blocked_end = client.post(
                f"/api/v1/sessions/{session_id}/end",
                headers={
                    **TRUSTED_ORIGIN,
                    "Idempotency-Key": "answer-capture-blocks-end-001",
                },
            )
            assert blocked_end.status_code == 409
            assert blocked_end.json()["error"]["code"] == "ANSWER_CAPTURE_ACTIVE"
            assert client.get(f"/api/v1/sessions/{session_id}").json()["status"] == "LIVE"

            asyncio.run(_add_final_segment(migrated_database_url, session_id))
            started_at = asyncio.run(
                _move_answer_start_forward(migrated_database_url, voice.json()["id"])
            )
            completed = client.post(
                f"/api/v1/answers/{voice.json()['id']}/complete",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-complete-001"},
            )
            replay = client.post(
                f"/api/v1/answers/{voice.json()['id']}/complete",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-complete-001"},
            )
            assert completed.status_code == 200, completed.text
            assert replay.status_code == 200, replay.text
            assert completed.json() == replay.json()
            assert completed.json()["status"] == "COMPLETED"
            assert completed.json()["start_sequence"] == 1
            assert completed.json()["end_sequence"] == 1
            assert datetime.fromisoformat(completed.json()["completed_at"]) >= started_at

            cancelling = client.post(
                f"/api/v1/sessions/{session_id}/answers",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-voice-003"},
                json={
                    "answer_type": "VOICE",
                    "target": {
                        "type": "STUDENT_QUESTION",
                        "question_id": second_question.json()["question"]["id"],
                    },
                },
            )
            assert cancelling.status_code == 201
            cancelled = client.post(
                f"/api/v1/answers/{cancelling.json()['id']}/cancel",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-cancel-001"},
            )
            cancel_replay = client.post(
                f"/api/v1/answers/{cancelling.json()['id']}/cancel",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-cancel-001"},
            )
            assert cancelled.status_code == cancel_replay.status_code == 204
            assert client.get(f"/api/v1/answers/{cancelling.json()['id']}").status_code == 404

            asyncio.run(_mark_completed(migrated_database_url, session_id))
            text_answer = client.post(
                f"/api/v1/sessions/{session_id}/answers",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-text-001"},
                json={
                    "answer_type": "TEXT",
                    "target": {
                        "type": "STUDENT_QUESTION",
                        "question_id": second_question.json()["question"]["id"],
                    },
                    "text_content": "  cafe\u0301를 정규화한 텍스트 Answer입니다.  ",
                },
            )
            assert text_answer.status_code == 201
            assert text_answer.json()["text_content"] == "café를 정규화한 텍스트 Answer입니다."

            updated = client.patch(
                f"/api/v1/answers/{text_answer.json()['id']}",
                headers=TRUSTED_ORIGIN,
                json={"text_content": "수정한 설명", "expected_version": 1},
            )
            assert updated.status_code == 200
            stale = client.patch(
                f"/api/v1/answers/{text_answer.json()['id']}",
                headers=TRUSTED_ORIGIN,
                json={"text_content": "로컬 초안", "expected_version": 1},
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "ANSWER_VERSION_CONFLICT"
            assert stale.json()["error"]["details"] == {
                "current_version": 2,
                "current_text_content": "수정한 설명",
            }

            withdrawn = client.delete(
                f"/api/v1/answers/{text_answer.json()['id']}/text",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "answer-withdraw-001"},
            )
            assert withdrawn.status_code == 204
            assert client.get(f"/api/v1/answers/{text_answer.json()['id']}").status_code == 404
    finally:
        asyncio.run(database.dispose())
