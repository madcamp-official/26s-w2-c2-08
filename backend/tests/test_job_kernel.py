"""PostgreSQL integration tests for the shared AIJob execution kernel."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text

from tbd.core.config import AppEnvironment, Settings
from tbd.core.crypto import AesGcmResponseCipher
from tbd.core.request_hash import idempotency_key_hash
from tbd.db import create_database
from tbd.jobs.kernel import JobKernel
from tbd.models.consistency import IdempotencyRecord, OutboxEvent
from tbd.models.enums import AIJobStatus, AIJobVisibility
from tbd.models.questions import AIJob
from tbd.repositories.idempotency import (
    AcquiredIdempotencyRecord,
    IdempotencyKeyReusedError,
    IdempotencyRepository,
    IdempotencyRequest,
    ReplayIdempotencyRecord,
)

pytestmark = pytest.mark.integration


def _database(database_url: str):
    return create_database(
        Settings(
            _env_file=None,
            app_env=AppEnvironment.TEST,
            database_url=database_url,
        )
    )


async def _create_session_aggregate(database_url: str) -> tuple[UUID, UUID]:
    """Create only the durable User/Course/Session rows an AIJob requires."""

    suffix = uuid4().hex
    database = _database(database_url)
    try:
        async with database.engine.begin() as connection:
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (display_name, primary_email) "
                    "VALUES (:name, :email) RETURNING id"
                ),
                {"name": f"kernel-{suffix}", "email": f"kernel-{suffix}@example.test"},
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
                    "title": f"Kernel {suffix}",
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
        assert isinstance(user_id, UUID)
        assert isinstance(session_id, UUID)
        return user_id, session_id
    finally:
        await database.dispose()


async def _enqueue_final_summary_job(database_url: str, session_id: UUID) -> UUID:
    database = _database(database_url)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                job = AIJob(
                    session_id=session_id,
                    job_type="FINAL_SUMMARY",
                    visibility=AIJobVisibility.SHARED,
                    blocks_session_completion=True,
                )
                await JobKernel().enqueue(session, job)
                assert job.id is not None
                return job.id
    finally:
        await database.dispose()


def test_enqueue_job_and_outbox_roll_back_together(migrated_database_url: str) -> None:
    """A failed domain transaction leaves neither the Job nor its queue hint behind."""

    async def assert_atomicity() -> None:
        _, session_id = await _create_session_aggregate(migrated_database_url)
        database = _database(migrated_database_url)
        try:
            with pytest.raises(RuntimeError, match="abort"):
                async with database.session_factory() as session:
                    async with session.begin():
                        await JobKernel().enqueue(
                            session,
                            AIJob(
                                session_id=session_id,
                                job_type="FINAL_SUMMARY",
                                visibility=AIJobVisibility.SHARED,
                                blocks_session_completion=True,
                            ),
                        )
                        raise RuntimeError("abort")

            async with database.session_factory() as session:
                job_count = await session.scalar(select(func.count()).select_from(AIJob))
                event_count = await session.scalar(select(func.count()).select_from(OutboxEvent))
            assert job_count == 0
            assert event_count == 0
        finally:
            await database.dispose()

    asyncio.run(assert_atomicity())


def test_two_workers_cannot_claim_the_same_shared_job(migrated_database_url: str) -> None:
    """SKIP LOCKED lets a second worker continue without executing the locked Job."""

    async def assert_claim_is_exclusive() -> None:
        _, session_id = await _create_session_aggregate(migrated_database_url)
        await _enqueue_final_summary_job(migrated_database_url, session_id)
        database = _database(migrated_database_url)
        first_claimed = asyncio.Event()
        release_first = asyncio.Event()
        kernel = JobKernel()
        now = datetime.now(UTC)

        async def first_worker():
            async with database.session_factory() as session:
                async with session.begin():
                    run = await kernel.claim_next_shared(
                        session,
                        now=now,
                        lease_duration=timedelta(seconds=60),
                    )
                    first_claimed.set()
                    await release_first.wait()
                    return run

        async def second_worker():
            await first_claimed.wait()
            async with database.session_factory() as session:
                async with session.begin():
                    return await kernel.claim_next_shared(
                        session,
                        now=now,
                        lease_duration=timedelta(seconds=60),
                    )

        try:
            first_task = asyncio.create_task(first_worker())
            second_task = asyncio.create_task(second_worker())
            await first_claimed.wait()
            second_result = await asyncio.wait_for(second_task, timeout=3)
            release_first.set()
            first_result = await asyncio.wait_for(first_task, timeout=3)
            assert first_result is not None
            assert second_result is None
        finally:
            release_first.set()
            await database.dispose()

    asyncio.run(assert_claim_is_exclusive())


def test_retry_fences_the_previous_worker_result(migrated_database_url: str) -> None:
    """A late success from attempt one cannot overwrite a running attempt two."""

    async def assert_late_result_is_rejected() -> None:
        _, session_id = await _create_session_aggregate(migrated_database_url)
        job_id = await _enqueue_final_summary_job(migrated_database_url, session_id)
        database = _database(migrated_database_url)
        kernel = JobKernel()
        now = datetime.now(UTC)
        try:
            async with database.session_factory() as session:
                async with session.begin():
                    first_run = await kernel.claim_next_shared(
                        session,
                        now=now,
                        lease_duration=timedelta(seconds=60),
                    )
                    assert first_run is not None
                    assert await kernel.fail(
                        session,
                        first_run,
                        error_code="MODEL_UNAVAILABLE",
                        error_message="모델을 사용할 수 없습니다.",
                        retryable=True,
                        now=now + timedelta(seconds=1),
                    )

            async with database.session_factory() as session:
                async with session.begin():
                    retried = await kernel.retry_failed(
                        session,
                        job_id,
                        now=now + timedelta(seconds=2),
                    )
                    assert retried is not None
                    assert retried.attempt == 2

            async with database.session_factory() as session:
                async with session.begin():
                    second_run = await kernel.claim_next_shared(
                        session,
                        now=now + timedelta(seconds=3),
                        lease_duration=timedelta(seconds=60),
                    )
                    assert second_run is not None
                    assert second_run.attempt == 2
                    assert not await kernel.succeed(
                        session,
                        first_run,
                        now=now + timedelta(seconds=4),
                    )
                    current = await session.get(AIJob, job_id)
                    assert current is not None
                    assert current.status == AIJobStatus.RUNNING
                    assert current.attempt == 2
        finally:
            await database.dispose()

    asyncio.run(assert_late_result_is_rejected())


def test_heartbeat_extends_the_active_worker_lease(migrated_database_url: str) -> None:
    """A current run token extends its lease, while a later watchdog still fences it."""

    async def assert_heartbeat() -> None:
        _, session_id = await _create_session_aggregate(migrated_database_url)
        job_id = await _enqueue_final_summary_job(migrated_database_url, session_id)
        database = _database(migrated_database_url)
        kernel = JobKernel()
        now = datetime.now(UTC)
        try:
            async with database.session_factory() as session:
                async with session.begin():
                    run = await kernel.claim_next_shared(
                        session,
                        now=now,
                        lease_duration=timedelta(seconds=60),
                    )
                    assert run is not None
                    assert await kernel.jobs.heartbeat(
                        session,
                        run,
                        now=now + timedelta(seconds=30),
                        lease_duration=timedelta(seconds=60),
                    )

            async with database.session_factory() as session:
                async with session.begin():
                    assert (
                        await kernel.fail_expired_shared(
                            session,
                            now=now + timedelta(seconds=61),
                            general_timeout=timedelta(minutes=5),
                        )
                        == []
                    )

            async with database.session_factory() as session:
                async with session.begin():
                    assert await kernel.fail_expired_shared(
                        session,
                        now=now + timedelta(seconds=91),
                        general_timeout=timedelta(minutes=5),
                    ) == [job_id]
        finally:
            await database.dispose()

    asyncio.run(assert_heartbeat())


def test_watchdog_failure_is_retryable_and_supersession_is_non_retryable(
    migrated_database_url: str,
) -> None:
    """Lease expiry fences a late worker, while supersession never creates a retry candidate."""

    async def assert_terminal_states() -> None:
        _, session_id = await _create_session_aggregate(migrated_database_url)
        job_id = await _enqueue_final_summary_job(migrated_database_url, session_id)
        database = _database(migrated_database_url)
        kernel = JobKernel()
        now = datetime.now(UTC)
        try:
            async with database.session_factory() as session:
                async with session.begin():
                    run = await kernel.claim_next_shared(
                        session,
                        now=now,
                        lease_duration=timedelta(seconds=60),
                    )
                    assert run is not None

            async with database.session_factory() as session:
                async with session.begin():
                    expired = await kernel.fail_expired_shared(
                        session,
                        now=now + timedelta(seconds=61),
                        general_timeout=timedelta(minutes=5),
                    )
                    assert expired == [job_id]
                    assert not await kernel.succeed(
                        session,
                        run,
                        now=now + timedelta(seconds=62),
                    )
                    failed = await session.get(AIJob, job_id)
                    assert failed is not None
                    assert failed.status == AIJobStatus.FAILED
                    assert failed.error_code == "WORKER_LEASE_EXPIRED"
                    assert failed.retryable

            async with database.session_factory() as session:
                async with session.begin():
                    retried = await kernel.retry_failed(
                        session,
                        job_id,
                        now=now + timedelta(seconds=63),
                    )
                    assert retried is not None
                    assert retried.attempt == 2

            _, second_session_id = await _create_session_aggregate(migrated_database_url)
            second_job_id = await _enqueue_final_summary_job(
                migrated_database_url,
                second_session_id,
            )
            async with database.session_factory() as session:
                async with session.begin():
                    assert await kernel.supersede(
                        session,
                        second_job_id,
                        now=now + timedelta(seconds=64),
                    )
                    superseded = await session.get(AIJob, second_job_id)
                    assert superseded is not None
                    assert superseded.status == AIJobStatus.SUPERSEDED
                    assert not superseded.retryable
                    assert (
                        await kernel.retry_failed(
                            session,
                            second_job_id,
                            now=now + timedelta(seconds=65),
                        )
                        is None
                    )
        finally:
            await database.dispose()

    asyncio.run(assert_terminal_states())


def test_idempotency_replays_encrypted_terminal_response(migrated_database_url: str) -> None:
    """The same request reuses a response while a different hash gets a conflict."""

    async def assert_idempotency() -> None:
        user_id, _ = await _create_session_aggregate(migrated_database_url)
        database = _database(migrated_database_url)
        repository = IdempotencyRepository(AesGcmResponseCipher(b"k" * 32))
        now = datetime.now(UTC)
        request = IdempotencyRequest(
            user_id=user_id,
            method="POST",
            route_key="/api/v1/jobs/{job_id}/retry",
            key_hash=idempotency_key_hash("idempotency-test-key"),
            request_hash=b"a" * 32,
        )
        try:
            async with database.session_factory() as session:
                async with session.begin():
                    acquired = await repository.acquire(
                        session,
                        request,
                        now=now,
                        processing_lease=timedelta(minutes=1),
                    )
                    assert isinstance(acquired, AcquiredIdempotencyRecord)
                    await repository.complete(
                        session,
                        record_id=acquired.record_id,
                        status_code=202,
                        body={"job": "safe-id"},
                        now=now,
                    )

            async with database.session_factory() as session:
                async with session.begin():
                    replay = await repository.acquire(
                        session,
                        request,
                        now=now + timedelta(seconds=1),
                        processing_lease=timedelta(minutes=1),
                    )
                    assert isinstance(replay, ReplayIdempotencyRecord)
                    assert replay.status_code == 202
                    assert replay.body == {"job": "safe-id"}
                    stored_ciphertext = await session.scalar(
                        select(IdempotencyRecord.response_body_ciphertext)
                    )
                    assert stored_ciphertext is not None
                    assert b"safe-id" not in stored_ciphertext

            conflicting = IdempotencyRequest(
                user_id=request.user_id,
                method=request.method,
                route_key=request.route_key,
                key_hash=request.key_hash,
                request_hash=b"b" * 32,
            )
            async with database.session_factory() as session:
                async with session.begin():
                    with pytest.raises(IdempotencyKeyReusedError):
                        await repository.acquire(
                            session,
                            conflicting,
                            now=now + timedelta(seconds=2),
                            processing_lease=timedelta(minutes=1),
                        )
        finally:
            await database.dispose()

    asyncio.run(assert_idempotency())
