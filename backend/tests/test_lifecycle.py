"""Integration coverage for irreversible lifecycle and storage cleanup rules."""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text

from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database, transaction
from tbd.models.consistency import StorageDeletionLedger
from tbd.models.courses import CourseMember
from tbd.models.materials import SessionRecording
from tbd.models.sessions import LectureSession
from tbd.models.users import User
from tbd.services.courses import CourseNotFoundError, CourseService
from tbd.services.lifecycle import (
    DELETION_RETRY_BASE,
    AccountOwnedCourseError,
    CourseDeletionBlockedError,
    LifecycleService,
    StorageDeletionWorker,
)
from tbd.services.sessions import SessionService
from tbd.storage import (
    FailureStorage,
    InMemoryStorage,
    StorageKey,
    StorageNamespace,
    StorageNotFoundError,
    StorageOperation,
    sha256_bytes,
)

pytestmark = pytest.mark.integration


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
        idempotency_response_encryption_key=base64.b64encode(b"i" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"e" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"h" * 32).decode(),
    )


async def _new_user(database_url: str) -> UUID:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (display_name, primary_email) "
                    "VALUES (:name, :email) RETURNING id"
                ),
                {
                    "name": f"lifecycle-{uuid4().hex[:8]}",
                    "email": f"lifecycle-{uuid4().hex[:8]}@example.test",
                },
            )
            assert isinstance(user_id, UUID)
            return user_id
    finally:
        await database.dispose()


def test_course_deletion_blocks_active_class_and_leaves_no_access(
    migrated_database_url: str,
) -> None:
    owner_id = asyncio.run(_new_user(migrated_database_url))
    settings = _settings(migrated_database_url)
    codec = settings.course_join_code_codec
    assert codec is not None

    async def scenario() -> None:
        database = create_database(settings)
        try:
            async with database.session_factory() as session:
                async with transaction(session):
                    course, join_code = await CourseService(codec).create(
                        session,
                        user_id=owner_id,
                        title="삭제 정책",
                        semester="2026 여름",
                    )
                    active = await SessionService().create(
                        session,
                        course_id=course.course.id,
                        user_id=owner_id,
                        title="준비 class",
                        lecture_date=datetime.now(UTC).date(),
                    )
                    with pytest.raises(CourseDeletionBlockedError):
                        await LifecycleService().delete_course(
                            session,
                            course_id=course.course.id,
                            user_id=owner_id,
                            now=datetime.now(UTC),
                        )
                    active.status = "COMPLETED"
                    active.started_at = datetime.now(UTC) - timedelta(minutes=2)
                    active.ended_at = datetime.now(UTC) - timedelta(minutes=1)
                    active.completed_at = datetime.now(UTC)

            async with database.session_factory() as session:
                async with transaction(session):
                    await LifecycleService().delete_course(
                        session,
                        course_id=course.course.id,
                        user_id=owner_id,
                        now=datetime.now(UTC),
                    )

            async with database.session_factory() as session:
                async with transaction(session):
                    memberships = await session.scalar(
                        select(func.count())
                        .select_from(CourseMember)
                        .where(CourseMember.course_id == course.course.id)
                    )
                    assert memberships == 0
                    with pytest.raises(CourseNotFoundError):
                        await CourseService(codec).join(
                            session,
                            user_id=uuid4(),
                            raw_join_code=join_code,
                        )
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_recording_deletion_worker_and_account_anonymization(
    migrated_database_url: str,
) -> None:
    owner_id = asyncio.run(_new_user(migrated_database_url))
    settings = _settings(migrated_database_url)
    codec = settings.course_join_code_codec
    assert codec is not None

    async def scenario() -> None:
        database = create_database(settings)
        storage = InMemoryStorage()
        try:
            now = datetime.now(UTC)
            temporary_key = StorageKey.new(StorageNamespace.TEMPORARY)
            final_key = StorageKey.new(StorageNamespace.FINAL)
            await storage.create_temporary(temporary_key)
            payload = b"private recording"
            await storage.append(
                temporary_key,
                payload,
                expected_offset=0,
                checksum=sha256_bytes(payload),
            )
            await storage.promote(temporary_key, final_key, expected_sha256=sha256_bytes(payload))

            async with database.session_factory() as session:
                async with transaction(session):
                    course, _ = await CourseService(codec).create(
                        session,
                        user_id=owner_id,
                        title="보관 정책",
                        semester="2026 여름",
                    )
                    lecture_session = LectureSession(
                        course_id=course.course.id,
                        created_by_user_id=owner_id,
                        title="완료 class",
                        lecture_date=now.date(),
                        status="COMPLETED",
                        started_at=now - timedelta(minutes=2),
                        ended_at=now - timedelta(minutes=1),
                        completed_at=now,
                        version=1,
                    )
                    session.add(lecture_session)
                    await session.flush()
                    recording = SessionRecording(
                        session_id=lecture_session.id,
                        publisher_user_id=owner_id,
                        publisher_client_stream_id_hash=b"x" * 32,
                        last_received_sequence=-1,
                        last_processed_sequence=-1,
                        last_captured_offset_ms=0,
                        status="UPLOADED",
                        content_type="audio/webm",
                        byte_size=len(payload),
                        duration_ms=1000,
                        storage_key=final_key.value,
                        capture_started_at=now - timedelta(minutes=2),
                        capture_ended_at=now - timedelta(minutes=1),
                        uploaded_at=now,
                        retention_expires_at=now + timedelta(days=30),
                        version=1,
                    )
                    session.add(recording)
                    await session.flush()
                    await LifecycleService().delete_recording(
                        session,
                        session_id=lecture_session.id,
                        user_id=owner_id,
                        now=now,
                    )

            failing_storage = FailureStorage(storage)
            failing_storage.fail_next(StorageOperation.DELETE)
            worker = StorageDeletionWorker(database.session_factory, failing_storage)
            assert await worker.run_once(now=now) is True

            async with database.session_factory() as session:
                ledger = await session.scalar(select(StorageDeletionLedger))
                assert ledger is not None
                assert ledger.state == "PENDING"
                assert ledger.attempt == 1
                assert ledger.next_attempt_at == now + DELETION_RETRY_BASE

            assert await worker.run_once(now=now + DELETION_RETRY_BASE) is True
            with pytest.raises(StorageNotFoundError):
                await storage.stat(final_key)

            async with database.session_factory() as session:
                async with transaction(session):
                    ledger = await session.scalar(select(StorageDeletionLedger))
                    assert ledger is not None
                    assert ledger.state == "SUCCEEDED"
                    assert ledger.succeeded_at == now + DELETION_RETRY_BASE
                    with pytest.raises(AccountOwnedCourseError):
                        await LifecycleService().withdraw_account(
                            session,
                            user_id=owner_id,
                            now=now,
                        )

            async with database.session_factory() as session:
                async with transaction(session):
                    await LifecycleService().delete_course(
                        session,
                        course_id=course.course.id,
                        user_id=owner_id,
                        now=now,
                    )
                    await LifecycleService().withdraw_account(
                        session,
                        user_id=owner_id,
                        now=now,
                    )

            async with database.session_factory() as session:
                user = await session.get(User, owner_id)
                assert user is not None
                assert user.deleted_at == now
                assert user.display_name == "탈퇴한 사용자"
                assert user.primary_email is None
                assert user.avatar_url is None
        finally:
            await database.dispose()

    asyncio.run(scenario())
