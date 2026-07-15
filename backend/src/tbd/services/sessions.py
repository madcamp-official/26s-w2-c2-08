"""Course-scoped lecture-session lifecycle policies."""

import base64
import binascii
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.jobs.kernel import JobKernel
from tbd.models.clustering import Answer
from tbd.models.enums import (
    AIJobStatus,
    AIJobType,
    AIJobVisibility,
    TranscriptSource,
    TranscriptStatus,
)
from tbd.models.materials import SessionRecording, TranscriptVersion
from tbd.models.questions import AIJob, Question, QuestionClusteringState
from tbd.models.sessions import LectureSession
from tbd.repositories.idempotency import IdempotencyRepository
from tbd.repositories.outbox import OutboxRepository
from tbd.repositories.sessions import SessionCursorPosition, SessionRepository
from tbd.schemas.sessions import LectureSessionResponse
from tbd.services.courses import (
    CourseAccessDeniedError,
    CourseNotFoundError,
    CourseRoleRequiredError,
)
from tbd.services.lifecycle import RECORDING_RETENTION
from tbd.services.personal_ai import PersonalAIService
from tbd.services.questions import QuestionService


class ActiveSessionExistsError(Exception):
    """A Course already has its one allowed unfinished class."""


class SessionStateConflictError(Exception):
    """The requested lifecycle action is invalid for the stored state."""


class MaterialProcessingActiveError(Exception):
    """A class cannot start while an attached PDF is still being processed."""


class InvalidSessionCursorError(Exception):
    """A cursor was tampered with or reused outside its Course list scope."""


@dataclass(frozen=True)
class SessionListResult:
    """A bounded Course Session page and its next opaque position."""

    items: list[LectureSession]
    next_cursor: str | None


