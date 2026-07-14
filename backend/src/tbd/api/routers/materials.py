"""Course-authorized PDF Material upload, reads, and detach endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile
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
from tbd.schemas.materials import (
    LectureMaterialListResponse,
    LectureMaterialResponse,
    MaterialUploadAcceptedResponse,
)
from tbd.services.courses import (
    CourseAccessDeniedError,
    CourseNotFoundError,
    CourseRoleRequiredError,
)
from tbd.services.materials import (
    InvalidMaterialCursorError,
    InvalidPdfError,
    MaterialDeleteConflictError,
    MaterialLimitExceededError,
    MaterialNotFoundError,
    MaterialService,
    MaterialStateConflictError,
    MaterialStorageUnavailableError,
    MaterialTooLargeError,
)
from tbd.storage import Storage, StorageCompensation, StorageError, StorageKey, StorageNotFoundError

router = APIRouter(tags=["Materials"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
StorageDependency = Annotated[Storage, Depends(get_storage)]
OptionalIdempotency = Annotated[
    IdempotencyRepository | None,
    Depends(get_optional_idempotency_repository),
]
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
MATERIAL_IDEMPOTENCY_LEASE = timedelta(seconds=60)


def _material_response(material: object) -> LectureMaterialResponse:
    return LectureMaterialResponse.model_validate(material)


def _raise_in_progress() -> None:
    raise ApiError(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS", "동일한 요청을 처리하고 있습니다.")


async def _acquire(
    session: AsyncSession,
    repository: IdempotencyRepository | None,
    *,
    user_id: UUID,
    key: str | None,
    method: str,
    route_key: str,
    body: dict[str, object],
    now: datetime,
) -> AcquiredIdempotencyRecord | ReplayIdempotencyRecord | None:
    if key is None:
        return None
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
        processing_lease=MATERIAL_IDEMPOTENCY_LEASE,
    )
    if isinstance(acquired, ProcessingIdempotencyRecord):
        _raise_in_progress()
    assert isinstance(acquired, (AcquiredIdempotencyRecord, ReplayIdempotencyRecord))
    return acquired


def _raise_session_error(error: Exception) -> None:
    if isinstance(error, CourseNotFoundError):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 class를 찾을 수 없습니다.") from error
    if isinstance(error, CourseAccessDeniedError):
        raise ApiError(
            403, "COURSE_ACCESS_DENIED", "이 Course에 접근할 권한이 없습니다."
        ) from error
    if isinstance(error, CourseRoleRequiredError):
        raise ApiError(
            403,
            "ROLE_REQUIRED",
            "Course 교수자만 강의자료를 관리할 수 있습니다.",
            details={"required_role": "COURSE_CREATOR_PROFESSOR"},
        ) from error
    if isinstance(error, MaterialStateConflictError):
        raise ApiError(
            409,
            "SESSION_STATE_CONFLICT",
            "정리 중인 class에서는 강의자료를 변경할 수 없습니다.",
            details={"allowed_statuses": ["READY", "LIVE", "COMPLETED"]},
        ) from error
    if isinstance(error, MaterialDeleteConflictError):
        raise ApiError(
            409,
            "MATERIAL_DELETE_CONFLICT",
            "강의자료 상태가 변경되었습니다. 목록을 새로고침한 뒤 다시 시도해 주세요.",
        ) from error
    if isinstance(error, MaterialLimitExceededError):
        raise ApiError(
            409,
            "MATERIAL_LIMIT_EXCEEDED",
            "class당 강의자료 개수 제한을 초과했습니다.",
            details={"max_active_materials": 10},
        ) from error
    if isinstance(error, MaterialNotFoundError):
        raise ApiError(404, "MATERIAL_NOT_FOUND", "요청한 강의자료를 찾을 수 없습니다.") from error
    if isinstance(error, InvalidMaterialCursorError):
        raise ApiError(400, "INVALID_CURSOR", "강의자료 목록 cursor를 확인해 주세요.") from error
    if isinstance(error, InvalidPdfError):
        raise ApiError(
            415, "UNSUPPORTED_MEDIA_TYPE", "유효한 PDF 파일만 업로드할 수 있습니다."
        ) from error
    if isinstance(error, MaterialTooLargeError):
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            "파일 크기는 100,000,000 bytes 이하여야 합니다.",
            details={"max_upload_bytes": 100_000_000},
        ) from error
    if isinstance(error, MaterialStorageUnavailableError):
        raise ApiError(
            503, "STORAGE_UNAVAILABLE", "파일 저장소를 일시적으로 사용할 수 없습니다."
        ) from error
    raise error


@router.get(
    "/sessions/{session_id}/materials",
    response_model=LectureMaterialListResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def list_session_materials(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LectureMaterialListResponse:
    try:
        items, next_cursor = await MaterialService().list_for_member(
            session,
            session_id=session_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )
    except (CourseNotFoundError, CourseAccessDeniedError, InvalidMaterialCursorError) as exc:
        _raise_session_error(exc)
    return LectureMaterialListResponse(
        items=[_material_response(material) for material in items], next_cursor=next_cursor
    )


@router.post(
    "/sessions/{session_id}/materials",
    status_code=202,
    response_model=MaterialUploadAcceptedResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def upload_session_material(
    session_id: UUID,
    file: Annotated[UploadFile, File()],
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    storage: StorageDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader,
) -> MaterialUploadAcceptedResponse | JSONResponse:
    service = MaterialService()
    now = datetime.now(UTC)
    response: MaterialUploadAcceptedResponse | None = None
    try:
        validated = await service.validate_upload(file, max_upload_bytes=settings.max_upload_bytes)
        async with StorageCompensation(storage) as compensation:
            storage_key = await service.store_validated_pdf(
                storage,
                validated,
                track=compensation.track,
                release=compensation.release,
            )
            async with transaction(session):
                acquired = await _acquire(
                    session,
                    idempotency,
                    user_id=user_id,
                    key=idempotency_key,
                    method="POST",
                    route_key="/api/v1/sessions/{session_id}/materials",
                    body={
                        "byte_size": validated.byte_size,
                        "filename": validated.original_filename,
                        "sha256": validated.sha256,
                    },
                    now=now,
                )
                if isinstance(acquired, ReplayIdempotencyRecord):
                    return JSONResponse(status_code=acquired.status_code, content=acquired.body)
                result = await service.upload(
                    session,
                    session_id=session_id,
                    user_id=user_id,
                    validated=validated,
                    storage_key=storage_key,
                )
                response = MaterialUploadAcceptedResponse(
                    material=_material_response(result.material),
                    job=project_ai_job(result.job),
                )
                if isinstance(acquired, AcquiredIdempotencyRecord):
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
        CourseNotFoundError,
        CourseAccessDeniedError,
        CourseRoleRequiredError,
        MaterialStateConflictError,
        MaterialLimitExceededError,
        InvalidPdfError,
        MaterialTooLargeError,
        MaterialStorageUnavailableError,
    ) as exc:
        _raise_session_error(exc)
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    finally:
        await file.close()
    assert response is not None
    result_response_headers = {"Location": f"/api/v1/materials/{response.material.id}"}
    return JSONResponse(
        status_code=202,
        content=response.model_dump(mode="json"),
        headers=result_response_headers,
    )


@router.get(
    "/materials/{material_id}",
    response_model=LectureMaterialResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_material(
    material_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> LectureMaterialResponse:
    try:
        material = await MaterialService().get_for_member(
            session, material_id=material_id, user_id=user_id
        )
    except MaterialNotFoundError as exc:
        _raise_session_error(exc)
    return _material_response(material)


@router.get(
    "/materials/{material_id}/content",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def get_material_content(
    material_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    storage: StorageDependency,
) -> Response:
    try:
        material = await MaterialService().get_for_member(
            session, material_id=material_id, user_id=user_id
        )
        if material.processing_status not in {"UPLOADED", "PROCESSING", "READY"}:
            raise MaterialNotFoundError
        storage_key = StorageKey.parse(material.storage_key)
        metadata = await storage.stat(storage_key)
        content = await storage.read_range(storage_key, start=0, end=metadata.byte_size)
    except (MaterialNotFoundError, StorageNotFoundError, ValueError) as exc:
        _raise_session_error(
            MaterialNotFoundError() if not isinstance(exc, MaterialNotFoundError) else exc
        )
    except StorageError as exc:
        raise ApiError(
            503, "STORAGE_UNAVAILABLE", "파일 저장소를 일시적으로 사용할 수 없습니다."
        ) from exc
    filename = quote(material.display_name, safe="")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"},
    )


@router.delete(
    "/materials/{material_id}",
    status_code=204,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def detach_material(
    material_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    storage: StorageDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader,
) -> Response:
    if idempotency_key is None:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.")
    now = datetime.now(UTC)
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                method="DELETE",
                route_key="/api/v1/materials/{material_id}",
                body={},
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return Response(status_code=acquired.status_code)
            storage_key = await MaterialService().detach(
                session, material_id=material_id, user_id=user_id, now=now
            )
            assert isinstance(acquired, AcquiredIdempotencyRecord)
            assert idempotency is not None
            await idempotency.complete(
                session, record_id=acquired.record_id, status_code=204, body={}, now=now
            )
    except (
        CourseNotFoundError,
        CourseAccessDeniedError,
        CourseRoleRequiredError,
        MaterialDeleteConflictError,
        MaterialStateConflictError,
        MaterialNotFoundError,
    ) as exc:
        _raise_session_error(exc)
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc

    try:
        await storage.delete(storage_key)
    except StorageError:
        # The committed outbox marker lets a later cleanup worker retry without re-exposing Material.
        pass
    return Response(status_code=204)
