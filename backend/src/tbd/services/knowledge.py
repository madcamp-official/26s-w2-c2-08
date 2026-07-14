"""Scoped KnowledgeChunk indexing, retrieval, and safe evidence projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

import fitz
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tbd.jobs.kernel import JobKernel
from tbd.models.clustering import Answer
from tbd.models.enums import AIJobStatus, AIJobType, AIJobVisibility, MaterialProcessingStatus
from tbd.models.knowledge import KNOWLEDGE_EMBEDDING_DIMENSION, KnowledgeChunk
from tbd.models.materials import LectureMaterial, TranscriptSegment
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession
from tbd.providers.ai import (
    AIProviderError,
    EmbeddingProvider,
    EmbeddingRequest,
    ProviderInvalidResponseError,
)
from tbd.repositories.jobs import ClaimedJob
from tbd.storage import Storage, StorageError, StorageKey

KNOWLEDGE_CHUNK_MAX_CHARS = 1000
KNOWLEDGE_EMBEDDING_TIMEOUT = timedelta(seconds=5)
KNOWLEDGE_INDEXING_LEASE = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class EvidenceProjection:
    """A public evidence label and REST recovery link without internal storage data."""

    source_kind: str
    label: str
    link: str | None


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    """Internal ranked retrieval value for a later Chat or Summary service."""

    chunk: KnowledgeChunk
    relevance_score: float


@dataclass(frozen=True, slots=True)
class _IndexCandidate:
    """Private snapshot of one source span while it is sent to the provider."""

    course_id: UUID
    session_id: UUID
    content: str
    chunk_index: int
    material_id: UUID | None = None
    page_number: int | None = None
    source_transcript_version_id: UUID | None = None
    transcript_start_segment_id: UUID | None = None
    transcript_end_segment_id: UUID | None = None
    answer_id: UUID | None = None

    @property
    def token_count(self) -> int:
        return len(self.content.split())


@dataclass(frozen=True, slots=True)
class _ClaimedKnowledgeWork:
    job_id: UUID
    session_id: UUID
    attempt: int
    run_token: UUID


def split_knowledge_text(
    text: str, *, max_chars: int = KNOWLEDGE_CHUNK_MAX_CHARS
) -> tuple[str, ...]:
    """Split normalized text at whitespace while keeping each chunk bounded.

    The indexing contract deliberately uses a character limit rather than a
    model-specific tokenizer, so every supported embedding provider sees the
    same durable source boundaries.
    """

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    normalized = " ".join(text.split())
    if not normalized:
        return ()

    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > max_chars:
        boundary = remaining.rfind(" ", 0, max_chars + 1)
        if boundary <= 0:
            boundary = max_chars
        chunk = remaining[:boundary].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[boundary:].lstrip()
    if remaining:
        chunks.append(remaining)
    return tuple(chunks)


async def enqueue_knowledge_indexing(
    session: AsyncSession,
    *,
    session_id: UUID,
    kernel: JobKernel,
) -> AIJob | None:
    """Create at most one active session-wide indexing Job under its row lock."""

    lecture_session = await session.scalar(
        select(LectureSession).where(LectureSession.id == session_id).with_for_update()
    )
    if lecture_session is None:
        return None
    active = await session.scalar(
        select(AIJob)
        .where(
            AIJob.session_id == session_id,
            AIJob.job_type == AIJobType.KNOWLEDGE_INDEXING,
            AIJob.status.in_((AIJobStatus.PENDING, AIJobStatus.RUNNING)),
        )
        .with_for_update()
    )
    if active is not None:
        return active
    return await kernel.enqueue(
        session,
        AIJob(
            session_id=session_id,
            job_type=AIJobType.KNOWLEDGE_INDEXING,
            visibility=AIJobVisibility.SHARED,
            status=AIJobStatus.PENDING,
            attempt=1,
            version=1,
            blocks_session_completion=False,
            retryable=False,
        ),
    )


class KnowledgeIndexingWorker:
    """Index current Material, canonical Transcript, and completed text Answers."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: Storage,
        provider: EmbeddingProvider,
        *,
        kernel: JobKernel | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.provider = provider
        self.kernel = kernel or JobKernel()

    async def run_once(self, *, now: datetime | None = None) -> bool:
        """Claim, embed, and persist one fenced session-wide indexing Job."""

        timestamp = now or datetime.now(UTC)
        claimed = await self._claim(timestamp)
        if claimed is None:
            return False
        try:
            candidates = await self._collect_candidates(claimed.session_id)
            if candidates:
                result = await self.provider.embed(
                    EmbeddingRequest(
                        purpose="knowledge-indexing-v1",
                        texts=tuple(candidate.content for candidate in candidates),
                    ),
                    timeout=KNOWLEDGE_EMBEDDING_TIMEOUT,
                )
                if (
                    len(result.vectors) != len(candidates)
                    or result.dimension != KNOWLEDGE_EMBEDDING_DIMENSION
                ):
                    raise ProviderInvalidResponseError
                model_name = result.model_name or "unknown-embedding-model"
                vectors = tuple(tuple(vector) for vector in result.vectors)
            else:
                model_name = "fake-embedding-v1"
                vectors = ()
        except StorageError:
            await self._fail(
                claimed,
                code="KNOWLEDGE_STORAGE_UNAVAILABLE",
                message="지식 자료 저장소에 일시적으로 접근할 수 없습니다.",
                retryable=True,
                now=timestamp,
            )
        except AIProviderError as exc:
            await self._fail(
                claimed,
                code=str(exc.code),
                message="지식 색인 AI 제공자를 사용할 수 없습니다.",
                retryable=exc.retryable,
                now=timestamp,
            )
        except (ValueError, fitz.FileDataError):
            await self._fail(
                claimed,
                code="KNOWLEDGE_SOURCE_INVALID",
                message="지식 색인 자료를 처리하지 못했습니다.",
                retryable=False,
                now=timestamp,
            )
        else:
            await self._succeed(claimed, candidates, vectors, model_name, timestamp)
        return True

    async def _claim(self, now: datetime) -> _ClaimedKnowledgeWork | None:
        async with self.session_factory() as session:
            async with session.begin():
                run = await self.kernel.claim_next_shared(
                    session,
                    now=now,
                    lease_duration=KNOWLEDGE_INDEXING_LEASE,
                    job_type=AIJobType.KNOWLEDGE_INDEXING,
                )
                if run is None:
                    return None
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == run.session_id)
                    .with_for_update()
                )
                if lecture_session is None:
                    await self.kernel.cancel(session, run.job_id, now=now)
                    return None
                return _ClaimedKnowledgeWork(
                    job_id=run.job_id,
                    session_id=run.session_id,
                    attempt=run.attempt,
                    run_token=run.run_token,
                )

    async def _collect_candidates(self, session_id: UUID) -> tuple[_IndexCandidate, ...]:
        async with self.session_factory() as session:
            lecture_session = await session.get(LectureSession, session_id)
            if lecture_session is None:
                return ()
            candidates = [
                *await self._material_candidates(session, lecture_session),
                *await self._transcript_candidates(session, lecture_session),
                *await self._answer_candidates(session, lecture_session),
            ]
            return tuple(candidates)

    async def _material_candidates(
        self,
        session: AsyncSession,
        lecture_session: LectureSession,
    ) -> list[_IndexCandidate]:
        materials = list(
            await session.scalars(
                select(LectureMaterial)
                .where(
                    LectureMaterial.session_id == lecture_session.id,
                    LectureMaterial.processing_status == MaterialProcessingStatus.READY,
                    LectureMaterial.detached_at.is_(None),
                )
                .order_by(LectureMaterial.created_at, LectureMaterial.id)
            )
        )
        candidates: list[_IndexCandidate] = []
        for material in materials:
            already_indexed = set(
                await session.scalars(
                    select(KnowledgeChunk.page_number).where(
                        KnowledgeChunk.material_id == material.id
                    )
                )
            )
            metadata = await self.storage.stat(StorageKey.parse(material.storage_key))
            content = await self.storage.read_range(
                StorageKey.parse(material.storage_key), start=0, end=metadata.byte_size
            )
            document = fitz.open(stream=content, filetype="pdf")
            try:
                for page_offset, page in enumerate(document):
                    page_number = page_offset + 1
                    if page_number in already_indexed:
                        continue
                    for chunk_index, chunk in enumerate(
                        split_knowledge_text(page.get_text("text"))
                    ):
                        candidates.append(
                            _IndexCandidate(
                                course_id=lecture_session.course_id,
                                session_id=lecture_session.id,
                                material_id=material.id,
                                page_number=page_number,
                                content=chunk,
                                chunk_index=chunk_index,
                            )
                        )
            finally:
                document.close()
        return candidates

    async def _transcript_candidates(
        self,
        session: AsyncSession,
        lecture_session: LectureSession,
    ) -> list[_IndexCandidate]:
        if lecture_session.canonical_transcript_version_id is None:
            return []
        existing = set(
            await session.scalars(
                select(KnowledgeChunk.transcript_start_segment_id).where(
                    KnowledgeChunk.source_transcript_version_id
                    == lecture_session.canonical_transcript_version_id
                )
            )
        )
        segments = list(
            await session.scalars(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.transcript_version_id
                    == lecture_session.canonical_transcript_version_id
                )
                .order_by(TranscriptSegment.sequence)
            )
        )
        return [
            _IndexCandidate(
                course_id=lecture_session.course_id,
                session_id=lecture_session.id,
                source_transcript_version_id=lecture_session.canonical_transcript_version_id,
                transcript_start_segment_id=segment.id,
                transcript_end_segment_id=segment.id,
                content=segment.text,
                chunk_index=0,
            )
            for segment in segments
            if segment.id not in existing
        ]

    async def _answer_candidates(
        self,
        session: AsyncSession,
        lecture_session: LectureSession,
    ) -> list[_IndexCandidate]:
        existing = set(
            await session.scalars(
                select(KnowledgeChunk.answer_id).where(
                    KnowledgeChunk.session_id == lecture_session.id
                )
            )
        )
        answers = list(
            await session.scalars(
                select(Answer)
                .where(
                    Answer.session_id == lecture_session.id,
                    Answer.status == "COMPLETED",
                    Answer.text_content.is_not(None),
                )
                .order_by(Answer.completed_at, Answer.id)
            )
        )
        return [
            _IndexCandidate(
                course_id=lecture_session.course_id,
                session_id=lecture_session.id,
                answer_id=answer.id,
                content=content,
                chunk_index=index,
            )
            for answer in answers
            if answer.id not in existing
            for index, content in enumerate(split_knowledge_text(answer.text_content or ""))
        ]

    async def _succeed(
        self,
        claimed: _ClaimedKnowledgeWork,
        candidates: tuple[_IndexCandidate, ...],
        vectors: tuple[tuple[float, ...], ...],
        model_name: str,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                lecture_session = await session.scalar(
                    select(LectureSession)
                    .where(LectureSession.id == claimed.session_id)
                    .with_for_update()
                )
                job = await session.scalar(
                    select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
                )
                if lecture_session is None or not self._is_current(job, claimed):
                    return
                for candidate, vector in zip(candidates, vectors, strict=True):
                    if not await self._source_is_current(session, lecture_session, candidate):
                        continue
                    await session.execute(
                        insert(KnowledgeChunk)
                        .values(
                            course_id=candidate.course_id,
                            session_id=candidate.session_id,
                            material_id=candidate.material_id,
                            source_transcript_version_id=candidate.source_transcript_version_id,
                            transcript_start_segment_id=candidate.transcript_start_segment_id,
                            transcript_end_segment_id=candidate.transcript_end_segment_id,
                            answer_id=candidate.answer_id,
                            chunk_index=candidate.chunk_index,
                            page_number=candidate.page_number,
                            content=candidate.content,
                            token_count=candidate.token_count,
                            embedding=list(vector),
                            embedding_model=model_name,
                            created_by_job_id=claimed.job_id,
                            created_by_job_attempt=claimed.attempt,
                        )
                        .on_conflict_do_nothing()
                    )
                await self.kernel.succeed(session, self._as_run(claimed), now=now)

    async def _source_is_current(
        self,
        session: AsyncSession,
        lecture_session: LectureSession,
        candidate: _IndexCandidate,
    ) -> bool:
        if candidate.material_id is not None:
            return (
                await session.scalar(
                    select(LectureMaterial.id).where(
                        LectureMaterial.id == candidate.material_id,
                        LectureMaterial.session_id == lecture_session.id,
                        LectureMaterial.processing_status == MaterialProcessingStatus.READY,
                        LectureMaterial.detached_at.is_(None),
                    )
                )
                is not None
            )
        if candidate.source_transcript_version_id is not None:
            return (
                lecture_session.canonical_transcript_version_id
                == candidate.source_transcript_version_id
            )
        if candidate.answer_id is not None:
            answer_text = await session.scalar(
                select(Answer.text_content).where(
                    Answer.id == candidate.answer_id,
                    Answer.session_id == lecture_session.id,
                    Answer.status == "COMPLETED",
                    Answer.text_content.is_not(None),
                )
            )
            chunks = split_knowledge_text(answer_text or "")
            return (
                candidate.chunk_index < len(chunks)
                and chunks[candidate.chunk_index] == candidate.content
            )
        return False

    async def _fail(
        self,
        claimed: _ClaimedKnowledgeWork,
        *,
        code: str,
        message: str,
        retryable: bool,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(AIJob).where(AIJob.id == claimed.job_id).with_for_update()
                )
                if self._is_current(job, claimed):
                    await self.kernel.fail(
                        session,
                        self._as_run(claimed),
                        error_code=code,
                        error_message=message,
                        retryable=retryable,
                        now=now,
                    )

    @staticmethod
    def _is_current(job: AIJob | None, claimed: _ClaimedKnowledgeWork) -> bool:
        return (
            job is not None
            and job.status == AIJobStatus.RUNNING
            and job.attempt == claimed.attempt
            and job.run_token == claimed.run_token
        )

    @staticmethod
    def _as_run(claimed: _ClaimedKnowledgeWork) -> ClaimedJob:
        return ClaimedJob(
            job_id=claimed.job_id,
            session_id=claimed.session_id,
            attempt=claimed.attempt,
            run_token=claimed.run_token,
            job_type=AIJobType.KNOWLEDGE_INDEXING,
        )


class KnowledgeRetrievalService:
    """Scope vector retrieval in SQL before a caller creates public Evidence."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    async def retrieve(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        session_id: UUID,
        query: str,
        limit: int = 8,
    ) -> list[KnowledgeSearchResult]:
        if not query.strip() or not 1 <= limit <= 100:
            raise ValueError("query and limit must be valid")
        embedded = await self.provider.embed(
            EmbeddingRequest(purpose="knowledge-retrieval-v1", texts=(query.strip(),)),
            timeout=KNOWLEDGE_EMBEDDING_TIMEOUT,
        )
        if embedded.dimension != KNOWLEDGE_EMBEDDING_DIMENSION:
            raise ProviderInvalidResponseError
        distance = KnowledgeChunk.embedding.cosine_distance(list(embedded.vectors[0]))
        material_is_visible = and_(
            KnowledgeChunk.material_id.is_not(None),
            LectureMaterial.processing_status == MaterialProcessingStatus.READY,
            LectureMaterial.detached_at.is_(None),
        )
        transcript_is_visible = and_(
            KnowledgeChunk.source_transcript_version_id.is_not(None),
            KnowledgeChunk.source_transcript_version_id
            == LectureSession.canonical_transcript_version_id,
        )
        answer_is_visible = and_(
            KnowledgeChunk.answer_id.is_not(None),
            Answer.status == "COMPLETED",
            Answer.text_content.is_not(None),
        )
        rows = await session.execute(
            select(KnowledgeChunk, distance.label("distance"))
            .join(LectureSession, LectureSession.id == KnowledgeChunk.session_id)
            .outerjoin(LectureMaterial, LectureMaterial.id == KnowledgeChunk.material_id)
            .outerjoin(Answer, Answer.id == KnowledgeChunk.answer_id)
            .where(
                KnowledgeChunk.course_id == course_id,
                KnowledgeChunk.session_id == session_id,
                or_(material_is_visible, transcript_is_visible, answer_is_visible),
            )
            .order_by(distance, KnowledgeChunk.id)
            .limit(limit)
        )
        return [
            KnowledgeSearchResult(chunk=row[0], relevance_score=1 - float(row[1])) for row in rows
        ]


async def project_evidence(
    session: AsyncSession,
    *,
    chunk: KnowledgeChunk,
) -> EvidenceProjection | None:
    """Resolve a current, user-safe source label for an already scoped chunk."""

    if chunk.material_id is not None:
        material = await session.get(LectureMaterial, chunk.material_id)
        if (
            material is None
            or material.processing_status != MaterialProcessingStatus.READY
            or material.detached_at is not None
        ):
            return None
        page_label = f" {chunk.page_number}쪽" if chunk.page_number is not None else ""
        fragment = f"#page={chunk.page_number}" if chunk.page_number is not None else ""
        return EvidenceProjection(
            source_kind="MATERIAL",
            label=f"{material.display_name}{page_label}",
            link=f"/api/v1/materials/{material.id}/content{fragment}",
        )
    if chunk.source_transcript_version_id is not None:
        lecture_session = await session.get(LectureSession, chunk.session_id)
        if (
            lecture_session is None
            or lecture_session.canonical_transcript_version_id != chunk.source_transcript_version_id
        ):
            return None
        start = await session.get(TranscriptSegment, chunk.transcript_start_segment_id)
        end = await session.get(TranscriptSegment, chunk.transcript_end_segment_id)
        if start is None or end is None:
            return None
        query = urlencode(
            {
                "transcript_version_id": str(chunk.source_transcript_version_id),
                "start_sequence": start.sequence,
                "end_sequence": end.sequence,
            }
        )
        return EvidenceProjection(
            source_kind="TRANSCRIPT",
            label=f"강의 내용 {start.start_ms // 1000}~{end.end_ms // 1000}초",
            link=f"/api/v1/sessions/{chunk.session_id}/transcript?{query}",
        )
    if chunk.answer_id is not None:
        answer = await session.get(Answer, chunk.answer_id)
        if answer is None or answer.status != "COMPLETED" or answer.text_content is None:
            return None
        return EvidenceProjection(
            source_kind="ANSWER",
            label="교수자 답변",
            link=f"/api/v1/answers/{answer.id}",
        )
    return None
