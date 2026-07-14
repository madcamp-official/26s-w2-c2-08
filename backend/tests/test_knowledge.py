"""Integration coverage for scoped KnowledgeChunk indexing and retrieval."""

import asyncio
import base64
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import fitz
import pytest
from sqlalchemy import select

from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.jobs.kernel import JobKernel
from tbd.models.clustering import Answer
from tbd.models.enums import AIJobStatus, AIJobType
from tbd.models.knowledge import KNOWLEDGE_EMBEDDING_DIMENSION, KnowledgeChunk
from tbd.models.materials import LectureMaterial
from tbd.models.questions import AIJob, Question
from tbd.models.sessions import LectureSession
from tbd.models.users import User
from tbd.providers.ai import FakeEmbeddingProvider, FakeProviderBehavior, ProviderUnavailableError
from tbd.providers.stt import STTFinal
from tbd.services.courses import CourseService
from tbd.services.knowledge import (
    KnowledgeIndexingWorker,
    KnowledgeRetrievalService,
    enqueue_knowledge_indexing,
    project_evidence,
)
from tbd.services.live_audio import LiveAudioService
from tbd.services.materials import MaterialProcessingWorker, MaterialService, ValidatedPdf
from tbd.services.sessions import SessionService
from tbd.storage import InMemoryStorage, StorageKey, StorageNamespace, sha256_bytes

pytestmark = pytest.mark.integration


def _settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
        storage_root=tmp_path / "uploads",
        idempotency_response_encryption_key=base64.b64encode(b"i" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"e" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"h" * 32).decode(),
    )


def _pdf_bytes() -> bytes:
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "RAG PDF source text")
        return document.tobytes()
    finally:
        document.close()


async def _seed_sources(
    database_url: str,
    tmp_path: Path,
    storage: InMemoryStorage,
) -> tuple[UUID, UUID, UUID]:
    settings = _settings(database_url, tmp_path)
    codec = settings.course_join_code_codec
    assert codec is not None
    database = create_database(settings)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                professor_id = uuid4()
                session.add(
                    User(
                        id=professor_id,
                        display_name="knowledge professor",
                        primary_email=f"knowledge-{uuid4().hex[:12]}@example.test",
                    )
                )
                course, _ = await CourseService(codec).create(
                    session,
                    user_id=professor_id,
                    title="지식 검색 수업",
                    semester="2026 여름학기",
                )
                lecture_session = await SessionService().create(
                    session,
                    course_id=course.course.id,
                    user_id=professor_id,
                    title="RAG 자료",
                    lecture_date=date(2026, 7, 14),
                )
                await SessionService().start(
                    session,
                    session_id=lecture_session.id,
                    user_id=professor_id,
                )
                content = _pdf_bytes()
                storage_key = StorageKey.new(StorageNamespace.FINAL)
                temporary_key = StorageKey.new(StorageNamespace.TEMPORARY)
                await storage.create_temporary(temporary_key)
                await storage.append(
                    temporary_key,
                    content,
                    expected_offset=0,
                    checksum=sha256_bytes(content),
                )
                await storage.promote(
                    temporary_key,
                    storage_key,
                    expected_sha256=sha256_bytes(content),
                )
                material = await MaterialService().upload(
                    session,
                    session_id=lecture_session.id,
                    user_id=professor_id,
                    validated=ValidatedPdf(
                        original_filename="rag.pdf",
                        content=content,
                        sha256=sha256_bytes(content),
                    ),
                    storage_key=storage_key,
                )
                return course.course.id, lecture_session.id, material.material.id
    finally:
        await database.dispose()


async def _append_transcript_and_answer(
    database_url: str,
    tmp_path: Path,
    session_id: UUID,
    professor_id: UUID,
) -> None:
    settings = _settings(database_url, tmp_path)
    database = create_database(settings)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                audio = LiveAudioService(settings)
                claim = await audio.claim_publisher(
                    session,
                    session_id=session_id,
                    user_id=professor_id,
                    client_stream_id="knowledge-indexing-test",
                    resume_from_sequence=None,
                )
                final = await audio.persist_final(
                    session,
                    session_id=session_id,
                    recording_id=claim.recording_id,
                    result=STTFinal(
                        utterance_id="knowledge-final",
                        audio_sequence_start=0,
                        audio_sequence_end=0,
                        start_ms=0,
                        end_ms=500,
                        text="canonical transcript source text",
                    ),
                )
                assert final is not None
                timestamp = datetime.now(UTC)
                question = Question(
                    session_id=session_id,
                    author_user_id=professor_id,
                    clustering_sequence=1,
                    content="RAG 답변 대상 질문",
                    status="OPEN",
                    reaction_count=0,
                    version=1,
                )
                session.add(question)
                await session.flush()
                session.add(
                    Answer(
                        session_id=session_id,
                        professor_user_id=professor_id,
                        target_question_id=question.id,
                        target_text_snapshot="RAG 답변 대상",
                        status="COMPLETED",
                        text_content="professor answer source text",
                        started_at=timestamp,
                        completed_at=timestamp,
                        version=1,
                    )
                )
                await enqueue_knowledge_indexing(
                    session,
                    session_id=session_id,
                    kernel=JobKernel(),
                )
    finally:
        await database.dispose()


