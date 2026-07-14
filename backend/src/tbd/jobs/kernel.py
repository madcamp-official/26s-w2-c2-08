"""Shared AIJob lifecycle orchestration with transactional Outbox notifications."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.enums import AIJobVisibility
from tbd.models.questions import AIJob
from tbd.repositories.jobs import ClaimedJob, JobRepository
from tbd.repositories.outbox import OutboxRepository


class JobKernel:
    """Keep state transition and safe shared-event persistence in one transaction."""

    def __init__(
        self,
        jobs: JobRepository | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self.jobs = jobs or JobRepository()
        self.outbox = outbox or OutboxRepository()

    async def enqueue(
        self,
        session: AsyncSession,
        job: AIJob,
    ) -> AIJob:
        """Persist a new Job and its durable queue hint atomically."""

        session.add(job)
        await session.flush()
        await self._emit_update(session, job, event_type="job.queued")
        return job

    async def claim_next_shared(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        lease_duration: timedelta,
        job_type: str | None = None,
    ) -> ClaimedJob | None:
        """Claim exactly one generic SHARED Job and record its safe state change."""

        run = await self.jobs.claim_next_shared(
            session,
            now=now,
            lease_duration=lease_duration,
            job_type=job_type,
        )
        if run is None:
            return None
        job = await session.get(AIJob, run.job_id)
        assert job is not None
        await self._emit_update(session, job)
        return run

    async def claim_shared_by_id(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        now: datetime,
        lease_duration: timedelta,
        job_type: str | None = None,
    ) -> ClaimedJob | None:
        """Claim a selected shared Job after its owning aggregate is locked."""

        run = await self.jobs.claim_shared_by_id(
            session,
            job_id,
            now=now,
            lease_duration=lease_duration,
            job_type=job_type,
        )
        if run is None:
            return None
        job = await session.get(AIJob, run.job_id)
        assert job is not None
        await self._emit_update(session, job)
        return run

    async def succeed(self, session: AsyncSession, run: ClaimedJob, *, now: datetime) -> bool:
        """Finish only the active fenced attempt and publish its shared projection."""

        changed = await self.jobs.succeed(session, run, now=now)
        if changed:
            job = await session.get(AIJob, run.job_id)
            assert job is not None
            await self._emit_update(session, job)
        return changed

    async def fail(
        self,
        session: AsyncSession,
        run: ClaimedJob,
        *,
        error_code: str,
        error_message: str,
        retryable: bool,
        now: datetime,
    ) -> bool:
        """Finish only the active fenced attempt with a safe public failure."""

        changed = await self.jobs.fail(
            session,
            run,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            now=now,
        )
        if changed:
            job = await session.get(AIJob, run.job_id)
            assert job is not None
            await self._emit_update(session, job)
        return changed

    async def retry_failed(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        now: datetime,
    ) -> AIJob | None:
        """Transition one retryable FAILED row to its next pending attempt."""

        job = await self.jobs.retry_failed(session, job_id, now=now)
        if job is not None:
            await self._emit_update(session, job, event_type="job.queued")
        return job

    async def cancel(self, session: AsyncSession, job_id: UUID, *, now: datetime) -> bool:
        """Record an explicit terminal cancellation when no replacement Job exists."""

        changed = await self.jobs.cancel(session, job_id, now=now)
        if changed:
            job = await session.get(AIJob, job_id)
            assert job is not None
            await self._emit_update(session, job)
        return changed

    async def supersede(self, session: AsyncSession, job_id: UUID, *, now: datetime) -> bool:
        """Record that a newer logical Job has replaced the pending or running work."""

        changed = await self.jobs.supersede(session, job_id, now=now)
        if changed:
            job = await session.get(AIJob, job_id)
            assert job is not None
            await self._emit_update(session, job)
        return changed

    async def fail_expired_shared(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        general_timeout: timedelta,
    ) -> list[UUID]:
        """Watchdog stale shared workers and record their public state changes."""

        job_ids = await self.jobs.fail_expired_shared(
            session,
            now=now,
            general_timeout=general_timeout,
        )
        for job_id in job_ids:
            job = await session.get(AIJob, job_id)
            assert job is not None
            await self._emit_update(session, job)
        return job_ids

    async def _emit_update(
        self,
        session: AsyncSession,
        job: AIJob,
        *,
        event_type: str = "job.updated",
    ) -> None:
        if job.visibility != AIJobVisibility.SHARED:
            return
        await self.outbox.enqueue(
            session,
            session_id=job.session_id,
            partition_key=f"session:{job.session_id}",
            event_type=event_type,
            resource_version=job.version,
            payload={
                "attempt": job.attempt,
                "job_id": str(job.id),
                "status": str(job.status),
                "version": job.version,
            },
        )
