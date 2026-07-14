"""Professor Answer capture and completed-record text endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_current_user_id,
    get_db_session,
    get_optional_idempotency_repository,
    get_settings,
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
from tbd.schemas.answers import (
    AnswerCompleteRequest,
    AnswerCreateRequest,
    AnswerListResponse,
    AnswerResponse,
    AnswerTextUpdateRequest,
)
from tbd.schemas.errors import ErrorResponse
from tbd.services.answers import (
    AnswerAccessDeniedError,
    AnswerAlreadyExistsError,
    AnswerCaptureActiveError,
    AnswerNotFoundError,
    AnswerRoleRequiredError,
    AnswerService,
    AnswerSessionStateError,
    AnswerTargetStateError,
    AnswerTextValidationError,
    AnswerTranscriptNotReadyError,
    AnswerTranscriptRangeError,
    AnswerVersionConflictError,
    InvalidAnswerCursorError,
)

router = APIRouter(tags=["Answers"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
OptionalIdempotency = Annotated[
    IdempotencyRepository | None, Depends(get_optional_idempotency_repository)
]
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
PROCESSING_LEASE = timedelta(seconds=60)


def _service(settings: Settings) -> AnswerService:
    return AnswerService(auth_secret=settings.auth_secret_key.get_secret_value())


def _raise_error(error: Exception, *, hide_access: bool = False) -> None:
    if isinstance(error, AnswerNotFoundError) or (
        hide_access and isinstance(error, AnswerAccessDeniedError)
    ):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 Answer를 찾을 수 없습니다.") from error
    if isinstance(error, AnswerAccessDeniedError):
        raise ApiError(
            403, "COURSE_ACCESS_DENIED", "이 Course에 접근할 권한이 없습니다."
        ) from error
    if isinstance(error, AnswerRoleRequiredError):
        raise ApiError(
            403, "ROLE_REQUIRED", "Course 교수자만 Answer를 변경할 수 있습니다."
        ) from error
    if isinstance(error, AnswerSessionStateError):
        raise ApiError(
            409, "SESSION_STATE_CONFLICT", "현재 class 상태에서는 Answer를 변경할 수 없습니다."
        ) from error
    if isinstance(error, AnswerCaptureActiveError):
        raise ApiError(
            409, "ANSWER_CAPTURE_ACTIVE", "이미 진행 중인 음성 Answer가 있습니다."
        ) from error
    if isinstance(error, AnswerAlreadyExistsError):
        raise ApiError(
            409, "ANSWER_ALREADY_EXISTS", "이 질문에는 이미 Answer가 있습니다."
        ) from error
    if isinstance(error, AnswerTargetStateError):
        raise ApiError(
            409, "ANSWER_TARGET_STATE_CONFLICT", "선택한 질문은 현재 Answer 대상이 아닙니다."
        ) from error
    if isinstance(error, AnswerTranscriptNotReadyError):
        raise ApiError(
            409, "ANSWER_TRANSCRIPT_NOT_READY", "답변 구간의 확정 Transcript가 아직 없습니다."
        ) from error
    if isinstance(error, AnswerTranscriptRangeError):
        raise ApiError(422, "VALIDATION_ERROR", "답변 Transcript 범위를 확인해 주세요.") from error
    if isinstance(error, InvalidAnswerCursorError):
        raise ApiError(400, "INVALID_CURSOR", "Answer 목록 커서를 다시 확인해 주세요.") from error
    if isinstance(error, AnswerTextValidationError):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Answer 텍스트를 확인해 주세요.",
            details={
                "field": "text_content",
                "reason": error.reason,
                "max_length": 2000,
                "actual_length": error.actual_length,
            },
        ) from error
    if isinstance(error, AnswerVersionConflictError):
        raise ApiError(
            409,
            "ANSWER_VERSION_CONFLICT",
            "다른 변경이 먼저 저장되었습니다. 작성 중인 내용은 유지됩니다.",
            details={
                "current_version": error.current_version,
                "current_text_content": error.current_text_content,
            },
        ) from error
    raise error


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
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.")
    if repository is None:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "멱등성 응답 설정을 사용할 수 없습니다.")
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
        processing_lease=PROCESSING_LEASE,
    )
    if isinstance(acquired, ProcessingIdempotencyRecord):
        raise ApiError(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS", "동일한 요청을 처리하고 있습니다.")
    assert isinstance(acquired, (AcquiredIdempotencyRecord, ReplayIdempotencyRecord))
    return acquired


@router.get(
    "/sessions/{session_id}/answers",
    response_model=AnswerListResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def list_session_answers(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AnswerListResponse:
    try:
        return await _service(settings).list_for_member(
            session,
            session_id=session_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_error(exc)


@router.post(
    "/sessions/{session_id}/answers",
    status_code=201,
    response_model=AnswerResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_session_answer(
    session_id: UUID,
    payload: AnswerCreateRequest,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader = None,
) -> AnswerResponse | JSONResponse:
    now = datetime.now(UTC)
    route_key = "/api/v1/sessions/{session_id}/answers"
    body = payload.model_dump(mode="json")
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                method="POST",
                route_key=route_key,
                body=body,
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return JSONResponse(status_code=acquired.status_code, content=acquired.body)
            result = await _service(settings).create(
                session, session_id=session_id, user_id=user_id, payload=payload, now=now
            )
            if isinstance(acquired, AcquiredIdempotencyRecord):
                assert idempotency is not None
                await idempotency.complete(
                    session,
                    record_id=acquired.record_id,
                    status_code=201,
                    body=result.model_dump(mode="json"),
                    now=now,
                )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except Exception as exc:
        _raise_error(exc)
    response.headers["Location"] = f"/api/v1/answers/{result.id}"
    return result


@router.get(
    "/answers/{answer_id}",
    response_model=AnswerResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_answer(
    answer_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> AnswerResponse:
    try:
        return await _service(settings).get_for_member(
            session, answer_id=answer_id, user_id=user_id
        )
    except Exception as exc:
        _raise_error(exc, hide_access=True)


@router.post(
    "/answers/{answer_id}/complete",
    response_model=AnswerResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def complete_answer_capture(
    answer_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader = None,
    payload: AnswerCompleteRequest | None = None,
) -> AnswerResponse | JSONResponse:
    now = datetime.now(UTC)
    body = payload.model_dump(mode="json") if payload is not None else {}
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                method="POST",
                route_key="/api/v1/answers/{answer_id}/complete",
                body=body,
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return JSONResponse(status_code=acquired.status_code, content=acquired.body)
            result = await _service(settings).complete(
                session, answer_id=answer_id, user_id=user_id, payload=payload, now=now
            )
            if isinstance(acquired, AcquiredIdempotencyRecord):
                assert idempotency is not None
                await idempotency.complete(
                    session,
                    record_id=acquired.record_id,
                    status_code=200,
                    body=result.model_dump(mode="json"),
                    now=now,
                )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except Exception as exc:
        _raise_error(exc, hide_access=True)
    return result


@router.patch(
    "/answers/{answer_id}",
    response_model=AnswerResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def update_answer_text(
    answer_id: UUID,
    payload: AnswerTextUpdateRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> AnswerResponse:
    try:
        async with transaction(session):
            return await _service(settings).update_text(
                session, answer_id=answer_id, user_id=user_id, payload=payload
            )
    except Exception as exc:
        _raise_error(exc, hide_access=True)


@router.post(
    "/answers/{answer_id}/cancel",
    status_code=204,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def cancel_answer_capture(
    answer_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader = None,
) -> Response:
    now = datetime.now(UTC)
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                method="POST",
                route_key="/api/v1/answers/{answer_id}/cancel",
                body={},
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return Response(status_code=acquired.status_code)
            await _service(settings).cancel(session, answer_id=answer_id, user_id=user_id)
            if isinstance(acquired, AcquiredIdempotencyRecord):
                assert idempotency is not None
                await idempotency.complete(
                    session, record_id=acquired.record_id, status_code=204, body={}, now=now
                )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except Exception as exc:
        _raise_error(exc, hide_access=True)
    return Response(status_code=204)


@router.delete(
    "/answers/{answer_id}/text",
    status_code=204,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def withdraw_answer_text(
    answer_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader = None,
) -> Response:
    now = datetime.now(UTC)
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                method="DELETE",
                route_key="/api/v1/answers/{answer_id}/text",
                body={},
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return Response(status_code=acquired.status_code)
            await _service(settings).withdraw_text(session, answer_id=answer_id, user_id=user_id)
            if isinstance(acquired, AcquiredIdempotencyRecord):
                assert idempotency is not None
                await idempotency.complete(
                    session, record_id=acquired.record_id, status_code=204, body={}, now=now
                )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except Exception as exc:
        _raise_error(exc, hide_access=True)
    return Response(status_code=204)
