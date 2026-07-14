"""Course-scoped lecture-session lifecycle policies."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.jobs.kernel import JobKernel
from tbd.models.enums import (
    AIJobStatus,
    AIJobType,
    AIJobVisibility,
    TranscriptSource,
    TranscriptStatus,
)
from tbd.models.materials import SessionRecording, TranscriptVersion
from tbd.models.questions import AIJob, QuestionClusteringState
from tbd.models.sessions import LectureSession
from tbd.repositories.idempotency import IdempotencyRepository
from tbd.repositories.outbox import OutboxRepository
from tbd.repositories.sessions import SessionRepository
from tbd.schemas.sessions import LectureSessionResponse
from tbd.services.courses import (
    CourseAccessDeniedError,
    CourseNotFoundError,
    CourseRoleRequiredError,
)
from tbd.services.personal_ai import PersonalAIService


class ActiveSessionExistsError(Exception):
    """A Course already has its one allowed unfinished class."""


class SessionStateConflictError(Exception):
    """The requested lifecycle action is invalid for the stored state."""


class MaterialProcessingActiveError(Exception):
    """A class cannot start while an attached PDF is still being processed."""


class InvalidSessionCursorError(Exception):
    """Cursor support is intentionally deferred until a non-empty cursor is supplied."""


@dataclass(frozen=True)
class SessionEndResult:
    """The class and blocking coordinator made durable in one transaction."""

    lecture_session: LectureSession
    coordinator: AIJob


class SessionService:
    """Apply Session lifecycle transitions inside a caller-owned transaction."""

    def __init__(
        self,
        *,
        timezone_name: str = "Asia/Seoul",
        repository: SessionRepository | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self.timezone = ZoneInfo(timezone_name)
        self.repository = repository or SessionRepository()
        self.outbox = outbox or OutboxRepository()

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        course_id: object,
        user_id: object,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> list[LectureSession]:
        if cursor is not None:
            raise InvalidSessionCursorError
        await self._require_member(session, course_id=course_id, user_id=user_id)
        return await self.repository.list_for_course(
            session, course_id=course_id, status=status, limit=limit
        )

    async def create(
        self,
        session: AsyncSession,
        *,
        course_id: object,
        user_id: object,
        title: str | None,
        lecture_date: date,
        now: datetime | None = None,
    ) -> LectureSession:
        timestamp = now or datetime.now(UTC)
        course = await self.repository.lock_course(session, course_id)
        if course is None:
            raise CourseNotFoundError
        await self._require_owner(session, course_id=course_id, user_id=user_id, course=course)
        if await self.repository.active_session_exists(session, course_id):
            raise ActiveSessionExistsError

        normalized_title = (title or "").strip()
        automatic_title = self.automatic_title(course.title, lecture_date, timestamp)
        try:
            async with session.begin_nested():
                lecture_session = await self.repository.create(
                    session,
                    course_id=course_id,
                    user_id=user_id,
                    title=normalized_title or automatic_title,
                    lecture_date=lecture_date,
                    now=timestamp,
                )
                session.add(QuestionClusteringState(session_id=lecture_session.id))
                await session.flush()
        except IntegrityError as exc:
            if self._is_active_session_constraint(exc):
                raise ActiveSessionExistsError from exc
            raise
        await self._emit_session_updated(session, lecture_session)
        return lecture_session

    async def get_for_member(
        self,
        session: AsyncSession,
        *,
        session_id: object,
        user_id: object,
    ) -> LectureSession:
        lecture_session = await self._get_existing(session, session_id)
        await self._require_member(session, course_id=lecture_session.course_id, user_id=user_id)
        return lecture_session

    async def update_title(
        self,
        session: AsyncSession,
        *,
        session_id: object,
        user_id: object,
        title: str,
    ) -> LectureSession:
        lecture_session = await self._lock_existing(session, session_id)
        course = await self.repository.lock_course(session, lecture_session.course_id)
        assert course is not None
        await self._require_owner(session, course_id=course.id, user_id=user_id, course=course)
        lecture_session.title = title.strip() or self.automatic_title(
            course.title, lecture_session.lecture_date, lecture_session.created_at
        )
        lecture_session.version += 1
        await session.flush()
        await self._emit_session_updated(session, lecture_session)
        return lecture_session

    async def delete(
        self,
        session: AsyncSession,
        *,
        session_id: object,
        user_id: object,
    ) -> None:
        lecture_session = await self._lock_existing(session, session_id)
        course = await self.repository.lock_course(session, lecture_session.course_id)
        assert course is not None
        await self._require_owner(session, course_id=course.id, user_id=user_id, course=course)
        if lecture_session.status not in {"READY", "COMPLETED"}:
            raise SessionStateConflictError
        await session.delete(lecture_session)
        await session.flush()

    async def start(
        self,
        session: AsyncSession,
        *,
        session_id: object,
        user_id: object,
        now: datetime | None = None,
    ) -> LectureSession:
        lecture_session = await self._lock_existing(session, session_id)
        course = await self.repository.lock_course(session, lecture_session.course_id)
        assert course is not None
        await self._require_owner(session, course_id=course.id, user_id=user_id, course=course)
        if lecture_session.status != "READY":
            raise SessionStateConflictError
        if await self.repository.processing_material_count(session, lecture_session.id):
            raise MaterialProcessingActiveError

        timestamp = now or datetime.now(UTC)
        live_version = TranscriptVersion(
            session_id=lecture_session.id,
            version=1,
            source=TranscriptSource.LIVE,
            status=TranscriptStatus.FINALIZING,
            last_sequence=0,
        )
        session.add(live_version)
        await session.flush()
        lecture_session.status = "LIVE"
        lecture_session.started_at = timestamp
        lecture_session.canonical_transcript_version_id = live_version.id
        lecture_session.version += 1
        await session.flush()
        await self._emit_session_updated(session, lecture_session)
        return lecture_session

    async def end(
        self,
        session: AsyncSession,
        *,
        session_id: object,
        user_id: object,
        idempotency: IdempotencyRepository | None = None,
        now: datetime | None = None,
    ) -> SessionEndResult:
        timestamp = now or datetime.now(UTC)
        personal_ai = PersonalAIService()
        purge_records = await personal_ai.lock_purge_records(session, session_id=session_id)
        lecture_session = await self._lock_existing(session, session_id)
        course = await self.repository.lock_course(session, lecture_session.course_id)
        assert course is not None
        await self._require_owner(session, course_id=course.id, user_id=user_id, course=course)
        if lecture_session.status != "LIVE":
            raise SessionStateConflictError

        await personal_ai.purge_live(
            session,
            lecture_session=lecture_session,
            records=purge_records,
            idempotency=idempotency,
            now=timestamp,
        )
        lecture_session.status = "PROCESSING"
        lecture_session.ended_at = timestamp
        lecture_session.version += 1
        recording = await session.scalar(
            select(SessionRecording)
            .where(SessionRecording.session_id == lecture_session.id)
            .with_for_update()
        )
        if recording is not None and recording.status == "CAPTURING":
            # The PCM socket is not the durable recording object. Preserve the
            # same logical aggregate for PR-21's resumable browser upload while
            # immediately fencing further live PCM through Session PROCESSING.
            recording.status = "UPLOAD_PENDING"
            recording.capture_ended_at = timestamp
            recording.live_audio_lease_expires_at = None
            recording.version += 1
        coordinator = AIJob(
            session_id=lecture_session.id,
            job_type=AIJobType.SESSION_POSTPROCESSING,
            visibility=AIJobVisibility.SHARED,
            status=AIJobStatus.PENDING,
            attempt=1,
            version=1,
            blocks_session_completion=True,
            retryable=True,
        )
        await JobKernel(outbox=self.outbox).enqueue(session, coordinator)
        await self._emit_session_updated(session, lecture_session)
        return SessionEndResult(lecture_session=lecture_session, coordinator=coordinator)

    async def mark_completed(
        self,
        session: AsyncSession,
        *,
        session_id: object,
        now: datetime | None = None,
    ) -> LectureSession:
        """Internal worker hook; browser clients must use the stored status, never Job counts."""

        lecture_session = await self._lock_existing(session, session_id)
        if lecture_session.status != "PROCESSING":
            raise SessionStateConflictError
        lecture_session.status = "COMPLETED"
        lecture_session.completed_at = now or datetime.now(UTC)
        lecture_session.version += 1
        await session.flush()
        await self._emit_session_updated(session, lecture_session)
        return lecture_session

    async def _emit_session_updated(
        self, session: AsyncSession, lecture_session: LectureSession
    ) -> None:
        """Persist the safe member-visible projection with the lifecycle transaction."""

        await self.outbox.enqueue(
            session,
            session_id=lecture_session.id,
            partition_key=f"session:{lecture_session.id}",
            event_type="session.updated",
            resource_version=lecture_session.version,
            payload=LectureSessionResponse.model_validate(lecture_session).model_dump(mode="json"),
        )

    def automatic_title(self, course_title: str, lecture_date: date, created_at: datetime) -> str:
        """Return the persisted title contract using the immutable creation instant."""

        return (
            f"{course_title} · {lecture_date:%Y.%m.%d} {created_at.astimezone(self.timezone):%H:%M}"
        )

    async def _get_existing(self, session: AsyncSession, session_id: object) -> LectureSession:
        lecture_session = await self.repository.get_session(session, session_id)
        if lecture_session is None:
            raise CourseNotFoundError
        return lecture_session

    async def _lock_existing(self, session: AsyncSession, session_id: object) -> LectureSession:
        lecture_session = await self.repository.lock_session(session, session_id)
        if lecture_session is None:
            raise CourseNotFoundError
        return lecture_session

    async def _require_member(
        self, session: AsyncSession, *, course_id: object, user_id: object
    ) -> None:
        if (
            await self.repository.member_role(session, course_id=course_id, user_id=user_id)
            is not None
        ):
            return
        if await self.repository.lock_course(session, course_id) is not None:
            raise CourseAccessDeniedError
        raise CourseNotFoundError

    async def _require_owner(
        self,
        session: AsyncSession,
        *,
        course_id: object,
        user_id: object,
        course: object,
    ) -> None:
        role = await self.repository.member_role(session, course_id=course_id, user_id=user_id)
        if role != "PROFESSOR" or course.created_by_user_id != user_id:
            raise CourseRoleRequiredError

    @staticmethod
    def _is_active_session_constraint(error: IntegrityError) -> bool:
        diagnostic = getattr(getattr(error, "orig", None), "diag", None)
        return (
            getattr(diagnostic, "constraint_name", None)
            == "lecture_sessions_one_active_per_course_uq"
        )
