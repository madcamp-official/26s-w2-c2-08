"""PostgreSQL integration tests for the relational schema spine."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "ai_jobs",
    "ai_representative_questions",
    "answer_organizations",
    "answer_transcript_mappings",
    "answers",
    "auth_sessions",
    "chat_message_evidence",
    "chat_messages",
    "chat_sessions",
    "course_members",
    "courses",
    "idempotency_records",
    "knowledge_chunks",
    "lecture_materials",
    "lecture_sessions",
    "lecture_summaries",
    "oauth_transactions",
    "outbox_events",
    "question_cluster_members",
    "question_clustering_states",
    "question_clusters",
    "question_reactions",
    "questions",
    "realtime_tickets",
    "recording_uploads",
    "session_recordings",
    "storage_deletion_ledgers",
    "transcript_gaps",
    "transcript_segments",
    "transcript_versions",
    "user_auth_identities",
    "users",
}


def _create_test_database(database_url: str):
    """Create a database resource bound to the isolated migrated database."""

    return create_database(
        Settings(
            _env_file=None,
            app_env=AppEnvironment.TEST,
            database_url=database_url,
        )
    )


async def create_course_and_ready_session(database_url: str) -> tuple[str, str, str]:
    """Create the minimum valid Course aggregate in one deferred-constraint transaction."""

    suffix = uuid4().hex
    database = _create_test_database(database_url)
    try:
        async with database.engine.begin() as connection:
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (display_name, primary_email) "
                    "VALUES (:name, :email) RETURNING id"
                ),
                {"name": f"schema-{suffix}", "email": f"schema-{suffix}@example.test"},
            )
            course_id = await connection.scalar(
                text(
                    "INSERT INTO courses (title, semester, created_by_user_id, "
                    "join_code_lookup_hash, join_code_lookup_key_version, "
                    "join_code_ciphertext, join_code_nonce, join_code_key_version) "
                    "VALUES (:title, '2026-2', :user_id, digest(:lookup, 'sha256'), 1, "
                    "decode('01', 'hex'), substring(digest(:nonce, 'sha256') FROM 1 FOR 12), 1) "
                    "RETURNING id"
                ),
                {
                    "title": f"Schema {suffix}",
                    "user_id": user_id,
                    "lookup": suffix,
                    "nonce": suffix,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO course_members (course_id, user_id, role) "
                    "VALUES (:course_id, :user_id, 'PROFESSOR')"
                ),
                {"course_id": course_id, "user_id": user_id},
            )
            session_id = await connection.scalar(
                text(
                    "INSERT INTO lecture_sessions (course_id, created_by_user_id, title, lecture_date) "
                    "VALUES (:course_id, :user_id, :title, CURRENT_DATE) RETURNING id"
                ),
                {"course_id": course_id, "user_id": user_id, "title": f"Session {suffix}"},
            )
        return str(user_id), str(course_id), str(session_id)
    finally:
        await database.dispose()


def test_schema_spine_creates_all_documented_tables_and_guards(
    migrated_database_url: str,
) -> None:
    """All relational tables, indexes, and integrity functions must be installed."""

    async def read_schema() -> tuple[set[str], set[str], set[str]]:
        database = _create_test_database(migrated_database_url)
        try:
            async with database.engine.connect() as connection:
                tables = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                            )
                        )
                    ).scalars()
                )
                indexes = set(
                    (
                        await connection.execute(
                            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
                        )
                    ).scalars()
                )
                functions = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT proname FROM pg_proc "
                                "WHERE proname IN ('set_updated_at', 'enforce_course_owner_membership', "
                                "'enforce_active_material_limit')"
                            )
                        )
                    ).scalars()
                )
                return tables, indexes, functions
        finally:
            await database.dispose()

    tables, indexes, functions = asyncio.run(read_schema())

    assert EXPECTED_TABLES <= tables
    assert {
        "course_members_one_professor_per_course_uq",
        "lecture_sessions_one_active_per_course_uq",
        "lecture_materials_active_display_name_uq",
        "ai_jobs_one_active_question_clustering_uq",
        "answers_one_per_question_uq",
        "outbox_events_unpublished_idx",
    } <= indexes
    assert functions == {
        "set_updated_at",
        "enforce_course_owner_membership",
        "enforce_active_material_limit",
    }


def test_course_and_session_concurrency_constraints_are_enforced(
    migrated_database_url: str,
) -> None:
    """Course ownership and one nonterminal class are database-enforced invariants."""

    async def assert_constraints() -> None:
        user_id, course_id, _ = await create_course_and_ready_session(migrated_database_url)
        database = _create_test_database(migrated_database_url)
        try:
            async with database.engine.connect() as connection:
                with pytest.raises(IntegrityError):
                    async with connection.begin():
                        await connection.execute(
                            text(
                                "INSERT INTO lecture_sessions "
                                "(course_id, created_by_user_id, title, lecture_date) "
                                "VALUES (:course_id, :user_id, 'Concurrent class', CURRENT_DATE)"
                            ),
                            {"course_id": course_id, "user_id": user_id},
                        )

                with pytest.raises(IntegrityError):
                    async with connection.begin():
                        await connection.execute(
                            text(
                                "DELETE FROM course_members "
                                "WHERE course_id = :course_id AND user_id = :user_id"
                            ),
                            {"course_id": course_id, "user_id": user_id},
                        )
        finally:
            await database.dispose()

    asyncio.run(assert_constraints())


def test_material_limit_guard_rejects_the_eleventh_active_pdf(
    migrated_database_url: str,
) -> None:
    """The trigger serializes concurrent upload checks through the session row lock."""

    async def assert_limit() -> None:
        _, _, session_id = await create_course_and_ready_session(migrated_database_url)
        database = _create_test_database(migrated_database_url)
        try:
            async with database.engine.connect() as connection:
                async with connection.begin():
                    for ordinal in range(10):
                        await connection.execute(
                            text(
                                "INSERT INTO lecture_materials "
                                "(session_id, original_filename, display_name, byte_size, storage_key) "
                                "VALUES (:session_id, :filename, :display_name, 1, :storage_key)"
                            ),
                            {
                                "session_id": session_id,
                                "filename": f"source-{ordinal}.pdf",
                                "display_name": f"source-{ordinal}.pdf",
                                "storage_key": f"internal/test/{uuid4()}",
                            },
                        )

                with pytest.raises(IntegrityError):
                    async with connection.begin():
                        await connection.execute(
                            text(
                                "INSERT INTO lecture_materials "
                                "(session_id, original_filename, display_name, byte_size, storage_key) "
                                "VALUES (:session_id, 'eleventh.pdf', 'eleventh.pdf', 1, :storage_key)"
                            ),
                            {"session_id": session_id, "storage_key": f"internal/test/{uuid4()}"},
                        )
        finally:
            await database.dispose()

    asyncio.run(assert_limit())
