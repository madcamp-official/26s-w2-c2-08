"""Polling and retry endpoints shared by asynchronous AI features."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_current_user_id,
    get_db_session,
    get_idempotency_repository,
    require_allowed_origin,
)
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
from tbd.schemas.jobs import AIJobAcceptedResponse, AIJobResponse, project_ai_job
from tbd.services.jobs import (
    JobAccessDeniedError,
    JobNotFoundError,
    JobRetryConflictError,
    JobService,
)

router = APIRouter(prefix="/jobs", tags=["Jobs"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
IdempotencyRepositoryDependency = Annotated[
    IdempotencyRepository,
    Depends(get_idempotency_repository),
]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1)]
AllowedOrigin = Annotated[None, Depends(require_allowed_origin)]
PROCESSING_LEASE = timedelta(seconds=60)


@router.get(
    "/{job_id}",
    response_model=AIJobResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_job(
    job_id: UUID,
    user_id: CurrentUserId,
    session: DatabaseSession,
) -> AIJobResponse:
    """Return a polling-safe Job representation to an allowed Course member."""

    try:
        job = await JobService().get_visible(session, job_id=job_id, user_id=user_id)
    except JobNotFoundError as exc:
        raise ApiError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="요청한 리소스를 찾을 수 없습니다.",
        ) from exc
    return project_ai_job(job)


@router.post(
    "/{job_id}/retry",
    response_model=AIJobAcceptedResponse,
    status_code=202,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def retry_job(
    job_id: UUID,
    idempotency_key: IdempotencyKey,
    user_id: CurrentUserId,
    session: DatabaseSession,
    idempotency: IdempotencyRepositoryDependency,
    _allowed_origin: AllowedOrigin,
) -> AIJobAcceptedResponse | JSONResponse:
    """Atomically requeue one eligible Job and persist its replayable 202 response."""

    try:
        key_hash = idempotency_key_hash(idempotency_key)
    except ValueError as exc:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="입력 형식을 확인해 주세요.",
        ) from exc

    now = datetime.now(UTC)
    request = IdempotencyRequest(
        user_id=user_id,
        method="POST",
        route_key="/api/v1/jobs/{job_id}/retry",
        key_hash=key_hash,
        request_hash=canonical_request_hash("POST", "/api/v1/jobs/{job_id}/retry", {}),
    )
    try:
        async with transaction(session):
            acquired = await idempotency.acquire(
                session,
                request,
                now=now,
                processing_lease=PROCESSING_LEASE,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return JSONResponse(status_code=acquired.status_code, content=acquired.body)
            if isinstance(acquired, ProcessingIdempotencyRecord):
                raise ApiError(
                    status_code=409,
                    code="IDEMPOTENCY_REQUEST_IN_PROGRESS",
                    message="동일한 요청을 처리하고 있습니다. 잠시 후 다시 시도해 주세요.",
                )
            assert isinstance(acquired, AcquiredIdempotencyRecord)
            job = await JobService().retry(session, job_id=job_id, user_id=user_id, now=now)
            response = AIJobAcceptedResponse(job=project_ai_job(job))
            await idempotency.complete(
                session,
                record_id=acquired.record_id,
                status_code=202,
                body=response.model_dump(mode="json"),
                now=now,
            )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="같은 멱등 키가 다른 요청에 사용되었습니다.",
        ) from exc
    except JobNotFoundError as exc:
        raise ApiError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="요청한 리소스를 찾을 수 없습니다.",
        ) from exc
    except JobAccessDeniedError as exc:
        raise ApiError(
            status_code=403,
            code="COURSE_ACCESS_DENIED",
            message="접근할 권한이 없습니다.",
        ) from exc
    except JobRetryConflictError as exc:
        raise ApiError(
            status_code=409,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ) from exc

    return response
