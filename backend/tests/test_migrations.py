"""Fresh PostgreSQL migration round-trip checks."""

import asyncio
import base64
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.models.clustering import Answer
from tbd.models.questions import AIJob, Question
from tbd.models.users import User
from tbd.services.courses import CourseService
from tbd.services.sessions import SessionService

pytestmark = [pytest.mark.integration, pytest.mark.migration]


def _sync_dsn(database_url: str) -> str:
    """Convert the application URL into a synchronous psycopg DSN."""

    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


def _migration_state(database_url: str) -> tuple[str | None, str | None]:
    """Return the Alembic revision and pgvector version if present."""

    with psycopg.connect(_sync_dsn(database_url)) as connection:
        revision = connection.execute("SELECT to_regclass('public.alembic_version')").fetchone()
        current_revision = None
        if revision is not None and revision[0] is not None:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            current_revision = row[0] if row is not None else None

        row = connection.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        vector_version = row[0] if row is not None else None

    return current_revision, vector_version


def test_fresh_upgrade_downgrade_and_reupgrade(
    temporary_database_url: str,
    alembic_runner: Callable[..., None],
) -> None:
    """Every migration must work from empty DB, downgrade, and apply again."""

    alembic_runner(temporary_database_url, "upgrade", "head")
    revision, vector_version = _migration_state(temporary_database_url)
    assert revision is not None
    assert vector_version is not None
    upgraded_revision = revision

    alembic_runner(temporary_database_url, "downgrade", "base")
    revision, vector_version = _migration_state(temporary_database_url)
    assert revision is None
    assert vector_version is None

    alembic_runner(temporary_database_url, "upgrade", "head")
    revision, vector_version = _migration_state(temporary_database_url)
    assert revision == upgraded_revision
    assert vector_version is not None


