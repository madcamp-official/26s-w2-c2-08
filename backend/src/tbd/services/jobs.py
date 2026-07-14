"""Authorization-aware AIJob lookup, listing, and retry policy."""

import base64
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.jobs.kernel import JobKernel
from tbd.models.courses import CourseMember
from tbd.models.enums import AIJobStatus, AIJobType, AIJobVisibility, LectureSessionStatus
from tbd.models.materials import SessionRecording, TranscriptVersion
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession
from tbd.repositories.recordings import RecordingRepository


class JobNotFoundError(Exception):
    """Raised when the caller must not learn whether a Job exists."""


class JobAccessDeniedError(Exception):
    """Raised when a visible shared Job needs a professor-only control."""


class SessionJobNotFoundError(Exception):
    """The Session whose shared jobs are requested does not exist."""


class SessionJobAccessDeniedError(Exception):
    """The current user is not a member of the Session's Course."""


class InvalidSharedJobCursorError(Exception):
    """The supplied cursor was tampered with or belongs to another filter scope."""


@dataclass(frozen=True)
class JobRetryConflictError(Exception):
    """A stable retry conflict that the HTTP router can render safely."""

    code: str
    message: str
    details: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class _SharedJobCursor:
    created_at: datetime
    job_id: UUID


class _SharedJobCursorCodec:
    """Sign a cursor that cannot switch Session or filter scopes."""

    _PREFIX = b"goal/shared-jobs/cursor/v1\x00"

    def __init__(self, secret: str) -> None:
        self._key = hmac.digest(secret.encode("utf-8"), self._PREFIX, "sha256")

    def encode(
        self,
        *,
        session_id: UUID,
        job_type: str | None,
        status: str | None,
        position: _SharedJobCursor,
    ) -> str:
        raw = json.dumps(
            {
                "created_at": position.created_at.isoformat(),
                "id": str(position.job_id),
                "job_type": job_type,
                "session_id": str(session_id),
                "status": status,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.digest(self._key, raw, "sha256")[:16]
        return base64.urlsafe_b64encode(raw + signature).decode("ascii").rstrip("=")

    def decode(
        self,
        *,
        cursor: str,
        session_id: UUID,
        job_type: str | None,
        status: str | None,
    ) -> _SharedJobCursor:
        try:
            payload_bytes = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            raw, signature = payload_bytes[:-16], payload_bytes[-16:]
            if not hmac.compare_digest(hmac.digest(self._key, raw, "sha256")[:16], signature):
                raise ValueError
            payload = json.loads(raw)
            if (
                payload["session_id"] != str(session_id)
                or payload["job_type"] != job_type
                or payload["status"] != status
            ):
                raise ValueError
            return _SharedJobCursor(
                created_at=datetime.fromisoformat(payload["created_at"]),
                job_id=UUID(payload["id"]),
            )
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise InvalidSharedJobCursorError from exc


class JobService:
    """Apply Course membership and Job lifecycle rules around the shared kernel."""

    def __init__(self, kernel: JobKernel | None = None, *, auth_secret: str = "") -> None:
        self._kernel = kernel or JobKernel()
        self._shared_job_cursors = _SharedJobCursorCodec(auth_secret)

    async def list_shared_for_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        job_type: str | None,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[AIJob], str | None]:
        """List only Course-visible SHARED work with a filter-bound keyset cursor."""

        lecture_session = await session.get(LectureSession, session_id)
        if lecture_session is None:
            raise SessionJobNotFoundError
        role = await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == lecture_session.course_id,
                CourseMember.user_id == user_id,
            )
        )
        if role is None:
            raise SessionJobAccessDeniedError
        after = (
            self._shared_job_cursors.decode(
                cursor=cursor,
                session_id=session_id,
                job_type=job_type,
                status=status,
            )
            if cursor is not None
            else None
        )
        statement = select(AIJob).where(
            AIJob.session_id == session_id,
            AIJob.visibility == AIJobVisibility.SHARED,
        )
        if job_type is not None:
            statement = statement.where(AIJob.job_type == job_type)
        if status is not None:
            statement = statement.where(AIJob.status == status)
        if after is not None:
            statement = statement.where(
                or_(
                    AIJob.created_at < after.created_at,
                    and_(AIJob.created_at == after.created_at, AIJob.id < after.job_id),
                )
            )
        rows = list(
            await session.scalars(
                statement.order_by(AIJob.created_at.desc(), AIJob.id.desc()).limit(limit + 1)
            )
        )
        page, extra = rows[:limit], rows[limit:]
        next_cursor = None
        if extra and page:
            last = page[-1]
            next_cursor = self._shared_job_cursors.encode(
                session_id=session_id,
                job_type=job_type,
                status=status,
                position=_SharedJobCursor(created_at=last.created_at, job_id=last.id),
            )
        return page, next_cursor

    async def get_visible(
        self,
        session: AsyncSession,
        *,
        job_id: UUID,
        user_id: UUID,
    ) -> AIJob:
        """Return a Job only to a current member in its declared visibility scope."""

        job = await session.scalar(
            select(AIJob)
            .join(LectureSession, LectureSession.id == AIJob.session_id)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(
                AIJob.id == job_id,
                CourseMember.user_id == user_id,
                (AIJob.visibility == AIJobVisibility.SHARED) | (AIJob.requester_user_id == user_id),
            )
        )
        if job is None:
            raise JobNotFoundError
        return job

    async def retry(
        self,
        session: AsyncSession,
        *,
        job_id: UUID,
        user_id: UUID,
        now: datetime | None = None,
    ) -> AIJob:
        """Requeue exactly one allowed FAILED row with its incremented attempt."""

        row = (
            await session.execute(
                select(AIJob, CourseMember.role, LectureSession.status)
                .join(LectureSession, LectureSession.id == AIJob.session_id)
                .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
                .where(AIJob.id == job_id, CourseMember.user_id == user_id)
                .with_for_update(of=AIJob)
            )
        ).one_or_none()
        if row is None:
            raise JobNotFoundError

        job, course_role, session_status = row
        if job.visibility == AIJobVisibility.REQUESTER_ONLY and job.requester_user_id != user_id:
            raise JobNotFoundError
        if job.visibility == AIJobVisibility.SHARED and course_role != "PROFESSOR":
            raise JobAccessDeniedError
        if job.status != AIJobStatus.FAILED:
            raise JobRetryConflictError(
                code="AI_JOB_STATE_CONFLICT",
                message="FAILED 상태의 작업만 재시도할 수 있습니다.",
                details={"current_status": str(job.status), "required_status": "FAILED"},
            )
        if (
            job.job_type == AIJobType.QUESTION_CLUSTERING
            and job.clustering_mode == "LIVE_INCREMENTAL"
        ):
            raise JobRetryConflictError(
                code="AI_JOB_RETRY_SYSTEM_MANAGED",
                message="이 작업의 재시도는 시스템이 자동으로 관리합니다.",
            )
        if (
            job.job_type == AIJobType.QUESTION_CLUSTERING
            and job.clustering_mode == "FINAL"
            and session_status != LectureSessionStatus.COMPLETED
        ):
            raise JobRetryConflictError(
                code="AI_JOB_STATE_CONFLICT",
                message="최종 클러스터링은 수업 정리가 완료된 뒤에만 재시도할 수 있습니다.",
                details={"current_session_status": str(session_status)},
            )
        if not job.retryable:
            raise JobRetryConflictError(
                code="AI_JOB_NOT_RETRYABLE",
                message="이 작업은 재시도할 수 없습니다.",
            )

        timestamp = now or datetime.now(UTC)
        recording: SessionRecording | None = None
        repository = RecordingRepository()
        if job.job_type == AIJobType.RECORDING_TRANSCRIPTION:
            lecture_session = await repository.lock_session(session, job.session_id)
            recording = await repository.lock_recording_for_session(
                session, session_id=job.session_id
            )
            if (
                lecture_session is None
                or recording is None
                or recording.id != job.target_recording_id
                or recording.status != "UPLOADED"
            ):
                raise JobRetryConflictError(
                    code="AI_JOB_STATE_CONFLICT",
                    message="재시도할 수 있는 녹음 원본을 찾을 수 없습니다.",
                )

        retried = await self._kernel.retry_failed(
            session,
            job.id,
            now=timestamp,
        )
        if retried is None:
            raise JobRetryConflictError(
                code="AI_JOB_STATE_CONFLICT",
                message="작업 상태가 변경되어 재시도할 수 없습니다.",
            )
        if recording is not None:
            session.add(
                TranscriptVersion(
                    session_id=retried.session_id,
                    version=await repository.next_transcript_version(
                        session, session_id=retried.session_id
                    ),
                    source="RECORDING",
                    status="FINALIZING",
                    recording_id=recording.id,
                    created_by_job_id=retried.id,
                    created_by_job_attempt=retried.attempt,
                    last_sequence=0,
                )
            )
            await session.flush()
        return retried
