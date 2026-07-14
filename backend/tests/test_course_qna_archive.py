"""Integration coverage for Course-wide anonymous Q&A archive reads."""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.repositories.course_qna import CourseQnaArchiveRepository

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


async def _seed_users(database_url: str, tmp_path: Path) -> tuple[UUID, UUID]:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.engine.begin() as connection:
            ids: list[UUID] = []
            for label in ("owner", "outsider"):
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (display_name, primary_email) "
                        "VALUES (:name, :email) RETURNING id"
                    ),
                    {
                        "name": f"qna-{label}-{uuid4().hex[:8]}",
                        "email": f"qna-{label}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                ids.append(user_id)
            return ids[0], ids[1]
    finally:
        await database.dispose()


async def _seed_archive(
    database_url: str,
    tmp_path: Path,
    *,
    course_id: UUID,
    owner_id: UUID,
) -> dict[str, UUID]:
    database = create_database(_settings(database_url, tmp_path))
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    ids = {
        "active_session": uuid4(),
        "completed_session": uuid4(),
        "older_session": uuid4(),
        "live_version": uuid4(),
        "start_segment": uuid4(),
        "end_segment": uuid4(),
        "answered_question": uuid4(),
        "capturing_question": uuid4(),
        "unanswered_question": uuid4(),
        "completed_question": uuid4(),
        "completed_question_2": uuid4(),
        "completed_question_3": uuid4(),
        "older_question": uuid4(),
        "representative": uuid4(),
        "discarded_representative": uuid4(),
        "representative_job": uuid4(),
        "discarded_job": uuid4(),
        "question_answer": uuid4(),
        "capturing_answer": uuid4(),
        "representative_answer": uuid4(),
        "discarded_answer": uuid4(),
        "organization_job": uuid4(),
        "organization": uuid4(),
    }
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO lecture_sessions (
                        id, course_id, created_by_user_id, title, lecture_date, status,
                        version, started_at, ended_at, completed_at, created_at, updated_at
                    ) VALUES (
                        :active_session, :course_id, :owner_id, '현재 class', '2026-07-15',
                        'LIVE', 1, :active_started_at, NULL, NULL, :active_created_at, :now
                    ), (
                        :completed_session, :course_id, :owner_id, '완료 class', '2026-07-14',
                        'COMPLETED', 1, :completed_started_at, :completed_ended_at,
                        :completed_at, :completed_created_at, :completed_at
                    ), (
                        :older_session, :course_id, :owner_id, '이전 완료 class', '2026-07-12',
                        'COMPLETED', 1, :older_started_at, :older_ended_at,
                        :older_completed_at, :older_created_at, :older_completed_at
                    )
                    """
                ),
                {
                    **ids,
                    "course_id": course_id,
                    "owner_id": owner_id,
                    "now": now,
                    "active_started_at": now - timedelta(hours=1),
                    "active_created_at": now - timedelta(hours=2),
                    # Deliberately newer than the initially active class. The
                    # active cursor must retain its frozen first group after
                    # that class transitions to COMPLETED.
                    "completed_started_at": now + timedelta(hours=1),
                    "completed_ended_at": now + timedelta(hours=2),
                    "completed_at": now + timedelta(hours=3),
                    "completed_created_at": now - timedelta(days=2),
                    "older_started_at": now - timedelta(days=3),
                    "older_ended_at": now - timedelta(days=3) + timedelta(hours=1),
                    "older_completed_at": now - timedelta(days=3) + timedelta(hours=2),
                    "older_created_at": now - timedelta(days=4),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO transcript_versions (
                        id, session_id, version, source, status, recording_id,
                        created_by_job_id, created_by_job_attempt, last_sequence,
                        finalized_at, failed_at, created_at, updated_at
                    ) VALUES (
                        :live_version, :active_session, 1, 'LIVE', 'FINALIZING', NULL,
                        NULL, NULL, 2, NULL, NULL, :created_at, :created_at
                    )
                    """
                ),
                {**ids, "created_at": now - timedelta(hours=1)},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO transcript_segments (
                        id, session_id, transcript_version_id, sequence, utterance_id,
                        start_ms, end_ms, recording_start_ms, recording_end_ms, text,
                        created_by_job_id, created_by_job_attempt, created_at
                    ) VALUES (
                        :start_segment, :active_session, :live_version, 1, NULL,
                        0, 1000, NULL, NULL, '첫 번째 답변 구간', NULL, NULL, :created_at
                    ), (
                        :end_segment, :active_session, :live_version, 2, NULL,
                        1000, 2000, NULL, NULL, '두 번째 답변 구간', NULL, NULL, :created_at
                    )
                    """
                ),
                {**ids, "created_at": now - timedelta(minutes=50)},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_jobs (
                        id, session_id, requester_user_id, job_type, visibility, status,
                        attempt, target_answer_id, input_transcript_version_id,
                        input_start_segment_id, input_end_segment_id, clustering_mode,
                        input_through_sequence, base_revision,
                        blocks_session_completion, retryable, started_at, finished_at,
                        version, created_at, updated_at
                    ) VALUES (
                        :representative_job, :active_session, NULL, 'QUESTION_CLUSTERING',
                        'SHARED', 'SUCCEEDED', 1, NULL, NULL, NULL, NULL,
                        'LIVE_INCREMENTAL', 3, 0,
                        false, false, :started_at, :finished_at, 1, :started_at, :finished_at
                    ), (
                        :discarded_job, :active_session, NULL, 'QUESTION_CLUSTERING',
                        'SHARED', 'SUCCEEDED', 1, NULL, NULL, NULL, NULL,
                        'LIVE_INCREMENTAL', 3, 0,
                        false, false, :started_at, :finished_at, 1, :started_at, :finished_at
                    ), (
                        :organization_job, :active_session, NULL, 'ANSWER_ORGANIZATION',
                        'SHARED', 'SUCCEEDED', 2, :representative_answer, :live_version,
                        :start_segment, :end_segment, NULL, NULL, NULL,
                        true, false, :started_at, :finished_at, 1, :started_at, :finished_at
                    )
                    """
                ),
                {
                    **ids,
                    "started_at": now - timedelta(minutes=45),
                    "finished_at": now - timedelta(minutes=44),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO questions (
                        id, session_id, author_user_id, clustering_sequence, content,
                        status, reaction_count, version, created_at, updated_at
                    ) VALUES
                        (:answered_question, :active_session, :owner_id, 1,
                         '답변된 학생 질문', 'ANSWERED', 2, 1, :answered_at, :answered_at),
                        (:capturing_question, :active_session, :owner_id, 2,
                         '캡처 중 학생 질문', 'SELECTED', 1, 1, :capturing_at, :capturing_at),
                        (:unanswered_question, :active_session, :owner_id, 3,
                         '미답변 학생 질문', 'OPEN', 0, 1, :unanswered_at, :unanswered_at),
                        (:completed_question, :completed_session, :owner_id, 1,
                         '완료 class 미답변 질문', 'OPEN', 0, 1,
                         :completed_question_at, :completed_question_at),
                        (:completed_question_2, :completed_session, :owner_id, 2,
                         '완료 class 두 번째 질문', 'OPEN', 0, 1,
                         :completed_question_2_at, :completed_question_2_at),
                        (:completed_question_3, :completed_session, :owner_id, 3,
                         '완료 class 세 번째 질문', 'OPEN', 0, 1,
                         :completed_question_3_at, :completed_question_3_at),
                        (:older_question, :older_session, :owner_id, 1,
                         '이전 완료 class 질문', 'OPEN', 0, 1,
                         :older_question_at, :older_question_at)
                    """
                ),
                {
                    **ids,
                    "owner_id": owner_id,
                    "answered_at": now - timedelta(minutes=10),
                    "capturing_at": now - timedelta(minutes=20),
                    "unanswered_at": now - timedelta(minutes=30),
                    "completed_question_at": now - timedelta(days=1),
                    "completed_question_2_at": now - timedelta(days=1, minutes=1),
                    "completed_question_3_at": now - timedelta(days=1, minutes=2),
                    "older_question_at": now - timedelta(days=3, minutes=30),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO ai_representative_questions (
                        id, session_id, text, status, lifecycle_status,
                        created_by_job_id, created_by_job_attempt, created_in_generation,
                        preserved_at, discarded_at, version, created_at
                    ) VALUES (
                        :representative, :active_session, '답변된 AI 대표질문', 'ANSWERED',
                        'ACTIVE', :representative_job, 1, 1, NULL, NULL, 1, :created_at
                    ), (
                        :discarded_representative, :active_session, '폐기된 대표질문', 'OPEN',
                        'DISCARDED', :discarded_job, 1, 1, NULL, :discarded_at, 1, :created_at
                    )
                    """
                ),
                {
                    **ids,
                    "created_at": now - timedelta(minutes=40),
                    "discarded_at": now - timedelta(minutes=15),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO answers (
                        id, session_id, professor_user_id, target_question_id,
                        target_representative_question_id, target_text_snapshot, status,
                        source_transcript_version_id, capture_started_after_sequence,
                        start_segment_id, end_segment_id, text_content, version,
                        started_at, completed_at, created_at, updated_at
                    ) VALUES (
                        :question_answer, :active_session, :owner_id, :answered_question,
                        NULL, '답변된 학생 질문', 'COMPLETED', NULL, NULL, NULL, NULL,
                        '학생 질문의 공개 답변', 1, :question_started_at,
                        :question_completed_at, :question_started_at, :question_completed_at
                    ), (
                        :capturing_answer, :active_session, :owner_id, :capturing_question,
                        NULL, '캡처 중 학생 질문', 'CAPTURING', :live_version, 0, NULL, NULL,
                        NULL, 1, :capturing_started_at, NULL,
                        :capturing_started_at, :capturing_started_at
                    ), (
                        :representative_answer, :active_session, :owner_id, NULL,
                        :representative, '답변된 AI 대표질문', 'COMPLETED', :live_version, 0,
                        :start_segment, :end_segment, NULL, 1, :representative_started_at,
                        :representative_completed_at, :representative_started_at,
                        :representative_completed_at
                    ), (
                        :discarded_answer, :active_session, :owner_id, NULL,
                        :discarded_representative, '폐기된 대표질문', 'COMPLETED', NULL, NULL,
                        NULL, NULL, '손상 원장에 남은 답변', 1, :discarded_started_at,
                        :discarded_completed_at, :discarded_started_at,
                        :discarded_completed_at
                    )
                    """
                ),
                {
                    **ids,
                    "owner_id": owner_id,
                    "question_started_at": now - timedelta(minutes=9),
                    "question_completed_at": now - timedelta(minutes=8),
                    "capturing_started_at": now - timedelta(minutes=19),
                    "representative_started_at": now - timedelta(minutes=6),
                    "representative_completed_at": now - timedelta(minutes=5),
                    "discarded_started_at": now - timedelta(minutes=4),
                    "discarded_completed_at": now - timedelta(minutes=3),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO answer_organizations (
                        id, answer_id, session_id, content, source_transcript_version_id,
                        source_start_segment_id, source_end_segment_id, created_by_job_id,
                        created_by_job_attempt, model_name, prompt_version, created_at
                    ) VALUES (
                        :organization, :representative_answer, :active_session,
                        '음성 Answer의 공개 AI 정리문', :live_version,
                        :start_segment, :end_segment, :organization_job, 2,
                        'private-model', 'private-prompt-v1', :created_at
                    )
                    """
                ),
                {**ids, "created_at": now - timedelta(minutes=2)},
            )
        return ids
    finally:
        await database.dispose()