def test_embeddinggemma_migration_discards_old_vectors_and_queues_reindex(
    temporary_database_url: str,
    alembic_runner: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An existing fake Chunk cannot survive the incompatible vector profile change."""

    alembic_runner(temporary_database_url, "upgrade", "20260714_0017")
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=temporary_database_url,
        storage_root=tmp_path / "uploads",
        idempotency_response_encryption_key=base64.b64encode(b"i" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"e" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"h" * 32).decode(),
    )
    database = create_database(settings)
    try:

        async def seed_old_profile() -> tuple[object, object]:
            codec = settings.course_join_code_codec
            assert codec is not None
            async with database.session_factory() as session:
                async with session.begin():
                    professor_id = uuid4()
                    session.add(
                        User(
                            id=professor_id,
                            display_name="migration professor",
                            primary_email=f"migration-{uuid4().hex[:12]}@example.test",
                        )
                    )
                    course, _ = await CourseService(codec).create(
                        session,
                        user_id=professor_id,
                        title="임베딩 migration",
                        semester="2026 여름학기",
                    )
                    lecture_session = await SessionService().create(
                        session,
                        course_id=course.course.id,
                        user_id=professor_id,
                        title="재색인 수업",
                        lecture_date=date(2026, 7, 15),
                    )
                    question = Question(
                        session_id=lecture_session.id,
                        author_user_id=professor_id,
                        clustering_sequence=1,
                        content="기존 vector 질문",
                        status="OPEN",
                        reaction_count=0,
                        version=1,
                    )
                    session.add(question)
                    await session.flush()
                    timestamp = datetime.now(UTC)
                    answer = Answer(
                        session_id=lecture_session.id,
                        professor_user_id=professor_id,
                        target_question_id=question.id,
                        target_text_snapshot="기존 vector 질문",
                        status="COMPLETED",
                        text_content="재색인할 교수 답변",
                        started_at=timestamp,
                        completed_at=timestamp,
                        version=1,
                    )
                    session.add(answer)
                    job = AIJob(
                        session_id=lecture_session.id,
                        job_type="KNOWLEDGE_INDEXING",
                        visibility="SHARED",
                        status="PENDING",
                        attempt=1,
                        version=1,
                        blocks_session_completion=False,
                        retryable=False,
                    )
                    session.add(job)
                    await session.flush()
                    await session.execute(
                        text(
                            "INSERT INTO knowledge_chunks ("
                            "course_id, session_id, answer_id, chunk_index, content, token_count, "
                            "embedding, embedding_model, created_by_job_id, created_by_job_attempt"
                            ") VALUES ("
                            ":course_id, :session_id, :answer_id, 0, 'old fake chunk', 3, "
                            "'[0,0,0,0,0,0,0,0]'::vector, 'fake-embedding-v1', :job_id, 1"
                            ")"
                        ),
                        {
                            "course_id": course.course.id,
                            "session_id": lecture_session.id,
                            "answer_id": answer.id,
                            "job_id": job.id,
                        },
                    )
                    return lecture_session.id, job.id

        lecture_session_id, old_job_id = asyncio.run(seed_old_profile())
    finally:
        asyncio.run(database.dispose())

    alembic_runner(temporary_database_url, "upgrade", "head")
    database = create_database(settings)
    try:

        async def read_reindex_state() -> tuple[int, list[AIJob]]:
            async with database.session_factory() as session:
                chunk_count = await session.scalar(text("SELECT count(*) FROM knowledge_chunks"))
                jobs = list(
                    await session.scalars(
                        select(AIJob)
                        .where(AIJob.session_id == lecture_session_id)
                        .order_by(AIJob.created_at, AIJob.id)
                    )
                )
                return int(chunk_count or 0), jobs

        chunk_count, jobs = asyncio.run(read_reindex_state())
    finally:
        asyncio.run(database.dispose())

    assert chunk_count == 0
    old_job = next(job for job in jobs if job.id == old_job_id)
    assert old_job.status == "CANCELLED"
    assert old_job.error_code == "EMBEDDING_PROFILE_REINDEX_REQUIRED"
    assert any(
        job.id != old_job_id and job.job_type == "KNOWLEDGE_INDEXING" and job.status == "PENDING"
        for job in jobs
    )


def test_final_summary_input_migration_backfills_legacy_success(
    temporary_database_url: str,
    alembic_runner: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A legacy successful FINAL_SUMMARY can be backfilled under the old checks."""

    alembic_runner(temporary_database_url, "upgrade", "20260715_0018")
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=temporary_database_url,
        storage_root=tmp_path / "uploads",
        idempotency_response_encryption_key=base64.b64encode(b"i" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"e" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"h" * 32).decode(),
    )
    database = create_database(settings)
    try:

        async def seed_legacy_summary() -> tuple[object, object]:
            codec = settings.course_join_code_codec
            assert codec is not None
            async with database.session_factory() as session:
                async with session.begin():
                    professor_id = uuid4()
                    session.add(
                        User(
                            id=professor_id,
                            display_name="summary migration professor",
                            primary_email=f"summary-migration-{uuid4().hex[:12]}@example.test",
                        )
                    )
                    course, _ = await CourseService(codec).create(
                        session,
                        user_id=professor_id,
                        title="요약 migration",
                        semester="2026 여름학기",
                    )
                    lecture_session = await SessionService().create(
                        session,
                        course_id=course.course.id,
                        user_id=professor_id,
                        title="기존 최종 요약 수업",
                        lecture_date=date(2026, 7, 15),
                    )
                    transcript_id = uuid4()
                    segment_id = uuid4()
                    job_id = uuid4()
                    parameters = {
                        "transcript_id": transcript_id,
                        "segment_id": segment_id,
                        "job_id": job_id,
                        "summary_id": uuid4(),
                        "session_id": lecture_session.id,
                    }
                    statements = (
                        """
                            INSERT INTO transcript_versions (
                                id, session_id, version, source, status, last_sequence,
                                finalized_at
                            ) VALUES (
                                :transcript_id, :session_id, 1, 'LIVE', 'FINALIZED', 1, now()
                            )
                        """,
                        """
                            INSERT INTO transcript_segments (
                                id, session_id, transcript_version_id, sequence,
                                start_ms, end_ms, text
                            ) VALUES (
                                :segment_id, :session_id, :transcript_id, 1,
                                0, 1000, '기존 최종 요약의 Transcript'
                            )
                        """,
                        """
                            UPDATE lecture_sessions
                            SET canonical_transcript_version_id = :transcript_id
                            WHERE id = :session_id
                        """,
                        """
                            INSERT INTO ai_jobs (
                                id, session_id, job_type, visibility, status, attempt,
                                version, blocks_session_completion, retryable,
                                started_at, finished_at
                            ) VALUES (
                                :job_id, :session_id, 'FINAL_SUMMARY', 'SHARED', 'SUCCEEDED',
                                2, 6, true, true, now(), now()
                            )
                        """,
                        """
                            INSERT INTO lecture_summaries (
                                id, session_id, created_by_job_id, created_by_job_attempt,
                                summary_type, visibility, content,
                                source_transcript_version_id, source_start_segment_id,
                                source_end_segment_id
                            ) VALUES (
                                :summary_id, :session_id, :job_id, 2, 'FINAL',
                                'COURSE_MEMBERS', '기존 최종 요약', :transcript_id,
                                :segment_id, :segment_id
                            )
                        """,
                    )
                    for statement in statements:
                        await session.execute(text(statement), parameters)
                    return job_id, transcript_id

        job_id, transcript_id = asyncio.run(seed_legacy_summary())
    finally:
        asyncio.run(database.dispose())

    alembic_runner(temporary_database_url, "upgrade", "head")

    with psycopg.connect(_sync_dsn(temporary_database_url)) as connection:
        row = connection.execute(
            "SELECT input_transcript_version_id, input_start_segment_id, "
            "input_end_segment_id FROM ai_jobs WHERE id = %s",
            (job_id,),
        ).fetchone()

    assert row == (transcript_id, None, None)
