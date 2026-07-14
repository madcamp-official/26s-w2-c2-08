"""Durable AIJob claim, heartbeat, terminal transition, and retry queries."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.enums import AIJobStatus, AIJobVisibility
from tbd.models.questions import AIJob


@dataclass(frozen=True)
class ClaimedJob:
    """Immutable worker fence returned by an atomic shared Job claim."""

    job_id: UUID
    session_id: UUID
    attempt: int
    run_token: UUID
    job_type: str


class JobRepository:
    """State transitions guarded by the current attempt and run token."""

    async def claim_next_shared(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
        lease_duration: timedelta,
        job_type: str | None = None,
    ) -> ClaimedJob | None:
        """Claim one due SHARED Job with PostgreSQL SKIP LOCKED semantics."""

        timestamp = now or datetime.now(UTC)
        conditions = self._pending_shared_conditions(timestamp)
        if job_type is not None:
            conditions.append(AIJob.job_type == job_type)
        job = await session.scalar(
            select(AIJob)
            .where(*conditions)
            .order_by(AIJob.available_at, AIJob.created_at, AIJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None

        return await self._claim_locked(session, job, timestamp, lease_duration)

    async def claim_shared_by_id(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        now: datetime | None = None,
        lease_duration: timedelta,
        job_type: str | None = None,
    ) -> ClaimedJob | None:
        """Claim one already-selected Job after its domain rows are locked."""

        timestamp = now or datetime.now(UTC)
        conditions = [AIJob.id == job_id, *self._pending_shared_conditions(timestamp)]
        if job_type is not None:
            conditions.append(AIJob.job_type == job_type)
        job = await session.scalar(
            select(AIJob).where(*conditions).with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        return await self._claim_locked(session, job, timestamp, lease_duration)

    async def claim_requester_by_id(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        now: datetime | None = None,
        lease_duration: timedelta,
        job_types: tuple[str, ...],
    ) -> ClaimedJob | None:
        """Claim a private Job after its Session aggregate has been fenced.

        Requester-only jobs intentionally do not use the shared outbox path. The
        caller locks the Session (and Chat when applicable) before this row so a
        ``LIVE → PROCESSING`` purge cannot race a late worker result.
        """

        timestamp = now or datetime.now(UTC)
        job = await session.scalar(
            select(AIJob)
            .where(
                AIJob.id == job_id,
                AIJob.status == AIJobStatus.PENDING,
                AIJob.visibility == AIJobVisibility.REQUESTER_ONLY,
                AIJob.available_at <= timestamp,
                AIJob.job_type.in_(job_types),
            )
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        return await self._claim_locked(session, job, timestamp, lease_duration)

    @staticmethod
    def _pending_shared_conditions(timestamp: datetime) -> list[object]:
        return [
            AIJob.status == AIJobStatus.PENDING,
            AIJob.visibility == AIJobVisibility.SHARED,
            AIJob.available_at <= timestamp,
        ]

    @staticmethod
    async def _claim_locked(
        session: AsyncSession,
        job: AIJob,
        timestamp: datetime,
        lease_duration: timedelta,
    ) -> ClaimedJob:
        """Move a row already protected by ``FOR UPDATE`` into the running state."""

        token = uuid4()
        job.status = AIJobStatus.RUNNING
        job.run_token = token
        job.lease_expires_at = timestamp + lease_duration
        job.started_at = timestamp
        job.version += 1
        await session.flush()
        return ClaimedJob(
            job_id=job.id,
            session_id=job.session_id,
            attempt=job.attempt,
            run_token=token,
            job_type=job.job_type,
        )

    async def heartbeat(
        self,
        session: AsyncSession,
        run: ClaimedJob,
        *,
        now: datetime | None = None,
        lease_duration: timedelta,
    ) -> bool:
        """Extend a lease only for the worker that owns the running attempt."""

        timestamp = now or datetime.now(UTC)
        result = await session.execute(
            update(AIJob)
            .where(*self._run_conditions(run))
            .values(
                lease_expires_at=timestamp + lease_duration,
                version=AIJob.version + 1,
            )
        )
        return result.rowcount == 1

    async def succeed(
        self,
        session: AsyncSession,
        run: ClaimedJob,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Mark the current fenced attempt successful without accepting late results."""

        return await self._finish_running(
            session,
            run,
            status=AIJobStatus.SUCCEEDED,
            error_code=None,
            error_message=None,
            retryable=False,
            now=now,
        )

    async def fail(
        self,
        session: AsyncSession,
        run: ClaimedJob,
        *,
        error_code: str,
        error_message: str,
        retryable: bool,
        now: datetime | None = None,
    ) -> bool:
        """Mark the current fenced attempt failed with a safe public error."""

        return await self._finish_running(
            session,
            run,
            status=AIJobStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            now=now,
        )

    async def cancel(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        error_code: str = "JOB_CANCELLED",
        now: datetime | None = None,
    ) -> bool:
        """End a pending or running Job when no replacement work exists."""

        return await self._finish_by_id(
            session,
            job_id,
            status=AIJobStatus.CANCELLED,
            error_code=error_code,
            now=now,
        )

    async def supersede(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        error_code: str = "JOB_SUPERSEDED",
        now: datetime | None = None,
    ) -> bool:
        """End a pending or running Job after a newer logical Job takes its place."""

        return await self._finish_by_id(
            session,
            job_id,
            status=AIJobStatus.SUPERSEDED,
            error_code=error_code,
            now=now,
        )

    async def retry_failed(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        now: datetime | None = None,
    ) -> AIJob | None:
        """Reuse exactly one retryable FAILED row with its next attempt number."""

        timestamp = now or datetime.now(UTC)
        job = await session.scalar(select(AIJob).where(AIJob.id == job_id).with_for_update())
        if job is None or job.status != AIJobStatus.FAILED or not job.retryable:
            return None

        job.status = AIJobStatus.PENDING
        job.attempt += 1
        job.version += 1
        job.available_at = timestamp
        job.run_token = None
        job.lease_expires_at = None
        job.progress_stage = None
        job.progress_percent = None
        job.retryable = False
        job.error_code = None
        job.error_message = None
        job.started_at = None
        job.finished_at = None
        await session.flush()
        return job

    async def fail_expired_shared(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
        general_timeout: timedelta,
    ) -> list[UUID]:
        """Fail stale SHARED workers and timed-out non-HQ postprocessing attempts."""

        timestamp = now or datetime.now(UTC)
        deadline = timestamp - general_timeout
        jobs = list(
            await session.scalars(
                select(AIJob)
                .where(
                    AIJob.status == AIJobStatus.RUNNING,
                    AIJob.visibility == AIJobVisibility.SHARED,
                    or_(
                        AIJob.lease_expires_at < timestamp,
                        and_(
                            AIJob.job_type != "RECORDING_TRANSCRIPTION",
                            AIJob.started_at <= deadline,
                        ),
                    ),
                )
                .order_by(AIJob.lease_expires_at, AIJob.id)
                .with_for_update(skip_locked=True)
            )
        )
        expired: list[UUID] = []
        for job in jobs:
            timed_out = (
                job.job_type != "RECORDING_TRANSCRIPTION"
                and job.started_at is not None
                and job.started_at <= deadline
            )
            job.status = AIJobStatus.FAILED
            job.run_token = None
            job.lease_expires_at = None
            job.finished_at = timestamp
            job.retryable = True
            job.error_code = "JOB_TIMEOUT" if timed_out else "WORKER_LEASE_EXPIRED"
            job.error_message = "작업 실행이 제한 시간을 초과했습니다."
            job.version += 1
            expired.append(job.id)
        await session.flush()
        return expired

    async def fail_expired_requester_only(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
        job_types: tuple[str, ...],
    ) -> list[UUID]:
        """Fail stale private workers without creating a shared outbox event."""

        timestamp = now or datetime.now(UTC)
        jobs = list(
            await session.scalars(
                select(AIJob)
                .where(
                    AIJob.status == AIJobStatus.RUNNING,
                    AIJob.visibility == AIJobVisibility.REQUESTER_ONLY,
                    AIJob.job_type.in_(job_types),
                    AIJob.lease_expires_at < timestamp,
                )
                .order_by(AIJob.lease_expires_at, AIJob.id)
                .with_for_update(skip_locked=True)
            )
        )
        expired: list[UUID] = []
        for job in jobs:
            job.status = AIJobStatus.FAILED
            job.run_token = None
            job.lease_expires_at = None
            job.finished_at = timestamp
            job.retryable = True
            job.error_code = "WORKER_LEASE_EXPIRED"
            job.error_message = "작업 실행 lease가 만료되었습니다."
            job.version += 1
            expired.append(job.id)
        await session.flush()
        return expired

    def _run_conditions(self, run: ClaimedJob) -> tuple[object, ...]:
        return (
            AIJob.id == run.job_id,
            AIJob.attempt == run.attempt,
            AIJob.run_token == run.run_token,
            AIJob.status == AIJobStatus.RUNNING,
        )

    async def _finish_running(
        self,
        session: AsyncSession,
        run: ClaimedJob,
        *,
        status: AIJobStatus,
        error_code: str | None,
        error_message: str | None,
        retryable: bool,
        now: datetime | None,
    ) -> bool:
        timestamp = now or datetime.now(UTC)
        result = await session.execute(
            update(AIJob)
            .where(*self._run_conditions(run))
            .values(
                status=status,
                run_token=None,
                lease_expires_at=None,
                retryable=retryable,
                error_code=error_code,
                error_message=error_message,
                finished_at=timestamp,
                version=AIJob.version + 1,
            )
        )
        return result.rowcount == 1

    async def _finish_by_id(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        status: AIJobStatus,
        error_code: str,
        now: datetime | None,
    ) -> bool:
        timestamp = now or datetime.now(UTC)
        result = await session.execute(
            update(AIJob)
            .where(
                AIJob.id == job_id,
                AIJob.status.in_([AIJobStatus.PENDING, AIJobStatus.RUNNING]),
            )
            .values(
                status=status,
                run_token=None,
                lease_expires_at=None,
                retryable=False,
                error_code=error_code,
                error_message="작업이 현재 실행 정책에 따라 종료되었습니다.",
                finished_at=timestamp,
                version=AIJob.version + 1,
            )
        )
        return result.rowcount == 1