async def _complete_active_session(
    database_url: str,
    tmp_path: Path,
    *,
    session_id: UUID,
) -> None:
    database = create_database(_settings(database_url, tmp_path))
    now = datetime(2026, 7, 15, 13, 0, tzinfo=UTC)
    try:
        async with database.engine.begin() as connection:
            # CAPTURING is not public and is removed by the normal end flow.
            await connection.execute(
                text("DELETE FROM answers WHERE session_id = :session_id AND status = 'CAPTURING'"),
                {"session_id": session_id},
            )
            await connection.execute(
                text(
                    """
                    UPDATE lecture_sessions
                    SET status = 'COMPLETED', ended_at = :now, completed_at = :now,
                        version = version + 1, updated_at = :now
                    WHERE id = :session_id
                    """
                ),
                {"session_id": session_id, "now": now},
            )
    finally:
        await database.dispose()


async def _delete_course(
    database_url: str,
    tmp_path: Path,
    *,
    course_id: UUID,
) -> None:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("UPDATE courses SET deleted_at = now() WHERE id = :course_id"),
                {"course_id": course_id},
            )
    finally:
        await database.dispose()


async def _repository_archive_count(
    database_url: str,
    tmp_path: Path,
    *,
    course_id: UUID,
    user_id: UUID,
) -> int:
    """Exercise the payload query's own lifecycle and membership gates."""

    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.session_factory() as session:
            rows = await CourseQnaArchiveRepository().list_course_archive(
                session,
                course_id=course_id,
                user_id=user_id,
                after=None,
                limit=100,
            )
            return len(rows)
    finally:
        await database.dispose()