def test_knowledge_worker_indexes_current_sources_and_hides_stale_ones(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    storage = InMemoryStorage()
    course_id, session_id, material_id = asyncio.run(
        _seed_sources(migrated_database_url, tmp_path, storage)
    )
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    try:
        material_worker = MaterialProcessingWorker(database.session_factory, storage)
        assert asyncio.run(material_worker.run_once()) is True

        async def professor_id() -> UUID:
            async with database.session_factory() as session:
                lecture_session = await session.get(LectureSession, session_id)
                assert lecture_session is not None
                return lecture_session.created_by_user_id

        asyncio.run(
            _append_transcript_and_answer(
                migrated_database_url,
                tmp_path,
                session_id,
                asyncio.run(professor_id()),
            )
        )
        worker = KnowledgeIndexingWorker(
            database.session_factory,
            storage,
            FakeEmbeddingProvider(),
        )
        assert asyncio.run(worker.run_once()) is True

        async def read_index() -> tuple[list[KnowledgeChunk], list[AIJob]]:
            async with database.session_factory() as session:
                chunks = list(
                    await session.scalars(
                        select(KnowledgeChunk)
                        .where(KnowledgeChunk.session_id == session_id)
                        .order_by(KnowledgeChunk.created_at)
                    )
                )
                jobs = list(
                    await session.scalars(
                        select(AIJob).where(
                            AIJob.session_id == session_id,
                            AIJob.job_type == AIJobType.KNOWLEDGE_INDEXING,
                        )
                    )
                )
                return chunks, jobs

        chunks, jobs = asyncio.run(read_index())
        assert {
            "RAG PDF source text",
            "canonical transcript source text",
            "professor answer source text",
        } <= {chunk.content for chunk in chunks}
        assert all(len(chunk.embedding) == KNOWLEDGE_EMBEDDING_DIMENSION for chunk in chunks)
        assert all(chunk.embedding_model == "fake-embedding-v1" for chunk in chunks)
        assert any(job.status == AIJobStatus.SUCCEEDED for job in jobs)

        async def retrieve_current() -> tuple[list[object], object | None]:
            async with database.session_factory() as session:
                service = KnowledgeRetrievalService(FakeEmbeddingProvider())
                results = await service.retrieve(
                    session,
                    course_id=course_id,
                    session_id=session_id,
                    query="source",
                )
                material_chunk = next(chunk for chunk in chunks if chunk.material_id == material_id)
                evidence = await project_evidence(session, chunk=material_chunk)
                return results, evidence

        results, evidence = asyncio.run(retrieve_current())
        assert len(results) == len(chunks)
        assert evidence is not None
        assert evidence.source_kind == "MATERIAL"
        assert "storage" not in evidence.link

        async def hide_material_and_transcript() -> list[object]:
            async with database.session_factory() as session:
                async with session.begin():
                    material = await session.get(LectureMaterial, material_id, with_for_update=True)
                    lecture_session = await session.get(
                        LectureSession,
                        session_id,
                        with_for_update=True,
                    )
                    assert material is not None and lecture_session is not None
                    material.detached_at = datetime.now(UTC)
                    lecture_session.canonical_transcript_version_id = None
                service = KnowledgeRetrievalService(FakeEmbeddingProvider())
                return await service.retrieve(
                    session,
                    course_id=course_id,
                    session_id=session_id,
                    query="source",
                )

        hidden = asyncio.run(hide_material_and_transcript())
        assert [result.chunk.answer_id for result in hidden] == [
            next(chunk.answer_id for chunk in chunks if chunk.answer_id is not None)
        ]
    finally:
        asyncio.run(database.dispose())


def test_knowledge_worker_records_safe_provider_failure(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    storage = InMemoryStorage()
    _, session_id, _ = asyncio.run(_seed_sources(migrated_database_url, tmp_path, storage))
    database = create_database(_settings(migrated_database_url, tmp_path))
    try:
        assert (
            asyncio.run(MaterialProcessingWorker(database.session_factory, storage).run_once())
            is True
        )
        worker = KnowledgeIndexingWorker(
            database.session_factory,
            storage,
            FakeEmbeddingProvider(
                behavior=FakeProviderBehavior(failure=ProviderUnavailableError())
            ),
        )
        assert asyncio.run(worker.run_once()) is True

        async def failed_job() -> AIJob:
            async with database.session_factory() as session:
                job = await session.scalar(
                    select(AIJob)
                    .where(
                        AIJob.session_id == session_id,
                        AIJob.job_type == AIJobType.KNOWLEDGE_INDEXING,
                    )
                    .order_by(AIJob.created_at.desc())
                )
                assert job is not None
                return job

        job = asyncio.run(failed_job())
        assert job.status == AIJobStatus.FAILED
        assert job.error_code == "PROVIDER_UNAVAILABLE"
        assert job.retryable is True
        assert "source text" not in (job.error_message or "")
    finally:
        asyncio.run(database.dispose())