class SessionCursorCodec:
    """Sign one Course Session keyset position and its immutable filters."""

    _PREFIX = b"goal/course-sessions/cursor/v1\x00"
    _RESOURCE = "course_sessions"
    _SIGNATURE_BYTES = 16

    def __init__(self, secret: str) -> None:
        self._key = hmac.digest(secret.encode("utf-8"), self._PREFIX, "sha256")

    def encode(
        self,
        *,
        course_id: UUID,
        status: str | None,
        position: SessionCursorPosition,
    ) -> str:
        raw = json.dumps(
            {
                "course_id": str(course_id),
                "id": str(position.session_id),
                "resource": self._RESOURCE,
                "started_at": (
                    position.started_at.isoformat() if position.started_at is not None else None
                ),
                "status": status,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.digest(self._key, raw, "sha256")[: self._SIGNATURE_BYTES]
        return base64.urlsafe_b64encode(raw + signature).decode("ascii").rstrip("=")

    def decode(
        self,
        *,
        cursor: str,
        course_id: UUID,
        status: str | None,
    ) -> SessionCursorPosition:
        try:
            encoded = base64.b64decode(
                cursor + "=" * (-len(cursor) % 4),
                altchars=b"-_",
                validate=True,
            )
            canonical = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
            if not hmac.compare_digest(canonical, cursor):
                raise ValueError
            if len(encoded) <= self._SIGNATURE_BYTES:
                raise ValueError
            raw = encoded[: -self._SIGNATURE_BYTES]
            signature = encoded[-self._SIGNATURE_BYTES :]
            expected = hmac.digest(self._key, raw, "sha256")[: self._SIGNATURE_BYTES]
            if not hmac.compare_digest(expected, signature):
                raise ValueError
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError
            if set(payload) != {"course_id", "id", "resource", "started_at", "status"}:
                raise ValueError
            if (
                payload["resource"] != self._RESOURCE
                or payload["course_id"] != str(course_id)
                or payload["status"] != status
            ):
                raise ValueError
            started_at_value = payload["started_at"]
            if started_at_value is None:
                started_at = None
            elif isinstance(started_at_value, str):
                started_at = datetime.fromisoformat(started_at_value)
                if started_at.tzinfo is None or started_at.utcoffset() is None:
                    raise ValueError
            else:
                raise ValueError
            return SessionCursorPosition(
                started_at=started_at,
                session_id=UUID(payload["id"]),
            )
        except (
            binascii.Error,
            KeyError,
            TypeError,
            ValueError,
            UnicodeError,
        ) as exc:
            raise InvalidSessionCursorError from exc


@dataclass(frozen=True)
class SessionEndResult:
    """The class and blocking coordinator made durable in one transaction."""

    lecture_session: LectureSession
    coordinator: AIJob
    final_clustering: AIJob | None = None


class SessionService:
    """Apply Session lifecycle transitions inside a caller-owned transaction."""

    def __init__(
        self,
        *,
        timezone_name: str = "Asia/Seoul",
        auth_secret: str | None = None,
        repository: SessionRepository | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self.timezone = ZoneInfo(timezone_name)
        self.repository = repository or SessionRepository()
        self.outbox = outbox or OutboxRepository()
        self.cursors = SessionCursorCodec(auth_secret) if auth_secret is not None else None

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> SessionListResult:
        await self._require_member(session, course_id=course_id, user_id=user_id)
        if self.cursors is None:
            raise RuntimeError("Session cursor signing requires auth_secret")
        after = (
            self.cursors.decode(cursor=cursor, course_id=course_id, status=status)
            if cursor is not None
            else None
        )
        rows = await self.repository.list_for_course(
            session,
            course_id=course_id,
            status=status,
            after=after,
            limit=limit + 1,
        )
        page, extra = rows[:limit], rows[limit:]
        next_cursor = None
        if extra and page:
            last = page[-1]
            next_cursor = self.cursors.encode(
                course_id=course_id,
                status=status,
                position=SessionCursorPosition(
                    started_at=last.started_at,
                    session_id=last.id,
                ),
            )
        return SessionListResult(items=page, next_cursor=next_cursor)

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
        live_version = await session.scalar(
            select(TranscriptVersion)
            .where(
                TranscriptVersion.session_id == lecture_session.id,
                TranscriptVersion.source == TranscriptSource.LIVE,
            )
            .order_by(TranscriptVersion.version.desc())
            .with_for_update()
        )
        if live_version is not None and live_version.status == TranscriptStatus.FINALIZING:
            live_version.status = (
                TranscriptStatus.FINALIZED
                if live_version.last_sequence > 0
                else TranscriptStatus.EMPTY
            )
            live_version.finalized_at = timestamp
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
        kernel = JobKernel(outbox=self.outbox)
        await kernel.enqueue(session, coordinator)
        final_clustering = await self._schedule_final_clustering(
            session,
            lecture_session=lecture_session,
            ended_at=timestamp,
            kernel=kernel,
        )
        await self._emit_session_updated(session, lecture_session)
        return SessionEndResult(
            lecture_session=lecture_session,
            coordinator=coordinator,
            final_clustering=final_clustering,
        )

    async def _schedule_final_clustering(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        ended_at: datetime,
        kernel: JobKernel,
    ) -> AIJob | None:
        """Freeze eligible Question inputs as a blocking FINAL clustering Job.

        A final run is deliberately created while ending the class, rather than
        by the later coordinator.  It therefore cannot accidentally absorb
        Question or Answer writes that race the ``LIVE → PROCESSING`` fence.
        """

        state = await session.scalar(
            select(QuestionClusteringState)
            .where(QuestionClusteringState.session_id == lecture_session.id)
            .with_for_update()
        )
        if state is None:
            return None

        live_jobs = list(
            await session.scalars(
                select(AIJob)
                .where(
                    AIJob.session_id == lecture_session.id,
                    AIJob.job_type == AIJobType.QUESTION_CLUSTERING,
                    AIJob.clustering_mode == "LIVE_INCREMENTAL",
                    AIJob.status.in_((AIJobStatus.PENDING, AIJobStatus.RUNNING)),
                )
                .with_for_update()
            )
        )
        for job in live_jobs:
            await kernel.supersede(session, job.id, now=ended_at)
        if state.retry_job_id is not None:
            await kernel.supersede(session, state.retry_job_id, now=ended_at)
            state.retry_job_id = None

        question_count = await session.scalar(
            select(func.count(Question.id)).where(
                Question.session_id == lecture_session.id,
                Question.clustering_sequence <= state.requested_sequence,
            )
        )
        representative_answer_count = await session.scalar(
            select(func.count(Answer.id)).where(
                Answer.session_id == lecture_session.id,
                Answer.status == "COMPLETED",
                Answer.target_representative_question_id.is_not(None),
                Answer.completed_at <= ended_at,
            )
        )
        if int(question_count or 0) + int(representative_answer_count or 0) == 0:
            return None

        final_job = AIJob(
            session_id=lecture_session.id,
            job_type=AIJobType.QUESTION_CLUSTERING,
            visibility=AIJobVisibility.SHARED,
            status=AIJobStatus.PENDING,
            attempt=1,
            version=1,
            clustering_mode="FINAL",
            input_through_sequence=state.requested_sequence,
            base_revision=state.current_revision,
            final_answered_through_at=ended_at,
            blocks_session_completion=True,
            retryable=True,
        )
        await kernel.enqueue(session, final_job)
        state.last_job_id = final_job.id
        state.last_job_attempt = final_job.attempt
        state.last_job_status = str(AIJobStatus.PENDING)
        await self.outbox.enqueue(
            session,
            session_id=lecture_session.id,
            partition_key=f"session:{lecture_session.id}",
            event_type="clustering.updated",
            resource_version=max(1, state.requested_sequence),
            payload=QuestionService.project_clustering_state(state, active=final_job).model_dump(
                mode="json"
            ),
        )
        return final_job

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
        recording = await session.scalar(
            select(SessionRecording)
            .where(SessionRecording.session_id == lecture_session.id)
            .with_for_update()
        )
        if (
            recording is not None
            and recording.status == "UPLOADED"
            and recording.deleted_at is None
            and recording.retention_expires_at is None
        ):
            recording.retention_expires_at = lecture_session.completed_at + RECORDING_RETENTION
            recording.version += 1
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