def _assert_private_fields_absent(value: object) -> None:
    forbidden = {
        "author_user_id",
        "professor_user_id",
        "created_by_job_id",
        "created_by_job_attempt",
        "created_in_generation",
        "job_id",
        "attempt",
        "retryable",
        "model_name",
        "prompt_version",
        "source_transcript_version_id",
    }
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value)
        for child in value.values():
            _assert_private_fields_absent(child)
    elif isinstance(value, list):
        for child in value:
            _assert_private_fields_absent(child)


def test_course_qna_archive_is_private_scoped_and_transition_stable(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    owner_id, outsider_id = asyncio.run(_seed_users(migrated_database_url, tmp_path))
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": owner_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]

    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "qna-archive-course"},
                json={"title": "Course Q&A 모음", "semester": "2026 여름학기"},
            )
            assert course.status_code == 201
            course_id = UUID(course.json()["id"])
            ids = asyncio.run(
                _seed_archive(
                    migrated_database_url,
                    tmp_path,
                    course_id=course_id,
                    owner_id=owner_id,
                )
            )

            first = client.get(f"/api/v1/courses/{course_id}/qna", params={"limit": 2})
            assert first.status_code == 200, first.text
            first_items = first.json()["items"]
            assert [item["target_type"] for item in first_items] == [
                "AI_REPRESENTATIVE_QUESTION",
                "STUDENT_QUESTION",
            ]
            assert first_items[0]["representative_question_id"] == str(ids["representative"])
            assert first_items[0]["answer"]["id"] == str(ids["representative_answer"])
            assert set(first_items[0]["answer"]) == {
                "id",
                "answer_type",
                "status",
                "text_content",
                "organization",
                "completed_at",
            }
            assert first_items[0]["answer"]["answer_type"] == "VOICE"
            assert first_items[0]["answer"]["organization"] == {
                "content": "음성 Answer의 공개 AI 정리문"
            }
            assert first_items[1]["question"]["id"] == str(ids["answered_question"])
            assert first_items[1]["answer"]["id"] == str(ids["question_answer"])
            _assert_private_fields_absent(first_items)
            first_cursor = first.json()["next_cursor"]
            assert isinstance(first_cursor, str)

            replacement = "A" if first_cursor[-1] != "A" else "B"
            tampered = client.get(
                f"/api/v1/courses/{course_id}/qna",
                params={"cursor": f"{first_cursor[:-1]}{replacement}"},
            )
            assert tampered.status_code == 400
            assert tampered.json()["error"]["code"] == "INVALID_CURSOR"

            asyncio.run(
                _complete_active_session(
                    migrated_database_url,
                    tmp_path,
                    session_id=ids["active_session"],
                )
            )
            second = client.get(
                f"/api/v1/courses/{course_id}/qna",
                params={"limit": 2, "cursor": first_cursor},
            )
            assert second.status_code == 200, second.text
            second_items = second.json()["items"]
            assert [item["question"]["id"] for item in second_items] == [
                str(ids["capturing_question"]),
                str(ids["unanswered_question"]),
            ]
            assert all(item["answer"] is None for item in second_items)
            assert all(item["session"]["id"] == str(ids["active_session"]) for item in second_items)
            _assert_private_fields_absent(second_items)
            second_cursor = second.json()["next_cursor"]
            assert isinstance(second_cursor, str)

            third = client.get(
                f"/api/v1/courses/{course_id}/qna",
                params={"limit": 2, "cursor": second_cursor},
            )
            assert third.status_code == 200, third.text
            assert [item["question"]["id"] for item in third.json()["items"]] == [
                str(ids["completed_question"]),
                str(ids["completed_question_2"]),
            ]
            third_cursor = third.json()["next_cursor"]
            assert isinstance(third_cursor, str)

            fourth = client.get(
                f"/api/v1/courses/{course_id}/qna",
                params={"limit": 2, "cursor": third_cursor},
            )
            assert fourth.status_code == 200, fourth.text
            assert [item["question"]["id"] for item in fourth.json()["items"]] == [
                str(ids["completed_question_3"]),
                str(ids["older_question"]),
            ]
            assert fourth.json()["next_cursor"] is None

            all_target_ids = [
                first_items[0]["representative_question_id"],
                first_items[1]["question"]["id"],
                *(item["question"]["id"] for item in second_items),
                *(item["question"]["id"] for item in third.json()["items"]),
                *(item["question"]["id"] for item in fourth.json()["items"]),
            ]
            assert len(all_target_ids) == len(set(all_target_ids)) == 8
            assert str(ids["discarded_representative"]) not in all_target_ids
            assert str(ids["discarded_answer"]) not in {
                item.get("answer", {}).get("id")
                for item in (
                    *first_items,
                    *second_items,
                    *third.json()["items"],
                    *fourth.json()["items"],
                )
                if item.get("answer") is not None
            }

            assert (
                asyncio.run(
                    _repository_archive_count(
                        migrated_database_url,
                        tmp_path,
                        course_id=course_id,
                        user_id=outsider_id,
                    )
                )
                == 0
            )

            current_user["id"] = outsider_id
            forbidden = client.get(f"/api/v1/courses/{course_id}/qna")
            assert forbidden.status_code == 403
            assert forbidden.json()["error"]["code"] == "COURSE_ACCESS_DENIED"

            current_user["id"] = owner_id
            asyncio.run(
                _delete_course(
                    migrated_database_url,
                    tmp_path,
                    course_id=course_id,
                )
            )
            assert (
                asyncio.run(
                    _repository_archive_count(
                        migrated_database_url,
                        tmp_path,
                        course_id=course_id,
                        user_id=owner_id,
                    )
                )
                == 0
            )
            missing = client.get(f"/api/v1/courses/{course_id}/qna")
            assert missing.status_code == 404
            assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    finally:
        asyncio.run(database.dispose())
