"""Recording upload, private playback, and HQ-transcription enqueue policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tbd.auth.security import AuthCrypto
from tbd.core.config import Settings
from tbd.jobs.kernel import JobKernel
from tbd.models.enums import AIJobStatus, AIJobType, AIJobVisibility
from tbd.models.materials import RecordingUpload, SessionRecording, TranscriptVersion
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession
from tbd.repositories.outbox import OutboxRepository
from tbd.repositories.recordings import RecordingRepository
from tbd.schemas.recordings import SessionRecordingResponse
from tbd.services.courses import (
    CourseAccessDeniedError,
    CourseNotFoundError,
    CourseRoleRequiredError,
)
from tbd.services.lifecycle import RECORDING_RETENTION
from tbd.storage import (
    Storage,
    StorageError,
    StorageKey,
    StorageNamespace,
    StorageOffsetMismatchError,
    StorageRangeError,
    StorageReconciler,
    sha256_bytes,
)

RECORDING_UPLOAD_TTL: Final = timedelta(hours=24)
RECORDING_CHUNK_MAX_BYTES: Final = 8 * 1024 * 1024
RECORDING_CONTENT_TYPES: Final = frozenset({"audio/webm", "audio/mp4"})


class RecordingNotFoundError(Exception):
    """Raised when a recording is unavailable to the current Course member."""


class RecordingStateConflictError(Exception):
    """Raised when the recording is not ready for the requested lifecycle action."""


class RecordingNotReadyError(Exception):
    """Raised when a visible Recording has not reached playback availability."""


class UnsupportedRecordingFormatError(Exception):
    """Raised before an unsupported browser recording container reaches storage."""


class RecordingTooLargeError(Exception):
    """Raised before a recording can exceed the configured aggregate byte cap."""


class RecordingPublisherRequiredError(Exception):
    """Raised when a different Course professor attempts to resume an upload."""


class RecordingUploadNotFoundError(Exception):
    """Raised when an upload manifest is unavailable to the initial publisher."""


class RecordingUploadConflictError(Exception):
    """Raised when another active manifest owns the logical recording upload."""


class RecordingUploadExpiredError(Exception):
    """Raised after the documented 24-hour resumable window has elapsed."""

    def __init__(self, temporary_key: StorageKey | None = None) -> None:
        self.temporary_key = temporary_key
        super().__init__("recording upload has expired")


class RecordingOffsetMismatchError(Exception):
    """Raised with the server-confirmed offset required by resumable upload."""

    def __init__(self, offset_bytes: int) -> None:
        self.offset_bytes = offset_bytes
        super().__init__("recording upload offset did not match")


class RecordingChecksumMismatchError(Exception):
    """Raised when one chunk or the final recording digest does not verify."""


class RecordingChunkTooLargeError(Exception):
    """Raised before a browser payload exceeds the bounded PATCH contract."""


class RecordingStorageUnavailableError(Exception):
    """Raised for safe, retryable storage adapter failures."""


class RecordingRangeNotSatisfiableError(Exception):
    """Raised for invalid or unsatisfiable HTTP byte ranges."""


@dataclass(frozen=True)
class RecordingUploadCreated:
    recording: SessionRecording
    upload: RecordingUpload
    replaced_temporary_key: StorageKey | None


@dataclass(frozen=True)
class RecordingUploadPrepared:
    recording: SessionRecording
    upload: RecordingUpload
    final_key: StorageKey


@dataclass(frozen=True)
class RecordingUploadCompleted:
    recording: SessionRecording
    transcript_version: TranscriptVersion
    job: AIJob


def recording_response(recording: SessionRecording) -> SessionRecordingResponse:
    """Project a Recording without ever exposing its storage key or publisher token."""

    return SessionRecordingResponse(
        id=recording.id,
        session_id=recording.session_id,
        status=recording.status,
        content_type=recording.content_type,
        byte_size=recording.byte_size,
        duration_ms=recording.duration_ms,
        version=recording.version,
        playback_url=(
            f"/api/v1/recordings/{recording.id}/playback"
            if recording.status == "UPLOADED" and recording.deleted_at is None
            else None
        ),
        created_at=recording.created_at,
        updated_at=recording.updated_at,
    )


def parse_http_range(value: str | None, *, byte_size: int) -> tuple[int, int] | None:
    """Parse one RFC 7233 byte range into the storage contract's half-open interval."""

    if value is None:
        return None
    if byte_size < 1 or not value.startswith("bytes=") or "," in value:
        raise RecordingRangeNotSatisfiableError
    raw_start, separator, raw_end = value[6:].strip().partition("-")
    if not separator:
        raise RecordingRangeNotSatisfiableError
    try:
        if not raw_start:
            length = int(raw_end)
            if length <= 0:
                raise ValueError
            start = max(0, byte_size - length)
            return start, byte_size
        start = int(raw_start)
        if start < 0 or start >= byte_size:
            raise ValueError
        if not raw_end:
            return start, byte_size
        end_inclusive = int(raw_end)
        if end_inclusive < start:
            raise ValueError
        return start, min(end_inclusive + 1, byte_size)
    except ValueError as exc:
        raise RecordingRangeNotSatisfiableError from exc


