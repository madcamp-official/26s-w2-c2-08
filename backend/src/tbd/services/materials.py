"""PDF Material validation, lifecycle policy, and fenced processing work."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Final
from uuid import UUID

import fitz
from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tbd.jobs.kernel import JobKernel
from tbd.models.enums import AIJobStatus, AIJobType, AIJobVisibility, MaterialProcessingStatus
from tbd.models.materials import LectureMaterial
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession
from tbd.repositories.jobs import ClaimedJob
from tbd.repositories.materials import MaterialRepository
from tbd.services.courses import (
    CourseAccessDeniedError,
    CourseNotFoundError,
    CourseRoleRequiredError,
)
from tbd.storage import Storage, StorageError, StorageKey, StorageNamespace, sha256_bytes

MATERIAL_MAX_COUNT: Final = 10
UPLOAD_CHUNK_BYTES: Final = 64 * 1024
MATERIAL_WORKER_LEASE: Final = timedelta(seconds=60)


class MaterialNotFoundError(Exception):
    """Raised when direct Material access must not reveal its existence."""


class MaterialLimitExceededError(Exception):
    """Raised before the database trigger confirms the active Material cap."""


class MaterialStateConflictError(Exception):
    """Raised when a Session state does not allow the requested Material action."""


class MaterialDeleteConflictError(Exception):
    """Raised when another detach changed the Material after the initial lookup."""


class InvalidMaterialCursorError(Exception):
    """Raised for malformed or incompatible Material cursor values."""


class InvalidPdfError(Exception):
    """Raised when an upload is not a readable, non-empty PDF document."""


class MaterialTooLargeError(Exception):
    """Raised before an upload can consume more than the configured byte cap."""


class MaterialStorageUnavailableError(Exception):
    """Raised with a safe HTTP-facing classification for retryable storage faults."""


@dataclass(frozen=True)
class ValidatedPdf:
    """Validated bytes that can safely be copied to private temporary storage."""

    original_filename: str
    content: bytes
    sha256: str

    @property
    def byte_size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class MaterialUploadResult:
    """The transactionally attached Material and durable processing Job."""

    material: LectureMaterial
    job: AIJob


@dataclass(frozen=True)
class ClaimedMaterialWork:
    """Private, fenced work item produced only after a Material Job is claimed."""

    job_id: UUID
    session_id: UUID
    attempt: int
    run_token: UUID
    material_id: UUID
    storage_key: StorageKey
    material_version: int


def _safe_filename(filename: str | None) -> str:
    normalized = (filename or "").replace("\\", "/")
    name = PurePath(normalized).name.strip().replace("\x00", "")
    name = " ".join(name.split())
    if not name:
        raise InvalidPdfError
    return name


def _display_name(original_filename: str, occupied: set[str]) -> str:
    path = PurePath(original_filename)
    suffix = path.suffix
    stem = path.name[: -len(suffix)] if suffix else path.name
    candidate = path.name
    sequence = 1
    while candidate in occupied:
        candidate = f"{stem} ({sequence}){suffix}"
        sequence += 1
    return candidate


def _page_count(content: bytes) -> int:
    try:
        document = fitz.open(stream=content, filetype="pdf")
        try:
            count = document.page_count
            if count < 1:
                raise InvalidPdfError
            # Loading the first page catches malformed files that declare a page tree but cannot open it.
            document.load_page(0).get_text("text")
            return count
        finally:
            document.close()
    except InvalidPdfError:
        raise
    except Exception as exc:  # PyMuPDF exposes backend-specific parse exceptions.
        raise InvalidPdfError from exc


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        created_at_value, material_id_value = json.loads(raw)
        created_at = datetime.fromisoformat(created_at_value)
        material_id = UUID(material_id_value)
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
        raise InvalidMaterialCursorError from exc
    if created_at.tzinfo is None:
        raise InvalidMaterialCursorError
    return created_at, material_id


def _encode_cursor(material: LectureMaterial) -> str:
    payload = json.dumps(
        [material.created_at.isoformat(), str(material.id)],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


class MaterialService:
    """Apply Course role, Session state, and durable Material lifecycle policies."""

    def __init__(
        self,
        *,
        repository: MaterialRepository | None = None,
        kernel: JobKernel | None = None,
    ) -> None:
        self.repository = repository or MaterialRepository()
        self.kernel = kernel or JobKernel()

    async def validate_upload(
        self,
        upload: UploadFile,
        *,
        max_upload_bytes: int,
    ) -> ValidatedPdf:
        """Bound reads, check declared and actual PDF type, then parse before storage."""

        if upload.content_type != "application/pdf":
            raise InvalidPdfError
        filename = _safe_filename(upload.filename)
        digest = hashlib.sha256()
        buffer = bytearray()
        while True:
            chunk = await upload.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            if len(buffer) + len(chunk) > max_upload_bytes:
                raise MaterialTooLargeError
            buffer.extend(chunk)
            digest.update(chunk)
        content = bytes(buffer)
        if not content.startswith(b"%PDF-"):
            raise InvalidPdfError
        _page_count(content)
        return ValidatedPdf(
            original_filename=filename,
            content=content,
            sha256=digest.hexdigest(),
        )

    async def store_validated_pdf(
        self,
        storage: Storage,
        validated: ValidatedPdf,
        *,
        track: Callable[[StorageKey], None],
        release: Callable[[StorageKey], None],
    ) -> StorageKey:
        """Copy validated bytes through temporary storage and return one private final key."""

        temporary_key = StorageKey.new(StorageNamespace.TEMPORARY)
        final_key = StorageKey.new(StorageNamespace.FINAL)
        try:
            await storage.create_temporary(temporary_key)
            track(temporary_key)
            offset = 0
            while offset < validated.byte_size:
                chunk = validated.content[offset : offset + UPLOAD_CHUNK_BYTES]
                result = await storage.append(
                    temporary_key,
                    chunk,
                    expected_offset=offset,
                    checksum=sha256_bytes(chunk),
                )
                offset = result.confirmed_offset
            promoted = await storage.promote(
                temporary_key,
                final_key,
                expected_sha256=validated.sha256,
            )
        except StorageError as exc:
            raise MaterialStorageUnavailableError from exc
        if promoted.byte_size != validated.byte_size or promoted.sha256 != validated.sha256:
            raise MaterialStorageUnavailableError
        release(temporary_key)
        track(final_key)
        return final_key

    async def upload(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        validated: ValidatedPdf,
        storage_key: StorageKey,
    ) -> MaterialUploadResult:
        """Attach an already-stored PDF and queue its non-blocking processing Job."""

        lecture_session = await self._lock_authorized_session(
            session, session_id=session_id, user_id=user_id, professor_required=True
        )
        if lecture_session.status not in {"READY", "LIVE", "COMPLETED"}:
            raise MaterialStateConflictError
        if await self.repository.active_count(session, lecture_session.id) >= MATERIAL_MAX_COUNT:
            raise MaterialLimitExceededError

        display_name = _display_name(
            validated.original_filename,
            await self.repository.active_display_names(session, lecture_session.id),
        )
        material = LectureMaterial(
            session_id=lecture_session.id,
            uploaded_by_user_id=user_id,
            original_filename=validated.original_filename,
            display_name=display_name,
            mime_type="application/pdf",
            byte_size=validated.byte_size,
            storage_key=storage_key.value,
            processing_status=MaterialProcessingStatus.UPLOADED,
            version=1,
        )
        job = AIJob(
            session_id=lecture_session.id,
            job_type=AIJobType.MATERIAL_PROCESSING,
            visibility=AIJobVisibility.SHARED,
            status=AIJobStatus.PENDING,
            attempt=1,
            version=1,
            target_material_id=material.id,
            blocks_session_completion=False,
            retryable=False,
        )
        try:
            async with session.begin_nested():
                session.add(material)
                await session.flush()
                job.target_material_id = material.id
                await self.kernel.enqueue(session, job)
        except IntegrityError as exc:
            if self._is_material_limit_constraint(exc):
                raise MaterialLimitExceededError from exc
            raise
        return MaterialUploadResult(material=material, job=job)

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[LectureMaterial], str | None]:
        lecture_session = await self.repository.lock_session(session, session_id)
        if lecture_session is None:
            raise CourseNotFoundError
        role = await self.repository.member_role(
            session, course_id=lecture_session.course_id, user_id=user_id
        )
        if role is None:
            raise CourseAccessDeniedError
        after = _decode_cursor(cursor) if cursor else None
        rows = await self.repository.list_active_for_member(
            session,
            session_id=session_id,
            user_id=user_id,
            after=after,
            limit=limit + 1,
        )
        has_next = len(rows) > limit
        items = rows[:limit]
        return items, _encode_cursor(items[-1]) if has_next and items else None

    async def get_for_member(
        self,
        session: AsyncSession,
        *,
        material_id: UUID,
        user_id: UUID,
    ) -> LectureMaterial:
        material = await self.repository.get_active_for_member(
            session, material_id=material_id, user_id=user_id
        )
        if material is None:
            raise MaterialNotFoundError
        return material

    async def detach(
        self,
        session: AsyncSession,
        *,
        material_id: UUID,
        user_id: UUID,
        now: datetime | None = None,
    ) -> StorageKey:
        """Tombstone a Material before scheduling its private object cleanup."""

        candidate = await self.repository.get_active_for_member(
            session, material_id=material_id, user_id=user_id
        )
        if candidate is None:
            raise MaterialNotFoundError
        lecture_session = await self._lock_authorized_session(
            session,
            session_id=candidate.session_id,
            user_id=user_id,
            professor_required=True,
        )
        if lecture_session.status not in {"READY", "LIVE", "COMPLETED"}:
            raise MaterialStateConflictError
        material = await self.repository.lock_active_for_member(
            session, material_id=material_id, user_id=user_id
        )
        if material is None:
            raise MaterialDeleteConflictError
        job = await self.repository.material_job(session, material.id)
        material.detached_at = now or datetime.now(UTC)
        material.version += 1
        if job is not None:
            if job.status in {AIJobStatus.PENDING, AIJobStatus.RUNNING}:
                await self.kernel.cancel(session, job.id, now=material.detached_at)
            elif job.status == AIJobStatus.FAILED:
                job.retryable = False
                job.version += 1
                await session.flush()
        await self.kernel.outbox.enqueue(
            session,
            session_id=material.session_id,
            partition_key=f"session:{material.session_id}",
            event_type="material.cleanup.requested",
            resource_version=material.version,
            payload={"material_id": str(material.id)},
        )
        await session.flush()
        return StorageKey.parse(material.storage_key)

    async def _lock_authorized_session(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        professor_required: bool,
    ) -> LectureSession:
        lecture_session = await self.repository.lock_session(session, session_id)
        if lecture_session is None:
            raise CourseNotFoundError
        course = await self.repository.lock_course(session, lecture_session.course_id)
        if course is None:
            raise CourseNotFoundError
        role = await self.repository.member_role(session, course_id=course.id, user_id=user_id)
        if role is None:
            raise CourseAccessDeniedError
        if professor_required and (role != "PROFESSOR" or course.created_by_user_id != user_id):
            raise CourseRoleRequiredError
        return lecture_session

    @staticmethod
    def _is_material_limit_constraint(error: IntegrityError) -> bool:
        diagnostic = getattr(getattr(error, "orig", None), "diag", None)
        if getattr(diagnostic, "constraint_name", None) == "lecture_materials_active_count_guard":
            return True
        return "lecture_materials_active_count_guard" in str(getattr(error, "orig", error))


class MaterialProcessingWorker:
    """Run one fenced MATERIAL_PROCESSING Job without embedding or RAG work."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: Storage,
        *,
        repository: MaterialRepository | None = None,
        kernel: JobKernel | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.repository = repository or MaterialRepository()
        self.kernel = kernel or JobKernel()

    async def run_once(self, *, now: datetime | None = None) -> bool:
        """Claim, process, and terminally record at most one Material Job."""

        timestamp = now or datetime.now(UTC)
        claimed = await self._claim(timestamp)
        if claimed is None:
            return False
        try:
            metadata = await self.storage.stat(claimed.storage_key)
            content = await self.storage.read_range(
                claimed.storage_key, start=0, end=metadata.byte_size
            )
            page_count = await asyncio.to_thread(_page_count, content)
        except StorageError:
            await self._finish_failure(
                claimed,
                code="MATERIAL_STORAGE_UNAVAILABLE",
                message="강의자료 저장소에 일시적으로 접근할 수 없습니다.",
                retryable=True,
                now=timestamp,
            )
        except InvalidPdfError:
            await self._finish_failure(
                claimed,
                code="MATERIAL_PROCESSING_FAILED",
                message="강의자료를 처리하지 못했습니다.",
                retryable=True,
                now=timestamp,
            )
        else:
            await self._finish_success(claimed, page_count=page_count, now=timestamp)
        return True

    async def _claim(self, now: datetime) -> ClaimedMaterialWork | None:
        async with self.session_factory() as session:
            async with session.begin():
                candidate = await self.repository.next_due_material_job(session, now)
                if candidate is None or candidate.target_material_id is None:
                    return None
                lecture_session = await self.repository.lock_session(session, candidate.session_id)
                if lecture_session is None:
                    return None
                material = await self.repository.lock_material(
                    session, candidate.target_material_id
                )
                run = await self.kernel.claim_shared_by_id(
                    session,
                    candidate.id,
                    now=now,
                    lease_duration=MATERIAL_WORKER_LEASE,
                    job_type=AIJobType.MATERIAL_PROCESSING,
                )
                if run is None:
                    return None
                if material is None or material.detached_at is not None:
                    await self.kernel.cancel(session, run.job_id, now=now)
                    return None
                material.processing_status = MaterialProcessingStatus.PROCESSING
                material.version += 1
                await session.flush()
                return ClaimedMaterialWork(
                    job_id=run.job_id,
                    session_id=run.session_id,
                    attempt=run.attempt,
                    run_token=run.run_token,
                    material_id=material.id,
                    storage_key=StorageKey.parse(material.storage_key),
                    material_version=material.version,
                )

    async def _finish_success(
        self,
        claimed: ClaimedMaterialWork,
        *,
        page_count: int,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                material = await self.repository.lock_material(session, claimed.material_id)
                if not self._is_current(material, claimed):
                    await self.kernel.cancel(session, claimed.job_id, now=now)
                    return
                run = self._as_run(claimed)
                if not await self.kernel.succeed(session, run, now=now):
                    return
                assert material is not None
                material.page_count = page_count
                material.processing_status = MaterialProcessingStatus.READY
                material.processed_by_job_id = claimed.job_id
                material.processed_by_job_attempt = claimed.attempt
                material.version += 1
                await session.flush()

    async def _finish_failure(
        self,
        claimed: ClaimedMaterialWork,
        *,
        code: str,
        message: str,
        retryable: bool,
        now: datetime,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                material = await self.repository.lock_material(session, claimed.material_id)
                if not self._is_current(material, claimed):
                    await self.kernel.cancel(session, claimed.job_id, now=now)
                    return
                run = self._as_run(claimed)
                if not await self.kernel.fail(
                    session,
                    run,
                    error_code=code,
                    error_message=message,
                    retryable=retryable,
                    now=now,
                ):
                    return
                assert material is not None
                material.processing_status = MaterialProcessingStatus.FAILED
                material.version += 1
                await session.flush()

    @staticmethod
    def _is_current(material: LectureMaterial | None, claimed: ClaimedMaterialWork) -> bool:
        return (
            material is not None
            and material.detached_at is None
            and material.version == claimed.material_version
            and material.processing_status == MaterialProcessingStatus.PROCESSING
        )

    @staticmethod
    def _as_run(claimed: ClaimedMaterialWork) -> ClaimedJob:
        return ClaimedJob(
            job_id=claimed.job_id,
            session_id=claimed.session_id,
            attempt=claimed.attempt,
            run_token=claimed.run_token,
            job_type=AIJobType.MATERIAL_PROCESSING,
        )
