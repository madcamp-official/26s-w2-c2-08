"""Professor Answer capture, completion, and completed-record text policies."""

from __future__ import annotations

import base64
import hmac
import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.clustering import AIRepresentativeQuestion, Answer, AnswerOrganization
from tbd.models.courses import CourseMember
from tbd.models.enums import AIJobStatus, AIJobType, LectureSessionStatus
from tbd.models.materials import TranscriptSegment
from tbd.models.questions import AIJob, Question
from tbd.models.sessions import LectureSession
from tbd.repositories.answers import AnswerCursorPosition, AnswerRepository
from tbd.repositories.outbox import OutboxRepository
from tbd.schemas.answers import (
    AnswerCompleteRequest,
    AnswerCreateRequest,
    AnswerListResponse,
    AnswerOrganizationResponse,
    AnswerOrganizationStateResponse,
    AnswerResponse,
    AnswerTarget,
    AnswerTextUpdateRequest,
    AnswerTranscriptMappingResponse,
    RepresentativeQuestionAnswerTarget,
    StudentQuestionAnswerTarget,
)

MAX_ANSWER_TEXT_LENGTH = 2000


class AnswerNotFoundError(Exception):
    """The Answer or target is not visible in its asserted Course scope."""


class AnswerAccessDeniedError(Exception):
    """The caller is not a member of the Answer's Course."""


class AnswerRoleRequiredError(Exception):
    """Only the immutable Course professor may write Answers."""


class AnswerSessionStateError(Exception):
    """The requested Answer transition is unavailable in this Session state."""


class AnswerTargetStateError(Exception):
    """The selected target cannot create another Answer in its present state."""


class AnswerCaptureActiveError(Exception):
    """One LIVE Session already has an active voice capture."""


class AnswerAlreadyExistsError(Exception):
    """A target has its one non-cancelled Answer."""


class AnswerTranscriptNotReadyError(Exception):
    """No final Segment exists after the capture start watermark."""


class AnswerTranscriptRangeError(Exception):
    """The requested range is not a valid portion of the captured live version."""


class InvalidAnswerCursorError(Exception):
    """An Answer list cursor is malformed or belongs to another Session."""


@dataclass
class AnswerTextValidationError(Exception):
    reason: str
    actual_length: int


@dataclass
class AnswerVersionConflictError(Exception):
    current_version: int
    current_text_content: str | None


@dataclass(frozen=True)
class _AnswerProjectionContext:
    lecture_session: LectureSession
    segments: dict[UUID, TranscriptSegment]
    organizations: dict[UUID, AnswerOrganization]
    organization_jobs: dict[UUID, AIJob]