class RecordingService:
    """Keep recording authorization, resumable offsets, and finalization transactional."""

    def __init__(
        self,
        settings: Settings,
        *,
        repository: RecordingRepository | None = None,
        outbox: OutboxRepository | None = None,
        kernel: JobKernel | None = None,
    ) -> None:
        self.repository = repository or RecordingRepository()
        self.outbox = outbox or OutboxRepository()
        self.kernel = kernel or JobKernel(outbox=self.outbox)
        self._crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())

    async def get_for_member(
        self,
        session: AsyncSession,
        *,
        recording_id: UUID,
        user_id: UUID,
    ) -> SessionRecording:
        recording = await self.repository.get_recording_for_member(
            session, recording_id=recording_id, user_id=user_id
        )
        if recording is None or recording.deleted_at is not None:
            raise RecordingNotFoundError
        return recording

    async def get_for_session_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> SessionRecording:
        lecture_session = await self.repository.get_session(session, session_id)
        if lecture_session is None:
            raise CourseNotFoundError
        role = await self.repository.member_role(
            session, course_id=lecture_session.course_id, user_id=user_id
        )
        if role is None:
            raise CourseAccessDeniedError
        recording = await self.repository.get_recording_for_session(session, session_id=session_id)
        if recording is None or recording.deleted_at is not None:
            raise RecordingNotFoundError
        return recording

    async def abandon_local_upload(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> SessionRecording:
        """Terminalize the HQ source when the publisher has no usable browser recording."""

        lecture_session, recording = await self._lock_recording_context(
            session, session_id=session_id, user_id=user_id
        )
        if recording.publisher_user_id != user_id:
            raise RecordingPublisherRequiredError
        if lecture_session.status != "PROCESSING":
            raise RecordingStateConflictError
        if recording.status == "FAILED":
            return recording
        if recording.status != "UPLOAD_PENDING":
            raise RecordingStateConflictError
        if await self.repository.lock_active_upload(session, recording_id=recording.id):
            raise RecordingUploadConflictError

        recording.status = "FAILED"
        recording.failed_at = now
        recording.live_audio_lease_expires_at = None
        recording.version += 1
        await session.flush()
        await self._emit_recording_updated(session, recording)
        return recording

    async def create_upload(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        client_stream_id: str,
        content_type: str,
        total_bytes: int,
        duration_ms: int,
        temporary_key: StorageKey,
        max_upload_bytes: int,
        now: datetime,
    ) -> RecordingUploadCreated:
        if content_type not in RECORDING_CONTENT_TYPES:
            raise UnsupportedRecordingFormatError
        if total_bytes > max_upload_bytes:
            raise RecordingTooLargeError
        lecture_session, recording = await self._lock_recording_context(
            session, session_id=session_id, user_id=user_id
        )
        self._require_initial_publisher(
            recording, user_id=user_id, client_stream_id=client_stream_id
        )
        if lecture_session.status not in {"PROCESSING", "COMPLETED"}:
            raise RecordingStateConflictError
        if recording.status not in {"UPLOAD_PENDING", "UPLOADING", "FAILED"}:
            raise RecordingStateConflictError

        replaced_temporary_key: StorageKey | None = None
        active = await self.repository.lock_active_upload(session, recording_id=recording.id)
        if active is not None:
            if active.expires_at > now:
                raise RecordingUploadConflictError
            active.status = "EXPIRED"
            active.terminal_at = now
            active.version += 1
            replaced_temporary_key = StorageKey.parse(active.temporary_storage_key)

        upload = RecordingUpload(
            recording_id=recording.id,
            initiated_by_user_id=user_id,
            status="ACTIVE",
            offset_bytes=0,
            total_bytes=total_bytes,
            declared_content_type=content_type,
            declared_duration_ms=duration_ms,
            temporary_storage_key=temporary_key.value,
            expires_at=now + RECORDING_UPLOAD_TTL,
            version=1,
        )
        session.add(upload)
        recording.status = "UPLOADING"
        recording.failed_at = None
        recording.version += 1
        await session.flush()
        await self._emit_recording_updated(session, recording)
        return RecordingUploadCreated(
            recording=recording,
            upload=upload,
            replaced_temporary_key=replaced_temporary_key,
        )

    async def get_upload_for_publisher(
        self,
        session: AsyncSession,
        *,
        upload_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> RecordingUpload:
        _, recording, upload = await self._lock_upload_context(
            session, upload_id=upload_id, user_id=user_id
        )
        await self._require_upload_active(session, recording=recording, upload=upload, now=now)
        if recording.status != "UPLOADING":
            raise RecordingStateConflictError
        return upload

    async def expire_upload_if_due(
        self,
        session: AsyncSession,
        *,
        upload_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> StorageKey | None:
        """Terminally expire only an active manifest without affecting a completed replay."""

        _, recording, upload = await self._lock_upload_context(
            session, upload_id=upload_id, user_id=user_id
        )
        if upload.status != "ACTIVE" or upload.expires_at > now:
            return None
        try:
            await self._require_upload_active(session, recording=recording, upload=upload, now=now)
        except RecordingUploadExpiredError as exc:
            return exc.temporary_key
        raise AssertionError("an expired active upload must transition to EXPIRED")

    async def append_chunk(
        self,
        session: AsyncSession,
        *,
        upload_id: UUID,
        user_id: UUID,
        offset_bytes: int,
        checksum: str,
        content: bytes,
        storage: Storage,
        now: datetime,
    ) -> RecordingUpload:
        if len(content) > RECORDING_CHUNK_MAX_BYTES:
            raise RecordingChunkTooLargeError
        _, recording, upload = await self._lock_upload_context(
            session, upload_id=upload_id, user_id=user_id
        )
        await self._require_upload_active(session, recording=recording, upload=upload, now=now)
        if recording.status != "UPLOADING":
            raise RecordingStateConflictError
        if offset_bytes != upload.offset_bytes:
            raise RecordingOffsetMismatchError(upload.offset_bytes)
        if offset_bytes + len(content) > upload.total_bytes:
            raise RecordingOffsetMismatchError(upload.offset_bytes)
        if sha256_bytes(content) != checksum:
            raise RecordingChecksumMismatchError

        temporary_key = StorageKey.parse(upload.temporary_storage_key)
        try:
            metadata = await storage.stat(temporary_key)
            if metadata.byte_size != upload.offset_bytes:
                if metadata.byte_size > upload.total_bytes:
                    raise RecordingStorageUnavailableError
                upload.offset_bytes = metadata.byte_size
                upload.version += 1
                raise RecordingOffsetMismatchError(upload.offset_bytes)
            result = await storage.append(
                temporary_key,
                content,
                expected_offset=offset_bytes,
                checksum=checksum,
            )
        except RecordingOffsetMismatchError:
            raise
        except StorageOffsetMismatchError as exc:
            upload.offset_bytes = exc.actual_offset
            upload.version += 1
            raise RecordingOffsetMismatchError(exc.actual_offset) from exc
        except (StorageError, ValueError) as exc:
            raise RecordingStorageUnavailableError from exc
        upload.offset_bytes = result.confirmed_offset
        upload.version += 1
        await session.flush()
        return upload

    async def prepare_completion(
        self,
        session: AsyncSession,
        *,
        upload_id: UUID,
        user_id: UUID,
        sha256: str,
        storage: Storage,
        now: datetime,
    ) -> RecordingUploadPrepared:
        _, recording, upload = await self._lock_upload_context(
            session, upload_id=upload_id, user_id=user_id
        )
        await self._require_upload_active(session, recording=recording, upload=upload, now=now)
        if recording.status != "UPLOADING":
            raise RecordingStateConflictError
        if upload.offset_bytes != upload.total_bytes:
            raise RecordingOffsetMismatchError(upload.offset_bytes)
        try:
            metadata = await storage.stat(StorageKey.parse(upload.temporary_storage_key))
        except (StorageError, ValueError) as exc:
            raise RecordingStorageUnavailableError from exc
        if metadata.byte_size != upload.total_bytes:
            upload.offset_bytes = metadata.byte_size
            upload.version += 1
            raise RecordingOffsetMismatchError(metadata.byte_size)
        if metadata.sha256 != sha256:
            raise RecordingChecksumMismatchError
        return RecordingUploadPrepared(
            recording=recording,
            upload=upload,
            final_key=StorageKey.new(StorageNamespace.FINAL),
        )

    async def complete_upload(
        self,
        session: AsyncSession,
        *,
        prepared: RecordingUploadPrepared,
        now: datetime,
    ) -> RecordingUploadCompleted:
        recording = prepared.recording
        upload = prepared.upload
        recording.status = "UPLOADED"
        recording.content_type = upload.declared_content_type
        recording.byte_size = upload.total_bytes
        recording.duration_ms = upload.declared_duration_ms
        recording.storage_key = prepared.final_key.value
        recording.uploaded_at = now
        lecture_session = await self.repository.get_session(session, recording.session_id)
        if lecture_session is not None and lecture_session.completed_at is not None:
            recording.retention_expires_at = lecture_session.completed_at + RECORDING_RETENTION
        recording.failed_at = None
        recording.version += 1
        upload.status = "COMPLETED"
        upload.terminal_at = now
        upload.version += 1

        job = AIJob(
            session_id=recording.session_id,
            job_type=AIJobType.RECORDING_TRANSCRIPTION,
            visibility=AIJobVisibility.SHARED,
            status=AIJobStatus.PENDING,
            attempt=1,
            version=1,
            target_recording_id=recording.id,
            blocks_session_completion=True,
            retryable=False,
        )
        await self.kernel.enqueue(session, job)
        transcript_version = TranscriptVersion(
            session_id=recording.session_id,
            version=await self.repository.next_transcript_version(
                session, session_id=recording.session_id
            ),
            source="RECORDING",
            status="FINALIZING",
            recording_id=recording.id,
            created_by_job_id=job.id,
            created_by_job_attempt=job.attempt,
            last_sequence=0,
        )
        session.add(transcript_version)
        await session.flush()
        await self._emit_recording_updated(session, recording)
        return RecordingUploadCompleted(
            recording=recording,
            transcript_version=transcript_version,
            job=job,
        )

    async def playback(
        self,
        session: AsyncSession,
        *,
        recording_id: UUID,
        user_id: UUID,
        byte_range: str | None,
        storage: Storage,
    ) -> tuple[SessionRecording, bytes, int, int, int]:
        recording = await self.get_for_member(session, recording_id=recording_id, user_id=user_id)
        if (
            recording.deleted_at is not None
            or recording.status != "UPLOADED"
            or recording.storage_key is None
        ):
            raise RecordingNotReadyError
        try:
            key = StorageKey.parse(recording.storage_key)
            metadata = await storage.stat(key)
            requested_range = parse_http_range(byte_range, byte_size=metadata.byte_size)
            start, end = requested_range or (0, metadata.byte_size)
            content = await storage.read_range(key, start=start, end=end)
        except RecordingRangeNotSatisfiableError:
            raise
        except (StorageRangeError, ValueError) as exc:
            raise RecordingRangeNotSatisfiableError from exc
        except StorageError as exc:
            raise RecordingStorageUnavailableError from exc
        return recording, content, start, end, metadata.byte_size

    async def find_storage_orphans(
        self,
        session: AsyncSession,
        *,
        storage: Storage,
        now: datetime,
    ) -> tuple[StorageKey, ...]:
        """Discover unreferenced recording objects without performing deletion.

        PR-28 owns deletion ledger persistence and quota release.  Keeping this
        operation read-only makes storage failures and operator reconciliation
        observable now without bypassing that later lifecycle boundary.
        """

        values = await self.repository.referenced_storage_values(session, now=now)
        keys = tuple(StorageKey.parse(value) for value in values)
        return await StorageReconciler(storage).find_orphans(keys)

    async def _lock_recording_context(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> tuple[LectureSession, SessionRecording]:
        lecture_session = await self.repository.lock_session(session, session_id)
        if lecture_session is None:
            raise CourseNotFoundError
        role = await self.repository.member_role(
            session, course_id=lecture_session.course_id, user_id=user_id
        )
        if role is None:
            raise CourseAccessDeniedError
        if role != "PROFESSOR":
            raise CourseRoleRequiredError
        recording = await self.repository.lock_recording_for_session(session, session_id=session_id)
        if recording is None:
            raise RecordingNotFoundError
        return lecture_session, recording

    async def _lock_upload_context(
        self,
        session: AsyncSession,
        *,
        upload_id: UUID,
        user_id: UUID,
    ) -> tuple[LectureSession, SessionRecording, RecordingUpload]:
        preview = await self.repository.get_upload(session, upload_id)
        if preview is None:
            raise RecordingUploadNotFoundError
        # Read just enough to establish the aggregate's Session before taking
        # locks.  From there every mutable path follows Session → Recording →
        # Upload, and rechecks the relationship after locking.
        recording_preview = await self.repository.get_recording(session, preview.recording_id)
        if recording_preview is None:
            raise RecordingUploadNotFoundError
        lecture_session = await self.repository.lock_session(session, recording_preview.session_id)
        if lecture_session is None:
            raise RecordingUploadNotFoundError
        role = await self.repository.member_role(
            session, course_id=lecture_session.course_id, user_id=user_id
        )
        if role is None:
            raise RecordingUploadNotFoundError
        if role != "PROFESSOR":
            raise CourseRoleRequiredError
        recording = await self.repository.lock_recording_for_session(
            session, session_id=lecture_session.id
        )
        upload = await self.repository.lock_upload(session, upload_id=upload_id)
        if recording is None or upload is None or upload.recording_id != recording.id:
            raise RecordingUploadNotFoundError
        if upload.initiated_by_user_id != user_id or recording.publisher_user_id != user_id:
            raise RecordingPublisherRequiredError
        return lecture_session, recording, upload

    def _require_initial_publisher(
        self,
        recording: SessionRecording,
        *,
        user_id: UUID,
        client_stream_id: str,
    ) -> None:
        stream_hash = self._crypto.hash_token("live-audio-publisher", client_stream_id)
        if (
            recording.publisher_user_id != user_id
            or recording.publisher_client_stream_id_hash != stream_hash
        ):
            raise RecordingPublisherRequiredError

    async def _require_upload_active(
        self,
        session: AsyncSession,
        *,
        recording: SessionRecording,
        upload: RecordingUpload,
        now: datetime,
    ) -> None:
        if upload.status != "ACTIVE":
            raise RecordingUploadNotFoundError
        if upload.expires_at <= now:
            upload.status = "EXPIRED"
            upload.terminal_at = now
            upload.version += 1
            if recording.status == "UPLOADING":
                recording.status = "UPLOAD_PENDING"
                recording.version += 1
                await self._emit_recording_updated(session, recording)
            raise RecordingUploadExpiredError(StorageKey.parse(upload.temporary_storage_key))

    async def _emit_recording_updated(
        self, session: AsyncSession, recording: SessionRecording
    ) -> None:
        await self.outbox.enqueue(
            session,
            session_id=recording.session_id,
            partition_key=f"session:{recording.session_id}",
            event_type="recording.updated",
            resource_version=recording.version,
            payload=recording_response(recording).model_dump(mode="json"),
        )
