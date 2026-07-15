"""Course-authorized recording metadata, resumable upload, and Range playback."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_current_user_id,
    get_db_session,
    get_optional_idempotency_repository,
    get_settings,
    get_storage,
    require_allowed_origin,
)
from tbd.core.config import Settings
from tbd.core.errors import ApiError
from tbd.core.request_hash import canonical_request_hash, idempotency_key_hash
from tbd.db import transaction
from tbd.repositories.idempotency import (
    AcquiredIdempotencyRecord,
    IdempotencyKeyReusedError,
    IdempotencyRepository,
    IdempotencyRequest,
    ProcessingIdempotencyRecord,
    ReplayIdempotencyRecord,
)
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.jobs import project_ai_job
from tbd.schemas.recordings import (
    RecordingUploadCompleteRequest,
    RecordingUploadCompleteResponse,
    RecordingUploadCreateRequest,
    RecordingUploadResponse,
    SessionRecordingResponse,
)
from tbd.schemas.transcripts import TranscriptVersionResponse
from tbd.services.courses import (
    CourseAccessDeniedError,
    CourseNotFoundError,
    CourseRoleRequiredError,
)
from tbd.services.lifecycle import (
    LifecycleAccessDeniedError,
    LifecycleResourceNotFoundError,
    LifecycleService,
    RecordingDeletionConflictError,
)
from tbd.services.recordings import (
    RecordingChecksumMismatchError,
    RecordingChunkTooLargeError,
    RecordingNotFoundError,
    RecordingNotReadyError,
    RecordingOffsetMismatchError,
    RecordingPublisherRequiredError,
    RecordingRangeNotSatisfiableError,
    RecordingService,
    RecordingStateConflictError,
    RecordingStorageUnavailableError,
    RecordingTooLargeError,
    RecordingUploadConflictError,
    RecordingUploadExpiredError,
    RecordingUploadNotFoundError,
    UnsupportedRecordingFormatError,
    recording_response,
)
from tbd.storage import Storage, StorageCompensation, StorageError, StorageKey, StorageNamespace

router = APIRouter(tags=["Recordings"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
StorageDependency = Annotated[Storage, Depends(get_storage)]
OptionalIdempotency = Annotated[
    IdempotencyRepository | None,
    Depends(get_optional_idempotency_repository),
]
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
UploadOffsetHeader = Annotated[int | None, Header(alias="Upload-Offset")]
ChunkChecksumHeader = Annotated[str | None, Header(alias="X-Chunk-SHA256")]
RangeHeader = Annotated[str | None, Header(alias="Range")]
RECORDING_IDEMPOTENCY_LEASE = timedelta(seconds=60)


def _service(settings: Settings) -> RecordingService:
    return RecordingService(settings)


def _upload_response(upload: object) -> RecordingUploadResponse:
    return RecordingUploadResponse(
        id=upload.id,
        recording_id=upload.recording_id,
        status=upload.status,
        offset_bytes=upload.offset_bytes,
        total_bytes=upload.total_bytes,
        expires_at=upload.expires_at,
        version=upload.version,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
    )


def _transcript_version_response(version: object) -> TranscriptVersionResponse:
    return TranscriptVersionResponse(
        id=version.id,
        session_id=version.session_id,
        source=version.source,
        status=version.status,
        version=version.version,
        last_sequence=version.last_sequence,
        is_canonical=False,
        recording_id=version.recording_id,
        created_by_job_id=version.created_by_job_id,
        created_by_job_attempt=version.created_by_job_attempt,
        finalized_at=version.finalized_at,
        failed_at=version.failed_at,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


def _require_idempotency_key(key: str | None) -> str:
    if key is None:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.")
    return key


async def _acquire(
    session: AsyncSession,
    repository: IdempotencyRepository | None,
    *,
    user_id: UUID,
    key: str,
    method: str,
    route_key: str,
    body: dict[str, object],
    now: datetime,
) -> AcquiredIdempotencyRecord | ReplayIdempotencyRecord:
    if repository is None:
        raise ApiError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "멱등성 응답 암호화 설정을 사용할 수 없습니다.",
        )
    try:
        key_hash = idempotency_key_hash(key)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.") from exc
    acquired = await repository.acquire(
        session,
        IdempotencyRequest(
            user_id=user_id,
            method=method,
            route_key=route_key,
            key_hash=key_hash,
            request_hash=canonical_request_hash(method, route_key, body),
        ),
        now=now,
        processing_lease=RECORDING_IDEMPOTENCY_LEASE,
    )
    if isinstance(acquired, ProcessingIdempotencyRecord):
        raise ApiError(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS", "동일한 요청을 처리하고 있습니다.")
    assert isinstance(acquired, (AcquiredIdempotencyRecord, ReplayIdempotencyRecord))
    return acquired


def _raise_recording_error(error: Exception) -> NoReturn:
    if isinstance(error, CourseNotFoundError):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 class를 찾을 수 없습니다.") from error
    if isinstance(error, CourseAccessDeniedError):
        raise ApiError(
            403, "COURSE_ACCESS_DENIED", "이 Course에 접근할 권한이 없습니다."
        ) from error
    if isinstance(error, (CourseRoleRequiredError, RecordingPublisherRequiredError)):
        raise ApiError(
            403,
            "RECORDING_PUBLISHER_REQUIRED",
            "이 녹음의 최초 교수자만 upload를 재개할 수 있습니다.",
        ) from error
    if isinstance(error, (RecordingNotFoundError, RecordingUploadNotFoundError)):
        code = (
            "RECORDING_UPLOAD_NOT_FOUND"
            if isinstance(error, RecordingUploadNotFoundError)
            else "RECORDING_NOT_FOUND"
        )
        message = (
            "요청한 녹음 upload를 찾을 수 없습니다."
            if isinstance(error, RecordingUploadNotFoundError)
            else "요청한 녹음을 찾을 수 없습니다."
        )
        raise ApiError(404, code, message) from error
    if isinstance(error, RecordingUploadExpiredError):
        raise ApiError(
            410, "RECORDING_UPLOAD_EXPIRED", "녹음 upload 재개 시간이 만료되었습니다."
        ) from error
    if isinstance(error, RecordingUploadConflictError):
        raise ApiError(
            409, "RECORDING_UPLOAD_CONFLICT", "이미 진행 중인 녹음 upload가 있습니다."
        ) from error
    if isinstance(error, RecordingOffsetMismatchError):
        raise ApiError(
            409,
            "UPLOAD_OFFSET_MISMATCH",
            "서버가 확인한 녹음 upload 위치와 일치하지 않습니다.",
            details={"offset_bytes": error.offset_bytes},
        ) from error
    if isinstance(error, RecordingStateConflictError):
        raise ApiError(
            409,
            "RECORDING_STATE_CONFLICT",
            "현재 녹음 상태에서는 이 작업을 수행할 수 없습니다.",
        ) from error
    if isinstance(error, RecordingNotReadyError):
        raise ApiError(
            409, "RECORDING_NOT_READY", "녹음 upload가 아직 완료되지 않았습니다."
        ) from error
    if isinstance(error, RecordingChecksumMismatchError):
        raise ApiError(
            422, "RECORDING_CHECKSUM_MISMATCH", "녹음 무결성 검증에 실패했습니다."
        ) from error
    if isinstance(error, RecordingTooLargeError):
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            "녹음 파일 크기는 100,000,000 bytes 이하여야 합니다.",
            details={"max_upload_bytes": 100_000_000},
        ) from error
    if isinstance(error, RecordingChunkTooLargeError):
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            "녹음 upload chunk는 8,388,608 bytes 이하여야 합니다.",
            details={"max_chunk_bytes": 8_388_608},
        ) from error
    if isinstance(error, UnsupportedRecordingFormatError):
        raise ApiError(
            415,
            "UNSUPPORTED_RECORDING_FORMAT",
            "audio/webm 또는 audio/mp4 녹음만 업로드할 수 있습니다.",
        ) from error
    if isinstance(error, RecordingRangeNotSatisfiableError):
        raise ApiError(
            416, "RANGE_NOT_SATISFIABLE", "요청한 녹음 범위를 재생할 수 없습니다."
        ) from error
    if isinstance(error, RecordingStorageUnavailableError):
        raise ApiError(
            503, "STORAGE_UNAVAILABLE", "파일 저장소를 일시적으로 사용할 수 없습니다."
        ) from error
    if isinstance(error, LifecycleResourceNotFoundError):
        raise ApiError(404, "RECORDING_NOT_FOUND", "요청한 녹음을 찾을 수 없습니다.") from error
    if isinstance(error, LifecycleAccessDeniedError):
        raise ApiError(
            403,
            "ROLE_REQUIRED",
            "Course를 처음 생성한 교수자만 녹음을 삭제할 수 있습니다.",
            details={"required_role": "COURSE_CREATOR_PROFESSOR"},
        ) from error
    if isinstance(error, RecordingDeletionConflictError):
        raise ApiError(
            409,
            "RECORDING_DELETE_CONFLICT",
            "COMPLETED class의 업로드 완료 녹음만 삭제할 수 있습니다.",
        ) from error
    raise error


@router.get(
    "/sessions/{session_id}/recording",
    response_model=SessionRecordingResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_session_recording(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> SessionRecordingResponse:
    try:
        recording = await _service(settings).get_for_session_member(
            session, session_id=session_id, user_id=user_id
        )
    except Exception as exc:
        _raise_recording_error(exc)
    return recording_response(recording)


@router.post(
    "/sessions/{session_id}/recording/abandon-upload",
    response_model=SessionRecordingResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def abandon_session_recording_upload(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> SessionRecordingResponse:
    """Use the finalized LIVE transcript when this browser has no HQ recording to upload."""

    try:
        async with transaction(session):
            recording = await _service(settings).abandon_local_upload(
                session,
                session_id=session_id,
                user_id=user_id,
                now=datetime.now(UTC),
            )
    except Exception as exc:
        _raise_recording_error(exc)
    return recording_response(recording)


@router.delete(
    "/sessions/{session_id}/recording",
    status_code=204,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def delete_session_recording(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader,
) -> Response:
    """Allow the Course owner to remove an uploaded completed-class recording early."""

    key = _require_idempotency_key(idempotency_key)
    now = datetime.now(UTC)
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=key,
                method="DELETE",
                route_key="/api/v1/sessions/{session_id}/recording",
                body={},
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return Response(status_code=acquired.status_code)
            await LifecycleService().delete_recording(
                session,
                session_id=session_id,
                user_id=user_id,
                now=now,
            )
            assert isinstance(acquired, AcquiredIdempotencyRecord)
            assert idempotency is not None
            await idempotency.complete(
                session,
                record_id=acquired.record_id,
                status_code=204,
                body={},
                now=now,
            )
    except (
        LifecycleResourceNotFoundError,
        LifecycleAccessDeniedError,
        RecordingDeletionConflictError,
    ) as exc:
        _raise_recording_error(exc)
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    return Response(status_code=204)


@router.post(
    "/sessions/{session_id}/recording/uploads",
    status_code=201,
    response_model=RecordingUploadResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def create_recording_upload(
    session_id: UUID,
    request_body: RecordingUploadCreateRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    storage: StorageDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader,
) -> RecordingUploadResponse | JSONResponse:
    key = _require_idempotency_key(idempotency_key)
    now = datetime.now(UTC)
    response: RecordingUploadResponse | None = None
    replaced_temporary_key: StorageKey | None = None
    try:
        async with StorageCompensation(storage) as compensation:
            temporary_key = StorageKey.new(StorageNamespace.TEMPORARY)
            await storage.create_temporary(temporary_key)
            compensation.track(temporary_key)
            async with transaction(session):
                acquired = await _acquire(
                    session,
                    idempotency,
                    user_id=user_id,
                    key=key,
                    method="POST",
                    route_key="/api/v1/sessions/{session_id}/recording/uploads",
                    body=request_body.model_dump(mode="json"),
                    now=now,
                )
                if isinstance(acquired, ReplayIdempotencyRecord):
                    return JSONResponse(status_code=acquired.status_code, content=acquired.body)
                created = await _service(settings).create_upload(
                    session,
                    session_id=session_id,
                    user_id=user_id,
                    client_stream_id=request_body.client_stream_id,
                    content_type=request_body.content_type,
                    total_bytes=request_body.total_bytes,
                    duration_ms=request_body.duration_ms,
                    temporary_key=temporary_key,
                    max_upload_bytes=settings.max_upload_bytes,
                    now=now,
                )
                response = _upload_response(created.upload)
                replaced_temporary_key = created.replaced_temporary_key
                assert idempotency is not None
                await idempotency.complete(
                    session,
                    record_id=acquired.record_id,
                    status_code=201,
                    body=response.model_dump(mode="json"),
                    now=now,
                )
            compensation.commit()
    except (StorageError, ValueError):
        _raise_recording_error(RecordingStorageUnavailableError())
    except (
        CourseNotFoundError,
        CourseAccessDeniedError,
        CourseRoleRequiredError,
        RecordingNotFoundError,
        RecordingPublisherRequiredError,
        RecordingStateConflictError,
        RecordingUploadConflictError,
        RecordingTooLargeError,
        UnsupportedRecordingFormatError,
        RecordingStorageUnavailableError,
    ) as exc:
        _raise_recording_error(exc)
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    if replaced_temporary_key is not None:
        try:
            await storage.delete(replaced_temporary_key)
        except StorageError:
            pass
    assert response is not None
    return JSONResponse(
        status_code=201,
        content=response.model_dump(mode="json"),
        headers={"Location": f"/api/v1/recording-uploads/{response.id}"},
    )


@router.get(
    "/recording-uploads/{upload_id}",
    response_model=RecordingUploadResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
    },
)
async def get_recording_upload(
    upload_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> RecordingUploadResponse:
    expired_temporary_key: StorageKey | None = None
    try:
        async with transaction(session):
            try:
                upload = await _service(settings).get_upload_for_publisher(
                    session, upload_id=upload_id, user_id=user_id, now=datetime.now(UTC)
                )
            except RecordingUploadExpiredError as exc:
                expired_temporary_key = exc.temporary_key
    except Exception as exc:
        _raise_recording_error(exc)
    if expired_temporary_key is not None:
        try:
            await storage.delete(expired_temporary_key)
        except StorageError:
            pass
        _raise_recording_error(RecordingUploadExpiredError())
    return _upload_response(upload)


@router.patch(
    "/recording-uploads/{upload_id}",
    response_model=RecordingUploadResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def append_recording_upload_chunk(
    upload_id: UUID,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    storage: StorageDependency,
    upload_offset: UploadOffsetHeader,
    chunk_checksum: ChunkChecksumHeader,
) -> RecordingUploadResponse:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/octet-stream"
    ):
        raise ApiError(
            415, "UNSUPPORTED_RECORDING_FORMAT", "binary 녹음 chunk만 전송할 수 있습니다."
        )
    if upload_offset is None or chunk_checksum is None:
        raise ApiError(422, "VALIDATION_ERROR", "Upload-Offset과 X-Chunk-SHA256을 확인해 주세요.")
    expired_temporary_key: StorageKey | None = None
    try:
        content = await request.body()
        async with transaction(session):
            try:
                upload = await _service(settings).append_chunk(
                    session,
                    upload_id=upload_id,
                    user_id=user_id,
                    offset_bytes=upload_offset,
                    checksum=chunk_checksum,
                    content=content,
                    storage=storage,
                    now=datetime.now(UTC),
                )
            except RecordingUploadExpiredError as exc:
                expired_temporary_key = exc.temporary_key
    except Exception as exc:
        _raise_recording_error(exc)
    if expired_temporary_key is not None:
        try:
            await storage.delete(expired_temporary_key)
        except StorageError:
            pass
        _raise_recording_error(RecordingUploadExpiredError())
    return _upload_response(upload)


@router.post(
    "/recording-uploads/{upload_id}/complete",
    status_code=202,
    response_model=RecordingUploadCompleteResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def complete_recording_upload(
    upload_id: UUID,
    request_body: RecordingUploadCompleteRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    storage: StorageDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader,
) -> RecordingUploadCompleteResponse | JSONResponse:
    key = _require_idempotency_key(idempotency_key)
    now = datetime.now(UTC)
    response: RecordingUploadCompleteResponse | None = None
    expired_temporary_key: StorageKey | None = None
    try:
        # Persist an expired manifest before acquiring a completion idempotency
        # record.  The expiry response itself must not reserve that key.
        async with transaction(session):
            expired_temporary_key = await _service(settings).expire_upload_if_due(
                session, upload_id=upload_id, user_id=user_id, now=now
            )
        if expired_temporary_key is not None:
            try:
                await storage.delete(expired_temporary_key)
            except StorageError:
                pass
            _raise_recording_error(RecordingUploadExpiredError())
        async with StorageCompensation(storage) as compensation:
            async with transaction(session):
                acquired = await _acquire(
                    session,
                    idempotency,
                    user_id=user_id,
                    key=key,
                    method="POST",
                    route_key="/api/v1/recording-uploads/{upload_id}/complete",
                    body=request_body.model_dump(mode="json"),
                    now=now,
                )
                if isinstance(acquired, ReplayIdempotencyRecord):
                    return JSONResponse(status_code=acquired.status_code, content=acquired.body)
                prepared = await _service(settings).prepare_completion(
                    session,
                    upload_id=upload_id,
                    user_id=user_id,
                    sha256=request_body.sha256,
                    storage=storage,
                    now=now,
                )
                try:
                    await storage.promote(
                        StorageKey.parse(prepared.upload.temporary_storage_key),
                        prepared.final_key,
                        expected_sha256=request_body.sha256,
                    )
                except StorageError as exc:
                    raise RecordingStorageUnavailableError from exc
                compensation.track(prepared.final_key)
                completed = await _service(settings).complete_upload(
                    session, prepared=prepared, now=now
                )
                response = RecordingUploadCompleteResponse(
                    recording=recording_response(completed.recording),
                    transcript_version=_transcript_version_response(completed.transcript_version),
                    job=project_ai_job(completed.job),
                )
                assert idempotency is not None
                await idempotency.complete(
                    session,
                    record_id=acquired.record_id,
                    status_code=202,
                    body=response.model_dump(mode="json"),
                    now=now,
                )
            compensation.commit()
    except (
        CourseRoleRequiredError,
        RecordingPublisherRequiredError,
        RecordingUploadNotFoundError,
        RecordingUploadExpiredError,
        RecordingStateConflictError,
        RecordingOffsetMismatchError,
        RecordingChecksumMismatchError,
        RecordingStorageUnavailableError,
    ) as exc:
        _raise_recording_error(exc)
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    assert response is not None
    return JSONResponse(status_code=202, content=response.model_dump(mode="json"))


@router.get(
    "/recordings/{recording_id}/playback",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        416: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def play_recording(
    recording_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    storage: StorageDependency,
    byte_range: RangeHeader = None,
) -> Response:
    try:
        recording, content, start, end, total = await _service(settings).playback(
            session,
            recording_id=recording_id,
            user_id=user_id,
            byte_range=byte_range,
            storage=storage,
        )
    except Exception as exc:
        _raise_recording_error(exc)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start),
    }
    status_code = 200
    if byte_range is not None:
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end - 1}/{total}"
    return Response(
        content=content,
        status_code=status_code,
        media_type=recording.content_type,
        headers=headers,
    )