class AnswerCursorCodec:
    """Sign a stable ascending Answer keyset position for one Session."""

    _PREFIX = b"goal/answers/cursor/v1\x00"

    def __init__(self, secret: str) -> None:
        self._key = hmac.digest(secret.encode("utf-8"), self._PREFIX, "sha256")

    def encode(self, *, session_id: UUID, position: AnswerCursorPosition) -> str:
        raw = json.dumps(
            {
                "id": str(position.answer_id),
                "session_id": str(session_id),
                "started_at": position.started_at.isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.digest(self._key, raw, "sha256")[:16]
        return base64.urlsafe_b64encode(raw + signature).decode("ascii").rstrip("=")

    def decode(self, *, cursor: str, session_id: UUID) -> AnswerCursorPosition:
        try:
            raw_and_signature = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            raw, signature = raw_and_signature[:-16], raw_and_signature[-16:]
            if not hmac.compare_digest(hmac.digest(self._key, raw, "sha256")[:16], signature):
                raise ValueError
            payload = json.loads(raw)
            if payload["session_id"] != str(session_id):
                raise ValueError
            return AnswerCursorPosition(
                started_at=datetime.fromisoformat(payload["started_at"]),
                answer_id=UUID(payload["id"]),
            )
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise InvalidAnswerCursorError from exc


class AnswerService:
    """Own short database transactions; Answer organization remains a later worker concern."""

    def __init__(
        self,
        *,
        auth_secret: str,
        repository: AnswerRepository | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self.repository = repository or AnswerRepository()
        self.outbox = outbox or OutboxRepository()
        self.cursors = AnswerCursorCodec(auth_secret)

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> AnswerListResponse:
        lecture_session = await self._require_member(
            session, session_id=session_id, user_id=user_id
        )
        after = (
            self.cursors.decode(cursor=cursor, session_id=lecture_session.id)
            if cursor is not None
            else None
        )
        answers = await self.repository.list_answers(
            session,
            session_id=lecture_session.id,
            after=after,
            limit=limit + 1,
        )
        page, extra = answers[:limit], answers[limit:]
        next_cursor = None
        if extra and page:
            last = page[-1]
            next_cursor = self.cursors.encode(
                session_id=lecture_session.id,
                position=AnswerCursorPosition(started_at=last.started_at, answer_id=last.id),
            )
        context = await self._projection_context(
            session, lecture_session=lecture_session, answers=page
        )
        return AnswerListResponse(
            items=[await self.project(session, answer, context=context) for answer in page],
            next_cursor=next_cursor,
        )

    async def get_for_member(
        self, session: AsyncSession, *, answer_id: UUID, user_id: UUID
    ) -> AnswerResponse:
        answer = await session.get(Answer, answer_id)
        if answer is None:
            raise AnswerNotFoundError
        await self._require_member(session, session_id=answer.session_id, user_id=user_id)
        return await self.project(session, answer)

    async def create(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        payload: AnswerCreateRequest,
        now: datetime | None = None,
    ) -> AnswerResponse:
        timestamp = now or datetime.now(UTC)
        lecture_session = await self._require_professor(
            session, session_id=session_id, user_id=user_id
        )
        if payload.answer_type == "VOICE":
            if lecture_session.status != "LIVE":
                raise AnswerSessionStateError
            if await self.repository.capturing_answer(session, lecture_session.id) is not None:
                raise AnswerCaptureActiveError
            target, target_kind = await self._lock_target(
                session, session_id=lecture_session.id, target=payload.target
            )
            self._require_open_target(target)
            if await self._existing_target_answer(session, target, target_kind) is not None:
                raise AnswerAlreadyExistsError
            live_version = await self.repository.live_version(session, lecture_session.id)
            if live_version is None:
                raise AnswerTranscriptNotReadyError
            answer = Answer(
                session_id=lecture_session.id,
                professor_user_id=user_id,
                target_question_id=target.id if target_kind == "STUDENT_QUESTION" else None,
                target_representative_question_id=(
                    target.id if target_kind == "AI_REPRESENTATIVE_QUESTION" else None
                ),
                target_text_snapshot=self._target_text(target),
                status="CAPTURING",
                source_transcript_version_id=live_version.id,
                capture_started_after_sequence=await self.repository.last_sequence(
                    session, live_version.id
                ),
                version=1,
                started_at=timestamp,
            )
            target.status = "SELECTED"
            target.version += 1
        else:
            if lecture_session.status != "COMPLETED":
                raise AnswerSessionStateError
            if not isinstance(payload.target, StudentQuestionAnswerTarget):
                raise AnswerTargetStateError
            target, target_kind = await self._lock_target(
                session, session_id=lecture_session.id, target=payload.target
            )
            assert target_kind == "STUDENT_QUESTION"
            self._require_open_target(target)
            if await self._existing_target_answer(session, target, target_kind) is not None:
                raise AnswerAlreadyExistsError
            answer = Answer(
                session_id=lecture_session.id,
                professor_user_id=user_id,
                target_question_id=target.id,
                target_text_snapshot=self._target_text(target),
                status="COMPLETED",
                text_content=self.normalize_text(payload.text_content or ""),
                version=1,
                started_at=timestamp,
                completed_at=timestamp,
            )
            target.status = "ANSWERED"
            target.version += 1
        session.add(answer)
        await session.flush()
        result = await self.project(session, answer)
        await self._emit_updated(session, result)
        return result

    async def complete(
        self,
        session: AsyncSession,
        *,
        answer_id: UUID,
        user_id: UUID,
        payload: AnswerCompleteRequest | None,
        now: datetime | None = None,
    ) -> AnswerResponse:
        answer = await self.repository.lock_answer(session, answer_id)
        if answer is None:
            raise AnswerNotFoundError
        lecture_session = await self._require_professor(
            session, session_id=answer.session_id, user_id=user_id
        )
        if answer.status == "COMPLETED":
            return await self.project(session, answer)
        if lecture_session.status != "LIVE" or answer.source_transcript_version_id is None:
            raise AnswerSessionStateError
        if payload is None:
            start, end = await self.repository.first_last_after(
                session,
                transcript_version_id=answer.source_transcript_version_id,
                sequence=answer.capture_started_after_sequence or 0,
            )
        else:
            if payload.transcript_version_id != answer.source_transcript_version_id:
                raise AnswerTranscriptRangeError
            if payload.start_sequence > payload.end_sequence or (
                payload.start_sequence <= (answer.capture_started_after_sequence or 0)
            ):
                raise AnswerTranscriptRangeError
            start = await self.repository.segment_by_sequence(
                session,
                transcript_version_id=payload.transcript_version_id,
                sequence=payload.start_sequence,
            )
            end = await self.repository.segment_by_sequence(
                session,
                transcript_version_id=payload.transcript_version_id,
                sequence=payload.end_sequence,
            )
        if start is None or end is None:
            raise AnswerTranscriptNotReadyError
        answer.start_segment_id = start.id
        answer.end_segment_id = end.id
        answer.status = "COMPLETED"
        completed_at = now or datetime.now(UTC)
        if completed_at < answer.started_at:
            completed_at = answer.started_at
        answer.completed_at = completed_at
        answer.version += 1
        target, _ = await self._lock_answer_target(session, answer)
        target.status = "ANSWERED"
        target.version += 1
        await session.flush()
        result = await self.project(session, answer)
        await self._emit_updated(session, result)
        return result

    async def cancel(self, session: AsyncSession, *, answer_id: UUID, user_id: UUID) -> None:
        answer = await self.repository.lock_answer(session, answer_id)
        if answer is None:
            raise AnswerNotFoundError
        lecture_session = await self._require_professor(
            session, session_id=answer.session_id, user_id=user_id
        )
        if lecture_session.status != "LIVE" or answer.status != "CAPTURING":
            raise AnswerSessionStateError
        target, target_kind = await self._lock_answer_target(session, answer)
        target.status = "OPEN"
        target.version += 1
        await session.delete(answer)
        await session.flush()
        await self.outbox.enqueue(
            session,
            session_id=lecture_session.id,
            partition_key=f"session:{lecture_session.id}",
            event_type="answer.deleted",
            resource_version=None,
            payload={
                "answer_id": str(answer_id),
                "target_type": target_kind,
                "target_id": str(target.id),
            },
        )

    async def update_text(
        self,
        session: AsyncSession,
        *,
        answer_id: UUID,
        user_id: UUID,
        payload: AnswerTextUpdateRequest,
    ) -> AnswerResponse:
        answer = await self.repository.lock_answer(session, answer_id)
        if answer is None:
            raise AnswerNotFoundError
        lecture_session = await self._require_professor(
            session, session_id=answer.session_id, user_id=user_id
        )
        if lecture_session.status != "COMPLETED" or answer.status != "COMPLETED":
            raise AnswerSessionStateError
        target, target_kind = await self._lock_answer_target(session, answer)
        if target_kind == "AI_REPRESENTATIVE_QUESTION" and target.lifecycle_status != "PRESERVED":
            raise AnswerTargetStateError
        if answer.version != payload.expected_version:
            raise AnswerVersionConflictError(answer.version, answer.text_content)
        answer.text_content = self.normalize_text(payload.text_content)
        answer.version += 1
        await session.flush()
        result = await self.project(session, answer)
        await self._emit_updated(session, result)
        return result

    async def withdraw_text(self, session: AsyncSession, *, answer_id: UUID, user_id: UUID) -> None:
        answer = await self.repository.lock_answer(session, answer_id)
        if answer is None:
            raise AnswerNotFoundError
        lecture_session = await self._require_professor(
            session, session_id=answer.session_id, user_id=user_id
        )
        if lecture_session.status != "COMPLETED" or answer.status != "COMPLETED":
            raise AnswerSessionStateError
        if answer.source_transcript_version_id is not None:
            if answer.text_content is None:
                raise AnswerTargetStateError
            answer.text_content = None
            answer.version += 1
            await session.flush()
            await self._emit_updated(session, await self.project(session, answer))
            return
        target, target_kind = await self._lock_answer_target(session, answer)
        target.status = "OPEN"
        target.version += 1
        await session.delete(answer)
        await session.flush()
        await self.outbox.enqueue(
            session,
            session_id=lecture_session.id,
            partition_key=f"session:{lecture_session.id}",
            event_type="answer.deleted",
            resource_version=None,
            payload={
                "answer_id": str(answer_id),
                "target_type": target_kind,
                "target_id": str(target.id),
            },
        )

    async def _projection_context(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        answers: list[Answer],
    ) -> _AnswerProjectionContext:
        answer_ids = [answer.id for answer in answers]
        organizations = (
            list(
                await session.scalars(
                    select(AnswerOrganization).where(AnswerOrganization.answer_id.in_(answer_ids))
                )
            )
            if answer_ids
            else []
        )
        jobs = (
            list(
                await session.scalars(
                    select(AIJob)
                    .where(
                        AIJob.job_type == AIJobType.ANSWER_ORGANIZATION,
                        AIJob.target_answer_id.in_(answer_ids),
                    )
                    .order_by(AIJob.created_at.desc(), AIJob.id.desc())
                )
            )
            if answer_ids
            else []
        )
        segment_ids = {
            segment_id
            for answer in answers
            for segment_id in (answer.start_segment_id, answer.end_segment_id)
            if segment_id is not None
        }
        segment_ids.update(
            segment_id
            for organization in organizations
            for segment_id in (
                organization.source_start_segment_id,
                organization.source_end_segment_id,
            )
        )
        segments = (
            list(
                await session.scalars(
                    select(TranscriptSegment).where(TranscriptSegment.id.in_(segment_ids))
                )
            )
            if segment_ids
            else []
        )
        organizations_by_answer = {
            organization.answer_id: organization for organization in organizations
        }
        jobs_by_id = {job.id: job for job in jobs}
        latest_jobs_by_answer: dict[UUID, AIJob] = {}
        for job in jobs:
            if job.target_answer_id is not None:
                latest_jobs_by_answer.setdefault(job.target_answer_id, job)
        jobs_by_answer: dict[UUID, AIJob] = {}
        for answer in answers:
            organization = organizations_by_answer.get(answer.id)
            job = (
                jobs_by_id.get(organization.created_by_job_id)
                if organization is not None
                else latest_jobs_by_answer.get(answer.id)
            )
            if job is not None:
                jobs_by_answer[answer.id] = job
        return _AnswerProjectionContext(
            lecture_session=lecture_session,
            segments={segment.id: segment for segment in segments},
            organizations=organizations_by_answer,
            organization_jobs=jobs_by_answer,
        )

    @staticmethod
    def _organization_job_is_consistent(
        answer: Answer, organization: AnswerOrganization, job: AIJob | None
    ) -> bool:
        return bool(
            job is not None
            and job.id == organization.created_by_job_id
            and job.attempt == organization.created_by_job_attempt
            and job.job_type == AIJobType.ANSWER_ORGANIZATION
            and job.target_answer_id == answer.id
            and job.status == AIJobStatus.SUCCEEDED
        )

    async def project(
        self,
        session: AsyncSession,
        answer: Answer,
        *,
        context: _AnswerProjectionContext | None = None,
    ) -> AnswerResponse:
        answer_type = "VOICE" if answer.source_transcript_version_id is not None else "TEXT"
        target: AnswerTarget
        if answer.target_question_id is not None:
            target = StudentQuestionAnswerTarget(
                type="STUDENT_QUESTION", question_id=answer.target_question_id
            )
        else:
            assert answer.target_representative_question_id is not None
            target = RepresentativeQuestionAnswerTarget(
                type="AI_REPRESENTATIVE_QUESTION",
                representative_question_id=answer.target_representative_question_id,
            )
        start_sequence = end_sequence = None
        if answer.start_segment_id is not None:
            if context is None:
                start = await session.get(TranscriptSegment, answer.start_segment_id)
                end = await session.get(TranscriptSegment, answer.end_segment_id)
            else:
                start = context.segments.get(answer.start_segment_id)
                end = context.segments.get(answer.end_segment_id)
            start_sequence = start.sequence if start is not None else None
            end_sequence = end.sequence if end is not None else None
        lecture_session = (
            context.lecture_session
            if context is not None
            else await session.get(LectureSession, answer.session_id)
        )
        mapping = await self.repository.canonical_mapping(
            session,
            answer_id=answer.id,
            version_id=lecture_session.canonical_transcript_version_id if lecture_session else None,
        )
        mapping_response = (
            AnswerTranscriptMappingResponse(
                target_transcript_version_id=mapping.target_transcript_version_id,
                status=mapping.status,
                start_segment_id=mapping.mapped_start_segment_id,
                end_segment_id=mapping.mapped_end_segment_id,
                updated_at=mapping.updated_at,
            )
            if mapping is not None
            else None
        )
        organization_state = AnswerOrganizationStateResponse(status="NOT_APPLICABLE")
        if answer_type == "VOICE":
            if context is None:
                organization = await session.scalar(
                    select(AnswerOrganization).where(AnswerOrganization.answer_id == answer.id)
                )
                organization_job = (
                    await session.get(AIJob, organization.created_by_job_id)
                    if organization is not None
                    else await session.scalar(
                        select(AIJob)
                        .where(
                            AIJob.job_type == AIJobType.ANSWER_ORGANIZATION,
                            AIJob.target_answer_id == answer.id,
                        )
                        .order_by(AIJob.created_at.desc(), AIJob.id.desc())
                    )
                )
            else:
                organization_job = context.organization_jobs.get(answer.id)
                organization = context.organizations.get(answer.id)
            if organization is not None:
                job_is_consistent = self._organization_job_is_consistent(
                    answer, organization, organization_job
                )
                if not job_is_consistent:
                    organization_state = AnswerOrganizationStateResponse(
                        status="DATA_INTEGRITY_ERROR",
                        job_id=(organization_job.id if organization_job is not None else None),
                        attempt=(
                            organization_job.attempt if organization_job is not None else None
                        ),
                    )
                elif context is None:
                    organization_start = await session.get(
                        TranscriptSegment, organization.source_start_segment_id
                    )
                    organization_end = await session.get(
                        TranscriptSegment, organization.source_end_segment_id
                    )
                else:
                    organization_start = context.segments.get(organization.source_start_segment_id)
                    organization_end = context.segments.get(organization.source_end_segment_id)
                if job_is_consistent and (organization_start is None or organization_end is None):
                    organization_state = AnswerOrganizationStateResponse(
                        status="DATA_INTEGRITY_ERROR",
                        job_id=organization_job.id,
                        attempt=organization_job.attempt,
                    )
                elif job_is_consistent:
                    organization_state = AnswerOrganizationStateResponse(
                        status="SUCCEEDED",
                        job_id=organization_job.id,
                        attempt=organization_job.attempt,
                        organization=AnswerOrganizationResponse(
                            content=organization.content,
                            source_transcript_version_id=(
                                organization.source_transcript_version_id
                            ),
                            start_sequence=organization_start.sequence,
                            end_sequence=organization_end.sequence,
                            created_by_job_id=organization.created_by_job_id,
                            created_by_job_attempt=(organization.created_by_job_attempt),
                            model_name=organization.model_name,
                            prompt_version=organization.prompt_version,
                            created_at=organization.created_at,
                        ),
                    )
            elif organization_job is not None:
                status = str(organization_job.status)
                if status == "SUCCEEDED":
                    status = "DATA_INTEGRITY_ERROR"
                elif status not in ("PENDING", "RUNNING", "FAILED"):
                    status = "FAILED"
                organization_state = AnswerOrganizationStateResponse(
                    status=status,
                    job_id=organization_job.id,
                    attempt=organization_job.attempt,
                    retryable=(organization_job.retryable if status == "FAILED" else False),
                )
            elif answer.status != "COMPLETED":
                organization_state = AnswerOrganizationStateResponse(status="NOT_STARTED")
            elif (
                lecture_session is not None
                and lecture_session.status == LectureSessionStatus.PROCESSING
            ):
                organization_state = AnswerOrganizationStateResponse(status="WAITING_SOURCE")
            else:
                organization_state = AnswerOrganizationStateResponse(status="DATA_INTEGRITY_ERROR")
        return AnswerResponse(
            id=answer.id,
            session_id=answer.session_id,
            answer_type=answer_type,
            status=answer.status,
            version=answer.version,
            target=target,
            target_text_snapshot=answer.target_text_snapshot,
            text_content=answer.text_content,
            source_transcript_version_id=answer.source_transcript_version_id,
            canonical_transcript_mapping=mapping_response,
            organization_state=organization_state,
            capture_started_after_sequence=answer.capture_started_after_sequence,
            start_sequence=start_sequence,
            end_sequence=end_sequence,
            started_at=answer.started_at,
            completed_at=answer.completed_at,
            updated_at=answer.updated_at,
        )

    async def _require_member(self, session: AsyncSession, *, session_id: UUID, user_id: UUID):
        lecture_session = await self.repository.lock_session(session, session_id)
        if lecture_session is None:
            raise AnswerNotFoundError
        role = await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == lecture_session.course_id, CourseMember.user_id == user_id
            )
        )
        if role is None:
            raise AnswerAccessDeniedError
        return lecture_session

    async def _require_professor(self, session: AsyncSession, *, session_id: UUID, user_id: UUID):
        lecture_session = await self._require_member(
            session, session_id=session_id, user_id=user_id
        )
        role = await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == lecture_session.course_id, CourseMember.user_id == user_id
            )
        )
        if role != "PROFESSOR":
            raise AnswerRoleRequiredError
        return lecture_session

    async def _lock_target(
        self, session: AsyncSession, *, session_id: UUID, target: AnswerTarget
    ) -> tuple[Question | AIRepresentativeQuestion, str]:
        if isinstance(target, StudentQuestionAnswerTarget):
            question = await self.repository.lock_question(session, target.question_id)
            if question is None or question.session_id != session_id:
                raise AnswerNotFoundError
            return question, "STUDENT_QUESTION"
        representative = await self.repository.lock_representative(
            session, target.representative_question_id
        )
        if (
            representative is None
            or representative.session_id != session_id
            or representative.lifecycle_status == "DISCARDED"
        ):
            raise AnswerNotFoundError
        return representative, "AI_REPRESENTATIVE_QUESTION"

    async def _lock_answer_target(
        self, session: AsyncSession, answer: Answer
    ) -> tuple[Question | AIRepresentativeQuestion, str]:
        if answer.target_question_id is not None:
            return await self._lock_target(
                session,
                session_id=answer.session_id,
                target=StudentQuestionAnswerTarget(
                    type="STUDENT_QUESTION", question_id=answer.target_question_id
                ),
            )
        assert answer.target_representative_question_id is not None
        return await self._lock_target(
            session,
            session_id=answer.session_id,
            target=RepresentativeQuestionAnswerTarget(
                type="AI_REPRESENTATIVE_QUESTION",
                representative_question_id=answer.target_representative_question_id,
            ),
        )

    async def _existing_target_answer(
        self,
        session: AsyncSession,
        target: Question | AIRepresentativeQuestion,
        target_kind: str,
    ) -> Answer | None:
        return await self.repository.existing_target_answer(
            session,
            question_id=target.id if target_kind == "STUDENT_QUESTION" else None,
            representative_id=target.id if target_kind == "AI_REPRESENTATIVE_QUESTION" else None,
        )

    @staticmethod
    def _require_open_target(target: Question | AIRepresentativeQuestion) -> None:
        if target.status != "OPEN":
            raise AnswerTargetStateError

    @staticmethod
    def _target_text(target: Question | AIRepresentativeQuestion) -> str:
        return target.content if isinstance(target, Question) else target.text

    @staticmethod
    def normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFC", value.strip())
        length = len(normalized)
        if length == 0:
            raise AnswerTextValidationError("EMPTY_AFTER_NORMALIZATION", length)
        if length > MAX_ANSWER_TEXT_LENGTH:
            raise AnswerTextValidationError("MAX_LENGTH_EXCEEDED", length)
        return normalized

    async def _emit_updated(self, session: AsyncSession, answer: AnswerResponse) -> None:
        await self.outbox.enqueue(
            session,
            session_id=answer.session_id,
            partition_key=f"session:{answer.session_id}",
            event_type="answer.updated",
            resource_version=answer.version,
            payload=answer.model_dump(mode="json"),
        )
