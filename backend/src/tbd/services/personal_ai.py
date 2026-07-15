"""Requester-only LIVE Summary and private Chat domain services."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tbd.jobs.kernel import JobKernel
from tbd.models.consistency import IdempotencyRecord
from tbd.models.courses import CourseMember
from tbd.models.enums import (
    AIJobStatus,
    AIJobType,
    AIJobVisibility,
    ChatMessageRole,
    LectureSessionStatus,
    SummaryType,
    SummaryVisibility,
    TranscriptSource,
    TranscriptStatus,
)
from tbd.models.knowledge import (
    ChatMessage,
    ChatMessageEvidence,
    ChatSession,
    KnowledgeChunk,
    LectureSummary,
)
from tbd.models.materials import TranscriptSegment, TranscriptVersion
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession
from tbd.providers.ai import (
    AIProviderError,
    EmbeddingProvider,
    LLMGenerationRequest,
    LLMMessage,
    LLMProvider,
    ProviderInvalidResponseError,
)
from tbd.repositories.idempotency import IdempotencyRepository
from tbd.repositories.jobs import ClaimedJob, JobRepository
from tbd.schemas.personal_ai import (
    ChatEvidenceResponse,
    ChatMessageResponse,
    ChatResponse,
    LectureSummaryResponse,
    SummaryRange,
)
from tbd.services.knowledge import (
    KNOWLEDGE_EMBEDDING_TIMEOUT,
    KnowledgeRetrievalService,
    KnowledgeSearchResult,
    project_evidence,
)

PERSONAL_AI_LEASE = timedelta(minutes=1)
PERSONAL_AI_PROVIDER_TIMEOUT = timedelta(seconds=60)
LIVE_SUMMARY_PROMPT_VERSION = "live-summary-v1"
CHAT_PROMPT_VERSION = "rag-chat-v2"
COURSE_ANSWER_TAG = "[[COURSE]]"
GENERAL_ANSWER_TAG = "[[GENERAL]]"
COURSE_ANSWER_PREFIX = "강의 근거에 의하면, "
GENERAL_ANSWER_PREFIX = "강의 내용에는 직접적인 근거가 없지만, 일반적으로 "


class PersonalAINotFoundError(Exception):
    """The caller may not learn whether a private resource exists."""


class PersonalAIStateConflictError(Exception):
    """The current Session state cannot accept the requested private AI action."""


class SummaryTranscriptNotReadyError(Exception):
    """No final transcript Segment exists in the requested LIVE range."""


class SummarySourceUnavailableError(Exception):
    """The selected transcript source has terminally failed."""


class ChatResponseInProgressError(Exception):
    """One Chat already has a pending or running answer turn."""


class PersonalAIInputUnavailableError(Exception):
    """The private request input no longer exists or is no longer current."""


@dataclass(frozen=True, slots=True)
class SummaryRequestResult:
    job: AIJob


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    user_message: ChatMessage
    job: AIJob


@dataclass(frozen=True, slots=True)
class _ClaimedPersonalAIWork:
    job_id: UUID
    session_id: UUID
    attempt: int
    run_token: UUID
    job_type: str
    target_chat_id: UUID | None


@dataclass(frozen=True, slots=True)
class _SummaryGeneration:
    content: str
    model_name: str | None


@dataclass(frozen=True, slots=True)
class _ChatGeneration:
    content: str
    model_name: str | None
    evidence: tuple[KnowledgeSearchResult, ...]


def _resolve_chat_answer(
    content: str,
    *,
    evidence_available: bool,
) -> tuple[str, bool]:
    """Apply the visible source policy and decide whether to publish Evidence.

    The model makes the relevance judgement because vector search can return a
    nearest Chunk even when it does not directly support the user's question.
    An untagged or invalid ``COURSE`` response falls back to a clearly labeled
    general answer so the UI never presents unrelated source links as support.
    """

    normalized = content.strip()
    if not normalized:
        raise ProviderInvalidResponseError
    if normalized.startswith(COURSE_ANSWER_TAG):
        answer = normalized.removeprefix(COURSE_ANSWER_TAG).strip()
        if answer and evidence_available:
            return f"{COURSE_ANSWER_PREFIX}{answer}", True
        normalized = answer or normalized
    elif normalized.startswith(GENERAL_ANSWER_TAG):
        normalized = normalized.removeprefix(GENERAL_ANSWER_TAG).strip()
        if not normalized:
            raise ProviderInvalidResponseError
    return f"{GENERAL_ANSWER_PREFIX}{normalized}", False


class PersonalAIService:
    """Keep private-resource authorization and lifecycle checks in one layer."""

    async def request_live_summary(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        requested_range: SummaryRange | None,
        now: datetime | None = None,
    ) -> SummaryRequestResult:
        lecture_session = await self._lock_member_session(session, session_id, user_id)
        self._require_state(lecture_session.status, expected="LIVE")
        source, start, end = await self._summary_source(
            session,
            lecture_session=lecture_session,
            requested_range=requested_range,
        )
        timestamp = now or datetime.now(UTC)
        dedupe_key_hash = _digest(
            "LIVE_SUMMARY",
            str(lecture_session.id),
            str(user_id),
            str(source.id),
            str(start.id),
            str(end.id),
        )
        existing = await session.scalar(
            select(AIJob)
            .where(
                AIJob.session_id == lecture_session.id,
                AIJob.job_type == AIJobType.LIVE_SUMMARY,
                AIJob.dedupe_key_hash == dedupe_key_hash,
            )
            .with_for_update()
        )
        if existing is not None:
            return SummaryRequestResult(job=existing)
        job = AIJob(
            session_id=lecture_session.id,
            requester_user_id=user_id,
            job_type=AIJobType.LIVE_SUMMARY,
            visibility=AIJobVisibility.REQUESTER_ONLY,
            status=AIJobStatus.PENDING,
            attempt=1,
            version=1,
            input_transcript_version_id=source.id,
            input_start_segment_id=start.id,
            input_end_segment_id=end.id,
            dedupe_key_hash=dedupe_key_hash,
            available_at=timestamp,
            blocks_session_completion=False,
            retryable=False,
        )
        await JobKernel().enqueue(session, job)
        return SummaryRequestResult(job=job)

    async def create_chat(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        mode: str,
    ) -> ChatSession:
        lecture_session = await self._lock_member_session(session, session_id, user_id)
        expected = "LIVE" if mode == "LIVE" else "COMPLETED"
        self._require_state(lecture_session.status, expected=expected)
        chat = ChatSession(
            session_id=lecture_session.id, owner_user_id=user_id, mode=mode, version=1
        )
        session.add(chat)
        await session.flush()
        return chat

    async def create_chat_turn(
        self,
        session: AsyncSession,
        *,
        chat_id: UUID,
        user_id: UUID,
        content: str,
        now: datetime | None = None,
    ) -> ChatTurnResult:
        normalized = self.normalize_user_content(content)
        chat, lecture_session = await self._lock_owned_chat(session, chat_id, user_id)
        self._require_state(
            lecture_session.status, expected="LIVE" if chat.mode == "LIVE" else "COMPLETED"
        )
        in_progress = await session.scalar(
            select(AIJob.id)
            .where(
                AIJob.target_chat_id == chat.id,
                AIJob.job_type == AIJobType.CHAT_RESPONSE,
                AIJob.status.in_([AIJobStatus.PENDING, AIJobStatus.RUNNING]),
            )
            .with_for_update()
        )
        if in_progress is not None:
            raise ChatResponseInProgressError
        next_sequence = (
            int(
                await session.scalar(
                    select(func.coalesce(func.max(ChatMessage.sequence), 0)).where(
                        ChatMessage.chat_id == chat.id
                    )
                )
                or 0
            )
            + 1
        )
        user_message = ChatMessage(
            chat_id=chat.id,
            session_id=chat.session_id,
            sequence=next_sequence,
            role="USER",
            content=normalized,
        )
        session.add(user_message)
        await session.flush()
        timestamp = now or datetime.now(UTC)
        job = AIJob(
            session_id=chat.session_id,
            requester_user_id=user_id,
            job_type=AIJobType.CHAT_RESPONSE,
            visibility=AIJobVisibility.REQUESTER_ONLY,
            status=AIJobStatus.PENDING,
            attempt=1,
            version=1,
            target_chat_id=chat.id,
            target_user_message_id=user_message.id,
            dedupe_key_hash=_digest(
                "CHAT_RESPONSE", str(chat.id), str(user_message.id), str(user_id)
            ),
            available_at=timestamp,
            blocks_session_completion=False,
            retryable=False,
        )
        await JobKernel().enqueue(session, job)
        return ChatTurnResult(user_message=user_message, job=job)

    async def list_summaries(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        summary_type: str,
        limit: int,
    ) -> tuple[list[LectureSummary], str, dict[str, str] | None]:
        lecture_session = await self._member_session(session, session_id, user_id)
        if summary_type == "LIVE":
            items = list(
                await session.scalars(
                    select(LectureSummary)
                    .where(
                        LectureSummary.session_id == lecture_session.id,
                        LectureSummary.summary_type == summary_type,
                        LectureSummary.requester_user_id == user_id,
                    )
                    .order_by(LectureSummary.created_at.desc(), LectureSummary.id.desc())
                    .limit(limit)
                )
            )
            if items:
                return items, "AVAILABLE", None
            return [], "NOT_STARTED", None
        return await self.final_summary_state(session, lecture_session)

    async def final_summary_state(
        self, session: AsyncSession, lecture_session: LectureSession
    ) -> tuple[list[LectureSummary], str, dict[str, str] | None]:
        """Expose the canonical FINAL state projection to public Course archives."""

        return await self._final_summary_state(session, lecture_session)

    async def _final_summary_state(
        self, session: AsyncSession, lecture_session: LectureSession
    ) -> tuple[list[LectureSummary], str, dict[str, str] | None]:
        """Project FINAL Summary state from immutable HQ source and Job records."""

        coordinator = await session.scalar(
            select(AIJob).where(
                AIJob.session_id == lecture_session.id,
                AIJob.job_type == AIJobType.SESSION_POSTPROCESSING,
            )
        )
        version = await session.scalar(
            select(TranscriptVersion)
            .where(
                TranscriptVersion.session_id == lecture_session.id,
                TranscriptVersion.source == TranscriptSource.RECORDING,
            )
            .order_by(TranscriptVersion.version.desc())
        )
        if version is None:
            if coordinator is None or coordinator.status in (
                AIJobStatus.PENDING,
                AIJobStatus.RUNNING,
            ):
                return [], "PENDING", None
            return [], "FAILED", {"code": "SUMMARY_SOURCE_UNAVAILABLE"}
        if version.status == TranscriptStatus.EMPTY:
            return [], "NOT_APPLICABLE", {"code": "NO_FINAL_TRANSCRIPT"}
        if version.status != TranscriptStatus.FINALIZED or version.last_sequence <= 0:
            if version.status == TranscriptStatus.FAILED:
                return [], "FAILED", {"code": "SUMMARY_SOURCE_UNAVAILABLE"}
            return [], "PENDING", None
        summary = await session.scalar(
            select(LectureSummary)
            .where(
                LectureSummary.session_id == lecture_session.id,
                LectureSummary.summary_type == SummaryType.FINAL,
                LectureSummary.visibility == SummaryVisibility.COURSE_MEMBERS,
                LectureSummary.requester_user_id.is_(None),
                LectureSummary.source_transcript_version_id == version.id,
            )
            .order_by(LectureSummary.created_at.desc(), LectureSummary.id.desc())
        )
        if summary is not None:
            creating_job = await session.get(AIJob, summary.created_by_job_id)
            if (
                creating_job is not None
                and creating_job.job_type == AIJobType.FINAL_SUMMARY
                and creating_job.status == AIJobStatus.SUCCEEDED
                and creating_job.attempt == summary.created_by_job_attempt
            ):
                return [summary], "AVAILABLE", None
            return [], "DATA_INTEGRITY_ERROR", None
        final_job = await session.scalar(
            select(AIJob)
            .where(
                AIJob.session_id == lecture_session.id,
                AIJob.job_type == AIJobType.FINAL_SUMMARY,
                AIJob.visibility == AIJobVisibility.SHARED,
                AIJob.requester_user_id.is_(None),
            )
            .order_by(AIJob.created_at.desc(), AIJob.id.desc())
        )
        if final_job is None:
            if coordinator is not None and coordinator.status in (
                AIJobStatus.PENDING,
                AIJobStatus.RUNNING,
            ):
                return [], "PENDING", None
            return [], "DATA_INTEGRITY_ERROR", None
        if final_job.status in (AIJobStatus.PENDING, AIJobStatus.RUNNING):
            return [], "PENDING", None
        if final_job.status == AIJobStatus.SUCCEEDED:
            return [], "DATA_INTEGRITY_ERROR", None
        return [], "FAILED", {"code": final_job.error_code or "FINAL_SUMMARY_FAILED"}

    async def get_summary(
        self, session: AsyncSession, *, summary_id: UUID, user_id: UUID
    ) -> LectureSummary:
        summary = await session.scalar(
            select(LectureSummary)
            .join(LectureSession, LectureSession.id == LectureSummary.session_id)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(
                LectureSummary.id == summary_id,
                CourseMember.user_id == user_id,
                (LectureSummary.summary_type == "FINAL")
                | (LectureSummary.requester_user_id == user_id),
            )
        )
        if summary is None:
            raise PersonalAINotFoundError
        return summary

    async def list_chats(
        self, session: AsyncSession, *, session_id: UUID, user_id: UUID, limit: int
    ) -> list[ChatSession]:
        lecture_session = await self._member_session(session, session_id, user_id)
        return list(
            await session.scalars(
                select(ChatSession)
                .where(
                    ChatSession.session_id == lecture_session.id,
                    ChatSession.owner_user_id == user_id,
                )
                .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
                .limit(limit)
            )
        )

    async def get_chat(self, session: AsyncSession, *, chat_id: UUID, user_id: UUID) -> ChatSession:
        chat, _ = await self._owned_chat(session, chat_id, user_id)
        return chat

    async def list_messages(
        self, session: AsyncSession, *, chat_id: UUID, user_id: UUID, limit: int
    ) -> list[ChatMessage]:
        chat, _ = await self._owned_chat(session, chat_id, user_id)
        return list(
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.chat_id == chat.id)
                .order_by(ChatMessage.sequence.asc())
                .limit(limit)
            )
        )

    async def get_message(
        self, session: AsyncSession, *, message_id: UUID, user_id: UUID
    ) -> ChatMessage:
        message = await session.scalar(
            select(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.chat_id)
            .join(LectureSession, LectureSession.id == ChatSession.session_id)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(
                ChatMessage.id == message_id,
                ChatSession.owner_user_id == user_id,
                CourseMember.user_id == user_id,
            )
        )
        if message is None:
            raise PersonalAINotFoundError
        return message

    async def project_message(
        self, session: AsyncSession, message: ChatMessage
    ) -> ChatMessageResponse:
        response_job_id = None
        if message.role == "USER":
            response_job_id = await session.scalar(
                select(AIJob.id).where(
                    AIJob.target_user_message_id == message.id,
                    AIJob.target_chat_id == message.chat_id,
                    AIJob.job_type == AIJobType.CHAT_RESPONSE,
                )
            )
        evidence: list[ChatEvidenceResponse] = []
        if message.role == "ASSISTANT":
            rows = await session.execute(
                select(ChatMessageEvidence, KnowledgeChunk)
                .join(KnowledgeChunk, KnowledgeChunk.id == ChatMessageEvidence.knowledge_chunk_id)
                .where(ChatMessageEvidence.chat_message_id == message.id)
                .order_by(ChatMessageEvidence.rank)
            )
            for evidence_row, chunk in rows:
                projected = await project_evidence(session, chunk=chunk)
                evidence.append(
                    ChatEvidenceResponse(
                        source_kind=_source_kind(chunk),
                        label=evidence_row.label_snapshot,
                        link=projected.link if projected is not None else None,
                    )
                )
        return ChatMessageResponse(
            id=message.id,
            chat_id=message.chat_id,
            job_id=message.created_by_job_id,
            response_job_id=response_job_id,
            sequence=message.sequence,
            role=message.role,
            content=message.content,
            evidence=evidence,
            model_name=message.model_name,
            prompt_version=message.prompt_version,
            created_at=message.created_at,
        )

    async def lock_purge_records(
        self, session: AsyncSession, *, session_id: UUID
    ) -> list[IdempotencyRecord]:
        return list(
            await session.scalars(
                select(IdempotencyRecord)
                .where(
                    IdempotencyRecord.session_id == session_id,
                    IdempotencyRecord.purge_on_session_end.is_(True),
                )
                .order_by(IdempotencyRecord.id)
                .with_for_update()
            )
        )

    async def purge_live(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        records: list[IdempotencyRecord],
        idempotency: IdempotencyRepository | None,
        now: datetime,
    ) -> None:
        summaries = list(
            await session.scalars(
                select(LectureSummary)
                .where(
                    LectureSummary.session_id == lecture_session.id,
                    LectureSummary.summary_type == "LIVE",
                )
                .order_by(LectureSummary.id)
                .with_for_update()
            )
        )
        chats = list(
            await session.scalars(
                select(ChatSession)
                .where(ChatSession.session_id == lecture_session.id, ChatSession.mode == "LIVE")
                .order_by(ChatSession.id)
                .with_for_update()
            )
        )
        chat_ids = [chat.id for chat in chats]
        if chat_ids:
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.chat_id.in_(chat_ids))
                .order_by(ChatMessage.id)
                .with_for_update()
            )
        jobs = list(
            await session.scalars(
                select(AIJob)
                .where(
                    AIJob.session_id == lecture_session.id,
                    AIJob.visibility == AIJobVisibility.REQUESTER_ONLY,
                    (
                        (AIJob.job_type == AIJobType.LIVE_SUMMARY)
                        | (
                            (AIJob.job_type == AIJobType.CHAT_RESPONSE)
                            & AIJob.target_chat_id.in_(chat_ids)
                        )
                    ),
                )
                .order_by(AIJob.id)
                .with_for_update()
            )
        )
        for summary in summaries:
            await session.delete(summary)
        for chat in chats:
            await session.delete(chat)
        for job in jobs:
            await session.delete(job)
        await session.flush()
        if idempotency is not None:
            await idempotency.mark_live_ai_purged(session, records=records, now=now)

    @staticmethod
    def normalize_user_content(content: str) -> str:
        normalized = unicodedata.normalize("NFC", content.strip())
        length = len(normalized)
        if length == 0:
            raise PersonalAIContentValidationError("EMPTY_AFTER_NORMALIZATION", length)
        if length > 2000:
            raise PersonalAIContentValidationError("MAX_LENGTH_EXCEEDED", length)
        return normalized

    async def _summary_source(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        requested_range: SummaryRange | None,
    ) -> tuple[TranscriptVersion, TranscriptSegment, TranscriptSegment]:
        if lecture_session.canonical_transcript_version_id is None:
            raise SummaryTranscriptNotReadyError
        source = await session.scalar(
            select(TranscriptVersion)
            .where(
                TranscriptVersion.id == lecture_session.canonical_transcript_version_id,
                TranscriptVersion.session_id == lecture_session.id,
            )
            .with_for_update()
        )
        # A LIVE transcript remains FINALIZING until class end, but each stored
        # Segment is already final STT output and therefore safe as a Summary
        # source. Availability is determined by the selected Segment range.
        if source is None or source.status == "EMPTY":
            raise SummaryTranscriptNotReadyError
        if source.status == "FAILED":
            raise SummarySourceUnavailableError
        clauses = [TranscriptSegment.transcript_version_id == source.id]
        if requested_range is not None and requested_range.start_sequence is not None:
            clauses.append(TranscriptSegment.sequence >= requested_range.start_sequence)
        if requested_range is not None and requested_range.end_sequence is not None:
            clauses.append(TranscriptSegment.sequence <= requested_range.end_sequence)
        segments = list(
            await session.scalars(
                select(TranscriptSegment)
                .where(*clauses)
                .order_by(TranscriptSegment.sequence)
                .with_for_update()
            )
        )
        if not segments:
            raise SummaryTranscriptNotReadyError
        return source, segments[0], segments[-1]

    async def _member_session(
        self, session: AsyncSession, session_id: UUID, user_id: UUID
    ) -> LectureSession:
        lecture_session = await session.scalar(
            select(LectureSession)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(LectureSession.id == session_id, CourseMember.user_id == user_id)
        )
        if lecture_session is None:
            raise PersonalAINotFoundError
        return lecture_session

    async def _lock_member_session(
        self, session: AsyncSession, session_id: UUID, user_id: UUID
    ) -> LectureSession:
        lecture_session = await session.scalar(
            select(LectureSession)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(LectureSession.id == session_id, CourseMember.user_id == user_id)
            .with_for_update(of=LectureSession)
        )
        if lecture_session is None:
            raise PersonalAINotFoundError
        return lecture_session

    async def _owned_chat(
        self, session: AsyncSession, chat_id: UUID, user_id: UUID
    ) -> tuple[ChatSession, LectureSession]:
        row = (
            await session.execute(
                select(ChatSession, LectureSession)
                .join(LectureSession, LectureSession.id == ChatSession.session_id)
                .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
                .where(
                    ChatSession.id == chat_id,
                    ChatSession.owner_user_id == user_id,
                    CourseMember.user_id == user_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise PersonalAINotFoundError
        return row

    async def _lock_owned_chat(
        self, session: AsyncSession, chat_id: UUID, user_id: UUID
    ) -> tuple[ChatSession, LectureSession]:
        row = (
            await session.execute(
                select(ChatSession, LectureSession)
                .join(LectureSession, LectureSession.id == ChatSession.session_id)
                .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
                .where(
                    ChatSession.id == chat_id,
                    ChatSession.owner_user_id == user_id,
                    CourseMember.user_id == user_id,
                )
                .with_for_update(of=(LectureSession, ChatSession))
            )
        ).one_or_none()
        if row is None:
            raise PersonalAINotFoundError
        return row

    @staticmethod
    def _require_state(status: str, *, expected: str) -> None:
        if status != expected:
            raise PersonalAIStateConflictError


@dataclass(frozen=True, slots=True)
class PersonalAIContentValidationError(Exception):
    reason: str
    actual_length: int


def summary_response(
    summary: LectureSummary,
    *,
    start_sequence: int,
    end_sequence: int,
) -> LectureSummaryResponse:
    return LectureSummaryResponse(
        id=summary.id,
        session_id=summary.session_id,
        job_id=summary.created_by_job_id,
        summary_type=summary.summary_type,
        visibility=summary.visibility,
        content=summary.content,
        source_transcript_version_id=summary.source_transcript_version_id,
        source_start_sequence=start_sequence,
        source_end_sequence=end_sequence,
        model_name=summary.model_name,
        prompt_version=summary.prompt_version,
        created_at=summary.created_at,
    )


def chat_response(chat: ChatSession) -> ChatResponse:
    return ChatResponse(
        id=chat.id,
        session_id=chat.session_id,
        mode=chat.mode,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


def _digest(*parts: str) -> bytes:
    return hashlib.sha256("\x1f".join(parts).encode()).digest()


def _source_kind(chunk: KnowledgeChunk) -> str:
    if chunk.material_id is not None:
        return "MATERIAL"
    if chunk.source_transcript_version_id is not None:
        return "TRANSCRIPT"
    if chunk.answer_id is not None:
        return "ANSWER"
    return "QUESTION"


class PersonalAIWorker:
    """Run private Summary and Chat Jobs without publishing shared events.

    Claiming follows the same Session → Chat → Job lock order as the end-of-
    class purge. A worker that loses that fence never persists an old result.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
        *,
        jobs: JobRepository | None = None,
        provider_timeout: timedelta = PERSONAL_AI_PROVIDER_TIMEOUT,
        embedding_timeout: timedelta = KNOWLEDGE_EMBEDDING_TIMEOUT,
    ) -> None:
        if provider_timeout.total_seconds() <= 0:
            raise ValueError("provider_timeout must be positive")
        if embedding_timeout.total_seconds() <= 0:
            raise ValueError("embedding_timeout must be positive")
        self.session_factory = session_factory
        self.llm_provider = llm_provider
        self.retrieval = KnowledgeRetrievalService(
            embedding_provider,
            embedding_timeout=embedding_timeout,
        )
        self.jobs = jobs or JobRepository()
        self.provider_timeout = provider_timeout

    async def run_once(self, *, now: datetime | None = None) -> bool:
        """Claim and process one requester-only Job, if a due Job exists."""

        timestamp = now or datetime.now(UTC)
        expired = await self._fail_expired(timestamp)
        claimed, had_candidate = await self._claim(timestamp)
        if claimed is None:
            return bool(expired) or had_candidate
        try:
            if claimed.job_type == AIJobType.LIVE_SUMMARY:
                generated = await self._generate_summary(claimed)
                await self._persist_summary(claimed, generated, timestamp)
            else:
                generated = await self._generate_chat_response(claimed)
                await self._persist_chat_response(claimed, generated, timestamp)
        except PersonalAIInputUnavailableError:
            await self._fail(
                claimed,
                code="PERSONAL_AI_INPUT_UNAVAILABLE",
                message="요청한 강의 근거를 더 이상 사용할 수 없습니다.",
                retryable=False,
                now=timestamp,
            )
        except AIProviderError as exc:
            await self._fail(
                claimed,
                code=str(exc.code),
                message="개인 AI 제공자를 사용할 수 없습니다.",
                retryable=exc.retryable,
                now=timestamp,
            )
        except Exception:
            await self._fail(
                claimed,
                code="PERSONAL_AI_PROCESSING_FAILED",
                message="개인 AI 결과를 처리하지 못했습니다.",
                retryable=True,
                now=timestamp,
            )
        return True

    async def _fail_expired(self, now: datetime) -> list[UUID]:
        async with self.session_factory() as session:
            async with session.begin():
                return await self.jobs.fail_expired_requester_only(
                    session,
                    now=now,
                    job_types=(AIJobType.LIVE_SUMMARY, AIJobType.CHAT_RESPONSE),
                )

    async def _claim(self, now: datetime) -> tuple[_ClaimedPersonalAIWork | None, bool]:
        async with self.session_factory() as session:
            candidate = (
                await session.execute(
                    select(
                        AIJob.id,
                        AIJob.session_id,
                        AIJob.job_type,
                        AIJob.target_chat_id,
                    )
                    .where(
                        AIJob.status == AIJobStatus.PENDING,
                        AIJob.visibility == AIJobVisibility.REQUESTER_ONLY,
                        AIJob.available_at <= now,
                        AIJob.job_type.in_((AIJobType.LIVE_SUMMARY, AIJobType.CHAT_RESPONSE)),
                    )
                    .order_by(AIJob.available_at, AIJob.created_at, AIJob.id)
                    .limit(1)
                )
            ).one_or_none()
        if candidate is None:
            return None, False

        candidate_id, candidate_session_id, candidate_type, candidate_chat_id = candidate
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == candidate_session_id)
                    .with_for_update()
                )
                if lecture_session is None:
                    return None, True
                chat: ChatSession | None = None
                if candidate_type == AIJobType.CHAT_RESPONSE:
                    if candidate_chat_id is None:
                        return None, True
                    chat = await session.scalar(
                        select(ChatSession)
                        .where(ChatSession.id == candidate_chat_id)
                        .with_for_update()
                    )
                    if chat is None:
                        await self.jobs.cancel(session, candidate_id, now=now)
                        return None, True
                if not self._job_state_is_current(lecture_session, candidate_type, chat):
                    await self.jobs.cancel(session, candidate_id, now=now)
                    return None, True
                run = await self.jobs.claim_requester_by_id(
                    session,
                    candidate_id,
                    now=now,
                    lease_duration=PERSONAL_AI_LEASE,
                    job_types=(AIJobType.LIVE_SUMMARY, AIJobType.CHAT_RESPONSE),
                )
                if run is None:
                    return None, True
                return (
                    _ClaimedPersonalAIWork(
                        job_id=run.job_id,
                        session_id=run.session_id,
                        attempt=run.attempt,
                        run_token=run.run_token,
                        job_type=run.job_type,
                        target_chat_id=candidate_chat_id,
                    ),
                    True,
                )

    async def _generate_summary(self, claimed: _ClaimedPersonalAIWork) -> _SummaryGeneration:
        async with self.session_factory() as session:
            job = await session.get(AIJob, claimed.job_id)
            lecture_session = await session.get(LectureSession, claimed.session_id)
            if (
                job is None
                or lecture_session is None
                or job.input_transcript_version_id is None
                or job.input_start_segment_id is None
                or job.input_end_segment_id is None
                or lecture_session.status != LectureSessionStatus.LIVE
                or lecture_session.canonical_transcript_version_id
                != job.input_transcript_version_id
            ):
                raise PersonalAIInputUnavailableError
            start = await session.get(TranscriptSegment, job.input_start_segment_id)
            end = await session.get(TranscriptSegment, job.input_end_segment_id)
            if (
                start is None
                or end is None
                or start.transcript_version_id != job.input_transcript_version_id
                or end.transcript_version_id != job.input_transcript_version_id
                or start.sequence > end.sequence
            ):
                raise PersonalAIInputUnavailableError
            segments = list(
                await session.scalars(
                    select(TranscriptSegment)
                    .where(
                        TranscriptSegment.transcript_version_id == job.input_transcript_version_id,
                        TranscriptSegment.sequence.between(start.sequence, end.sequence),
                    )
                    .order_by(TranscriptSegment.sequence)
                )
            )
            source = "\n".join(segment.text for segment in segments).strip()
        if not source:
            raise PersonalAIInputUnavailableError
        result = await self.llm_provider.generate(
            LLMGenerationRequest(
                purpose="live-summary-v1",
                prompt_version=LIVE_SUMMARY_PROMPT_VERSION,
                messages=(
                    LLMMessage(
                        role="system",
                        content="주어진 강의 내용을 사실에 근거해 간결하게 요약하세요.",
                    ),
                    LLMMessage(role="user", content=source),
                ),
            ),
            timeout=self.provider_timeout,
        )
        content = result.content.strip()
        if not content:
            raise ProviderInvalidResponseError
        return _SummaryGeneration(content=content, model_name=result.model_name)

    async def _generate_chat_response(self, claimed: _ClaimedPersonalAIWork) -> _ChatGeneration:
        if claimed.target_chat_id is None:
            raise PersonalAIInputUnavailableError
        async with self.session_factory() as session:
            job = await session.get(AIJob, claimed.job_id)
            chat = await session.get(ChatSession, claimed.target_chat_id)
            lecture_session = await session.get(LectureSession, claimed.session_id)
            if (
                job is None
                or chat is None
                or lecture_session is None
                or job.target_user_message_id is None
                or not self._job_state_is_current(lecture_session, AIJobType.CHAT_RESPONSE, chat)
            ):
                raise PersonalAIInputUnavailableError
            message = await session.get(ChatMessage, job.target_user_message_id)
            if (
                message is None
                or message.chat_id != chat.id
                or message.role != ChatMessageRole.USER
            ):
                raise PersonalAIInputUnavailableError
            evidence = tuple(
                await self.retrieval.retrieve(
                    session,
                    course_id=lecture_session.course_id,
                    session_id=lecture_session.id,
                    query=message.content,
                )
            )
            history = list(
                await session.scalars(
                    select(ChatMessage)
                    .where(
                        ChatMessage.chat_id == chat.id,
                        ChatMessage.sequence < message.sequence,
                    )
                    .order_by(ChatMessage.sequence.desc())
                    .limit(6)
                )
            )
            history.reverse()
            history_text = "\n".join(
                f"{history_message.role}: {history_message.content}" for history_message in history
            )
            context = "\n\n".join(result.chunk.content for result in evidence) or "(없음)"
            question = message.content
        result = await self.llm_provider.generate(
            LLMGenerationRequest(
                purpose="rag-chat-v2",
                prompt_version=CHAT_PROMPT_VERSION,
                messages=(
                    LLMMessage(
                        role="system",
                        content=(
                            "사용자의 질문에 한국어로 최대한 도움이 되게 답하세요. 제공된 강의 "
                            "근거가 질문의 핵심 주장에 직접적으로 충분하면 첫 줄을 [[COURSE]]로 "
                            "시작하고, 그 근거에만 기반한 답변을 이어 쓰세요. 이 경우에만 강의 "
                            "근거를 사용했다고 말할 수 있습니다. 근거가 없거나 질문과 관련이 "
                            "약하거나 불완전하면 첫 줄을 [[GENERAL]]로 시작하고, 일반 지식에 "
                            "기반한 답변을 이어 쓰세요. [[GENERAL]]에서는 제공된 강의 근거를 "
                            "사실의 출처처럼 사용하지 마세요. 태그 뒤에는 답변 본문만 쓰고, "
                            "두 태그 중 하나는 반드시 선택하세요."
                        ),
                    ),
                    LLMMessage(
                        role="user",
                        content=(
                            f"이전 대화:\n{history_text or '(없음)'}\n\n"
                            f"질문:\n{question}\n\n근거:\n{context}"
                        ),
                    ),
                ),
            ),
            timeout=self.provider_timeout,
        )
        content = result.content.strip()
        answer, use_evidence = _resolve_chat_answer(
            content,
            evidence_available=bool(evidence),
        )
        return _ChatGeneration(
            content=answer,
            model_name=result.model_name,
            evidence=evidence if use_evidence else (),
        )

    async def _persist_summary(
        self,
        claimed: _ClaimedPersonalAIWork,
        generated: _SummaryGeneration,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session = await self._lock_session(session, claimed.session_id)
                job = await self._lock_current_job(session, claimed)
                if lecture_session is None or job is None:
                    return
                if (
                    lecture_session.status != LectureSessionStatus.LIVE
                    or lecture_session.canonical_transcript_version_id
                    != job.input_transcript_version_id
                    or job.input_transcript_version_id is None
                    or job.input_start_segment_id is None
                    or job.input_end_segment_id is None
                    or job.requester_user_id is None
                ):
                    await self.jobs.fail(
                        session,
                        self._as_run(claimed),
                        error_code="PERSONAL_AI_INPUT_UNAVAILABLE",
                        error_message="요청한 강의 근거를 더 이상 사용할 수 없습니다.",
                        retryable=False,
                        now=now,
                    )
                    return
                session.add(
                    LectureSummary(
                        session_id=lecture_session.id,
                        requester_user_id=job.requester_user_id,
                        created_by_job_id=job.id,
                        created_by_job_attempt=claimed.attempt,
                        summary_type=SummaryType.LIVE,
                        visibility=SummaryVisibility.REQUESTER_ONLY,
                        content=generated.content,
                        source_transcript_version_id=job.input_transcript_version_id,
                        source_start_segment_id=job.input_start_segment_id,
                        source_end_segment_id=job.input_end_segment_id,
                        model_name=generated.model_name,
                        prompt_version=LIVE_SUMMARY_PROMPT_VERSION,
                    )
                )
                changed = await self.jobs.succeed(session, self._as_run(claimed), now=now)
                if not changed:
                    raise RuntimeError("private summary Job fence was lost")

    async def _persist_chat_response(
        self,
        claimed: _ClaimedPersonalAIWork,
        generated: _ChatGeneration,
        now: datetime,
    ) -> None:
        if claimed.target_chat_id is None:
            return
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session = await self._lock_session(session, claimed.session_id)
                chat = await session.scalar(
                    select(ChatSession)
                    .where(ChatSession.id == claimed.target_chat_id)
                    .with_for_update()
                )
                job = await self._lock_current_job(session, claimed)
                if lecture_session is None or chat is None or job is None:
                    return
                if (
                    not self._job_state_is_current(lecture_session, AIJobType.CHAT_RESPONSE, chat)
                    or job.target_user_message_id is None
                ):
                    await self.jobs.cancel(session, job.id, now=now)
                    return
                user_message = await session.scalar(
                    select(ChatMessage)
                    .where(
                        ChatMessage.id == job.target_user_message_id,
                        ChatMessage.chat_id == chat.id,
                        ChatMessage.role == ChatMessageRole.USER,
                    )
                    .with_for_update()
                )
                if user_message is None:
                    await self.jobs.fail(
                        session,
                        self._as_run(claimed),
                        error_code="PERSONAL_AI_INPUT_UNAVAILABLE",
                        error_message="요청한 Chat 입력을 찾을 수 없습니다.",
                        retryable=False,
                        now=now,
                    )
                    return
                assistant = ChatMessage(
                    chat_id=chat.id,
                    session_id=lecture_session.id,
                    sequence=user_message.sequence + 1,
                    role=ChatMessageRole.ASSISTANT,
                    content=generated.content,
                    created_by_job_id=job.id,
                    created_by_job_attempt=claimed.attempt,
                    model_name=generated.model_name,
                    prompt_version=CHAT_PROMPT_VERSION,
                )
                session.add(assistant)
                await session.flush()
                for rank, result in enumerate(generated.evidence, start=1):
                    projection = await project_evidence(session, chunk=result.chunk)
                    if projection is None:
                        continue
                    session.add(
                        ChatMessageEvidence(
                            chat_message_id=assistant.id,
                            knowledge_chunk_id=result.chunk.id,
                            session_id=lecture_session.id,
                            rank=rank,
                            relevance_score=result.relevance_score,
                            label_snapshot=projection.label,
                        )
                    )
                changed = await self.jobs.succeed(session, self._as_run(claimed), now=now)
                if not changed:
                    raise RuntimeError("private Chat Job fence was lost")

    async def _fail(
        self,
        claimed: _ClaimedPersonalAIWork,
        *,
        code: str,
        message: str,
        retryable: bool,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session = await self._lock_session(session, claimed.session_id)
                if lecture_session is None:
                    return
                if claimed.target_chat_id is not None:
                    await session.scalar(
                        select(ChatSession)
                        .where(ChatSession.id == claimed.target_chat_id)
                        .with_for_update()
                    )
                job = await self._lock_current_job(session, claimed)
                if job is not None:
                    await self.jobs.fail(
                        session,
                        self._as_run(claimed),
                        error_code=code,
                        error_message=message,
                        retryable=retryable,
                        now=now,
                    )

    async def _lock_session(
        self,
        session: AsyncSession,
        session_id: UUID,
    ) -> LectureSession | None:
        return await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )

    async def _lock_current_job(
        self,
        session: AsyncSession,
        claimed: _ClaimedPersonalAIWork,
    ) -> AIJob | None:
        job = await session.scalar(
            select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
        )
        if (
            job is None
            or job.status != AIJobStatus.RUNNING
            or job.attempt != claimed.attempt
            or job.run_token != claimed.run_token
        ):
            return None
        return job

    @staticmethod
    def _job_state_is_current(
        lecture_session: LectureSession,
        job_type: str,
        chat: ChatSession | None,
    ) -> bool:
        if job_type == AIJobType.LIVE_SUMMARY:
            return lecture_session.status == LectureSessionStatus.LIVE
        return chat is not None and (
            (chat.mode == "LIVE" and lecture_session.status == LectureSessionStatus.LIVE)
            or (chat.mode == "REVIEW" and lecture_session.status == LectureSessionStatus.COMPLETED)
        )

    @staticmethod
    def _as_run(claimed: _ClaimedPersonalAIWork) -> ClaimedJob:
        return ClaimedJob(
            job_id=claimed.job_id,
            session_id=claimed.session_id,
            attempt=claimed.attempt,
            run_token=claimed.run_token,
            job_type=claimed.job_type,
        )
