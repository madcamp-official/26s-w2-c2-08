"""Irreversible account, Course, and private-object lifecycle policies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tbd.models.auth import AuthSession, RealtimeTicket
from tbd.models.consistency import IdempotencyRecord, StorageDeletionLedger
from tbd.models.courses import Course, CourseMember
from tbd.models.materials import LectureMaterial, SessionRecording
from tbd.models.questions import QuestionReaction
from tbd.models.sessions import LectureSession
from tbd.models.users import User, UserAuthIdentity, UserPasswordCredential
from tbd.storage import Storage, StorageError, StorageKey

ACTIVE_SESSION_STATES = ("READY", "LIVE", "PROCESSING")
RECORDING_RETENTION = timedelta(days=30)
DELETION_LEASE = timedelta(seconds=60)
DELETION_RETRY_BASE = timedelta(seconds=30)


class CourseDeletionBlockedError(Exception):
    """A Course with an unfinished class cannot become inaccessible."""


class AccountOwnedCourseError(Exception):
    """An account must remove every owned Course before withdrawal."""


class RecordingDeletionConflictError(Exception):
    """Only a finalized, retained Recording can be removed early."""


class LifecycleResourceNotFoundError(Exception):
    """A lifecycle target must not be exposed to an unauthorized requester."""


class LifecycleAccessDeniedError(Exception):
    """The requester is a Course member but not the immutable owner."""


async def enqueue_storage_deletion(
    session: AsyncSession,
    *,
    course_id: UUID | None,
    resource_id: UUID,
    resource_type: str,
    storage_key: str,
    byte_size: int,
    now: datetime,
) -> StorageDeletionLedger:
    """Persist one idempotent object deletion without exposing its storage key.

    A key can belong to only one final object, so the unique key also makes
    repeated Course/recording deletion requests harmless.
    """

    existing = await session.scalar(
        select(StorageDeletionLedger)
        .where(StorageDeletionLedger.storage_key == storage_key)
        .with_for_update()
    )
    if existing is not None:
        return existing
    ledger = StorageDeletionLedger(
        course_id=course_id,
        resource_id=resource_id,
        resource_type=resource_type,
        storage_key=storage_key,
        byte_size=byte_size,
        state="PENDING",
        attempt=0,
        next_attempt_at=now,
    )
    session.add(ledger)
    await session.flush()
    return ledger


class LifecycleService:
    """Make resources invisible first and leave physical object removal to a worker."""

    async def delete_course(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> None:
        course = await session.scalar(
            select(Course)
            .where(Course.id == course_id, Course.deleted_at.is_(None))
            .with_for_update()
        )
        if course is None:
            raise LifecycleResourceNotFoundError
        membership = await session.get(CourseMember, (course.id, user_id))
        if (
            membership is None
            or membership.role != "PROFESSOR"
            or course.created_by_user_id != user_id
        ):
            raise LifecycleAccessDeniedError
        active = await session.scalar(
            select(LectureSession.id)
            .where(
                LectureSession.course_id == course.id,
                LectureSession.status.in_(ACTIVE_SESSION_STATES),
            )
            .with_for_update()
        )
        if active is not None:
            raise CourseDeletionBlockedError

        materials = list(
            await session.scalars(
                select(LectureMaterial)
                .join(LectureSession, LectureSession.id == LectureMaterial.session_id)
                .where(LectureSession.course_id == course.id)
                .with_for_update()
            )
        )
        recordings = list(
            await session.scalars(
                select(SessionRecording)
                .join(LectureSession, LectureSession.id == SessionRecording.session_id)
                .where(
                    LectureSession.course_id == course.id,
                    SessionRecording.storage_key.is_not(None),
                )
                .with_for_update()
            )
        )

        course.deleted_at = now
        course.version += 1
        await session.execute(delete(CourseMember).where(CourseMember.course_id == course.id))
        for material in materials:
            await enqueue_storage_deletion(
                session,
                course_id=course.id,
                resource_id=material.id,
                resource_type="MATERIAL",
                storage_key=material.storage_key,
                byte_size=material.byte_size,
                now=now,
            )
        for recording in recordings:
            if recording.deleted_at is None:
                recording.deleted_at = now
                recording.version += 1
            if recording.byte_size is not None and recording.storage_key is not None:
                await enqueue_storage_deletion(
                    session,
                    course_id=course.id,
                    resource_id=recording.id,
                    resource_type="RECORDING",
                    storage_key=recording.storage_key,
                    byte_size=recording.byte_size,
                    now=now,
                )
        await session.flush()

    async def delete_recording(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> SessionRecording:
        lecture_session = await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )
        if lecture_session is None:
            raise LifecycleResourceNotFoundError
        course = await session.scalar(
            select(Course)
            .where(Course.id == lecture_session.course_id, Course.deleted_at.is_(None))
            .with_for_update()
        )
        if course is None:
            raise LifecycleResourceNotFoundError
        membership = await session.get(CourseMember, (course.id, user_id))
        if (
            membership is None
            or membership.role != "PROFESSOR"
            or course.created_by_user_id != user_id
        ):
            raise LifecycleAccessDeniedError
        if lecture_session.status != "COMPLETED":
            raise RecordingDeletionConflictError
        recording = await session.scalar(
            select(SessionRecording)
            .where(SessionRecording.session_id == lecture_session.id)
            .with_for_update()
        )
        if recording is None or recording.deleted_at is not None:
            raise LifecycleResourceNotFoundError
        if (
            recording.status != "UPLOADED"
            or recording.storage_key is None
            or recording.byte_size is None
        ):
            raise RecordingDeletionConflictError

        await self._make_recording_inaccessible(
            session,
            recording=recording,
            course_id=course.id,
            now=now,
        )
        return recording

    async def schedule_due_recording_deletions(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        limit: int = 100,
    ) -> int:
        """Mark expired final recordings unavailable and queue their object removal."""

        rows = list(
            await session.scalars(
                select(SessionRecording)
                .join(LectureSession, LectureSession.id == SessionRecording.session_id)
                .join(Course, Course.id == LectureSession.course_id)
                .where(
                    Course.deleted_at.is_(None),
                    SessionRecording.deleted_at.is_(None),
                    SessionRecording.status == "UPLOADED",
                    SessionRecording.storage_key.is_not(None),
                    SessionRecording.byte_size.is_not(None),
                    SessionRecording.retention_expires_at.is_not(None),
                    SessionRecording.retention_expires_at <= now,
                )
                .order_by(SessionRecording.retention_expires_at, SessionRecording.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for recording in rows:
            course_id = await session.scalar(
                select(LectureSession.course_id).where(LectureSession.id == recording.session_id)
            )
            assert course_id is not None
            await self._make_recording_inaccessible(
                session,
                recording=recording,
                course_id=course_id,
                now=now,
            )
        return len(rows)

    async def withdraw_account(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        now: datetime,
    ) -> None:
        """Remove credentials and memberships while preserving shared record references."""

        user = await session.scalar(
            select(User).where(User.id == user_id, User.deleted_at.is_(None)).with_for_update()
        )
        if user is None:
            raise LifecycleResourceNotFoundError
        owned_course = await session.scalar(
            select(Course.id)
            .where(Course.created_by_user_id == user.id, Course.deleted_at.is_(None))
            .with_for_update()
        )
        if owned_course is not None:
            raise AccountOwnedCourseError

        await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        await session.execute(delete(RealtimeTicket).where(RealtimeTicket.user_id == user.id))
        await session.execute(delete(UserAuthIdentity).where(UserAuthIdentity.user_id == user.id))
        await session.execute(
            delete(UserPasswordCredential).where(UserPasswordCredential.user_id == user.id)
        )
        await session.execute(delete(CourseMember).where(CourseMember.user_id == user.id))
        await session.execute(delete(QuestionReaction).where(QuestionReaction.user_id == user.id))
        await session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.user_id == user.id))
        user.display_name = "탈퇴한 사용자"
        user.primary_email = None
        user.avatar_url = None
        user.deleted_at = now
        await session.flush()

    async def _make_recording_inaccessible(
        self,
        session: AsyncSession,
        *,
        recording: SessionRecording,
        course_id: UUID,
        now: datetime,
    ) -> None:
        assert recording.storage_key is not None
        assert recording.byte_size is not None
        recording.deleted_at = now
        recording.version += 1
        await enqueue_storage_deletion(
            session,
            course_id=course_id,
            resource_id=recording.id,
            resource_type="RECORDING",
            storage_key=recording.storage_key,
            byte_size=recording.byte_size,
            now=now,
        )
        await session.flush()


class StorageDeletionWorker:
    """Claim and retry one private object deletion without holding DB locks during I/O."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], storage: Storage) -> None:
        self._session_factory = session_factory
        self._storage = storage

    async def run_once(self, *, now: datetime | None = None) -> bool:
        timestamp = now or datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                service = LifecycleService()
                await service.schedule_due_recording_deletions(session, now=timestamp)
                ledger = await self._claim(session, now=timestamp)
        if ledger is None:
            return False

        try:
            await self._storage.delete(StorageKey.parse(ledger.storage_key))
        except (StorageError, ValueError):
            await self._release_after_failure(ledger.id, now=timestamp)
        else:
            await self._mark_succeeded(ledger.id, now=timestamp)
        return True

    async def _claim(self, session: AsyncSession, *, now: datetime) -> StorageDeletionLedger | None:
        ledger = await session.scalar(
            select(StorageDeletionLedger)
            .where(
                or_(
                    (StorageDeletionLedger.state == "PENDING")
                    & (StorageDeletionLedger.next_attempt_at <= now),
                    (StorageDeletionLedger.state == "RUNNING")
                    & (StorageDeletionLedger.lease_expires_at <= now),
                )
            )
            .order_by(StorageDeletionLedger.next_attempt_at, StorageDeletionLedger.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if ledger is None:
            return None
        ledger.state = "RUNNING"
        ledger.attempt += 1
        ledger.lease_expires_at = now + DELETION_LEASE
        ledger.last_error_code = None
        await session.flush()
        return ledger

    async def _mark_succeeded(self, ledger_id: UUID, *, now: datetime) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                ledger = await session.scalar(
                    select(StorageDeletionLedger)
                    .where(StorageDeletionLedger.id == ledger_id)
                    .with_for_update()
                )
                if ledger is None or ledger.state != "RUNNING":
                    return
                ledger.state = "SUCCEEDED"
                ledger.lease_expires_at = None
                ledger.succeeded_at = now
                ledger.last_error_code = None

    async def _release_after_failure(self, ledger_id: UUID, *, now: datetime) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                ledger = await session.scalar(
                    select(StorageDeletionLedger)
                    .where(StorageDeletionLedger.id == ledger_id)
                    .with_for_update()
                )
                if ledger is None or ledger.state != "RUNNING":
                    return
                delay = min(
                    DELETION_RETRY_BASE * (2 ** min(ledger.attempt - 1, 8)), timedelta(hours=1)
                )
                ledger.state = "PENDING"
                ledger.lease_expires_at = None
                ledger.next_attempt_at = now + delay
                ledger.last_error_code = "STORAGE_DELETE_FAILED"
