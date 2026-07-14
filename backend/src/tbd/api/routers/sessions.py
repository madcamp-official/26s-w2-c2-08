"""Course-scoped class creation and lifecycle HTTP endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_current_user_id,
    get_db_session,
    get_idempotency_repository,
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
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.jobs import project_ai_job
from tbd.schemas.sessions import (
    LectureSessionCreateRequest,
    LectureSessionListResponse,
    LectureSessionResponse,
    LectureSessionUpdateRequest,
    SessionEndAcceptedResponse,
)
from tbd.services.courses import (
    CourseAccessDeniedError,
    CourseNotFoundError,
    CourseRoleRequiredError,
)
from tbd.services.sessions import (
    ActiveSessionExistsError,
    InvalidSessionCursorError,
    MaterialProcessingActiveError,
    SessionService,
    SessionStateConflictError,
)

router = APIRouter(tags=["Sessions"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
OptionalIdempotency = Annotated[
    IdempotencyRepository | None,
    Depends(get_optional_idempotency_repository),
]
RequiredIdempotency = Annotated[IdempotencyRepository, Depends(get_idempotency_repository)]
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
RequiredIdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key")]
PROCESSING_LEASE = timedelta(seconds=60)
SessionStatus = Literal["READY", "LIVE", "PROCESSING", "COMPLETED"]


def _service(settings: Settings) -> SessionService:
    return SessionService(
        timezone_name=settings.app_timezone,
        auth_secret=settings.auth_secret_key.get_secret_value(),
    )


def _project(lecture_session: object) -> LectureSessionResponse:
    return LectureSessionResponse.model_validate(lecture_session)


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
    required: bool,
) -> AcquiredIdempotencyRecord | ReplayIdempotencyRecord | None:
    if key is None:
        if required:
            raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.")
        return None
    if repository is None:
        raise ApiError(
            503, "DEPENDENCY_UNAVAILABLE", "멱등성 응답 암호화 설정을 사용할 수 없습니다."
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
        processing_lease=PROCESSING_LEASE,
    )
    if isinstance(acquired, ProcessingIdempotencyRecord):
        _raise_in_progress()
    assert isinstance(acquired, (AcquiredIdempotencyRecord, ReplayIdempotencyRecord))
    return acquired


def _raise_domain_error(error: Exception) -> None:
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
            "Course를 처음 생성한 교수자만 수행할 수 있습니다.",
            details={"required_role": "COURSE_CREATOR_PROFESSOR"},
        ) from error
    if isinstance(error, ActiveSessionExistsError):
        raise ApiError(
            409, "ACTIVE_SESSION_EXISTS", "이 Course에는 이미 진행 중인 class가 있습니다."
        ) from error
    if isinstance(error, MaterialProcessingActiveError):
        raise ApiError(
            409,
            "MATERIAL_PROCESSING_ACTIVE",
            "처리 중인 강의자료가 있어 class를 시작할 수 없습니다.",
        ) from error
    if isinstance(error, SessionStateConflictError):
        raise ApiError(
            409, "SESSION_STATE_CONFLICT", "현재 class 상태에서는 요청을 수행할 수 없습니다."
        ) from error
    if isinstance(error, InvalidSessionCursorError):
        raise ApiError(400, "INVALID_CURSOR", "목록 커서를 다시 확인해 주세요.") from error
    raise error


@router.get(
    "/courses/{course_id}/sessions",
    response_model=LectureSessionListResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def list_course_sessions(
    course_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    status: Annotated[SessionStatus | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LectureSessionListResponse:
    """List the current member's classes without relying on WebSocket state."""

    try:
        result = await _service(settings).list_for_member(
            session,
            course_id=course_id,
            user_id=user_id,
            status=status,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_domain_error(exc)
    return LectureSessionListResponse(
        items=[_project(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/courses/{course_id}/sessions",
    status_code=201,
    response_model=LectureSessionResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def create_course_session(
    course_id: UUID,
    payload: LectureSessionCreateRequest,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader = None,
) -> LectureSessionResponse | JSONResponse:
    """Create exactly one READY class while the Course lock serializes contenders."""

    now = datetime.now(UTC)
    route_key = "/api/v1/courses/{course_id}/sessions"
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
                required=False,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return JSONResponse(status_code=acquired.status_code, content=acquired.body)
            lecture_session = await _service(settings).create(
                session, course_id=course_id, user_id=user_id, now=now, **payload.model_dump()
            )
            result = _project(lecture_session)
            if isinstance(acquired, AcquiredIdempotencyRecord):
                assert idempotency is not None
                await idempotency.complete(
                    session,
                    record_id=acquired.record_id,
                    status_code=201,
                    body=result.model_dump(mode="json"),
                    now=now,
                )
    except (
        CourseNotFoundError,
        CourseAccessDeniedError,
        CourseRoleRequiredError,
        ActiveSessionExistsError,
    ) as exc:
        _raise_domain_error(exc)
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    response.headers["Location"] = f"/api/v1/sessions/{result.id}"
    return result


@router.get(
    "/sessions/{session_id}",
    response_model=LectureSessionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_session(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> LectureSessionResponse:
    try:
        lecture_session = await _service(settings).get_for_member(
            session, session_id=session_id, user_id=user_id
        )
    except (CourseNotFoundError, CourseAccessDeniedError) as exc:
        _raise_domain_error(exc)
    return _project(lecture_session)


@router.patch(
    "/sessions/{session_id}",
    response_model=LectureSessionResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def update_session_title(
    session_id: UUID,
    payload: LectureSessionUpdateRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> LectureSessionResponse:
    try:
        async with transaction(session):
            lecture_session = await _service(settings).update_title(
                session, session_id=session_id, user_id=user_id, title=payload.title
            )
    except (CourseNotFoundError, CourseAccessDeniedError, CourseRoleRequiredError) as exc:
        _raise_domain_error(exc)
    return _project(lecture_session)


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def delete_session(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    idempotency: RequiredIdempotency,
    idempotency_key: RequiredIdempotencyHeader,
) -> Response:
    now = datetime.now(UTC)
    route_key = "/api/v1/sessions/{session_id}"
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                method="DELETE",
                route_key=route_key,
                body={},
                now=now,
                required=True,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return Response(status_code=acquired.status_code)
            await SessionService().delete(session, session_id=session_id, user_id=user_id)
            assert isinstance(acquired, AcquiredIdempotencyRecord)
            await idempotency.complete(
                session, record_id=acquired.record_id, status_code=204, body={}, now=now
            )
    except (
        CourseNotFoundError,
        CourseAccessDeniedError,
        CourseRoleRequiredError,
        SessionStateConflictError,
    ) as exc:
        _raise_domain_error(exc)
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    return Response(status_code=204)


@router.post(
    "/sessions/{session_id}/start",
    response_model=LectureSessionResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def start_session(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> LectureSessionResponse:
    try:
        async with transaction(session):
            lecture_session = await _service(settings).start(
                session, session_id=session_id, user_id=user_id
            )
    except (
        CourseNotFoundError,
        CourseAccessDeniedError,
        CourseRoleRequiredError,
        SessionStateConflictError,
        MaterialProcessingActiveError,
    ) as exc:
        _raise_domain_error(exc)
    return _project(lecture_session)


@router.post(
    "/sessions/{session_id}/end",
    status_code=202,
    response_model=SessionEndAcceptedResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def end_session(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    idempotency: RequiredIdempotency,
    idempotency_key: RequiredIdempotencyHeader,
) -> SessionEndAcceptedResponse | JSONResponse:
    now = datetime.now(UTC)
    route_key = "/api/v1/sessions/{session_id}/end"
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                method="POST",
                route_key=route_key,
                body={},
                now=now,
                required=True,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return JSONResponse(status_code=acquired.status_code, content=acquired.body)
            ended = await _service(settings).end(
                session,
                session_id=session_id,
                user_id=user_id,
                idempotency=idempotency,
                now=now,
            )
            result = SessionEndAcceptedResponse(
                session=_project(ended.lecture_session),
                recording=None,
                jobs=[
                    project_ai_job(job)
                    for job in (ended.coordinator, ended.final_clustering)
                    if job is not None
                ],
            )
            assert isinstance(acquired, AcquiredIdempotencyRecord)
            await idempotency.complete(
                session,
                record_id=acquired.record_id,
                status_code=202,
                body=result.model_dump(mode="json"),
                now=now,
            )
    except (
        CourseNotFoundError,
        CourseAccessDeniedError,
        CourseRoleRequiredError,
        SessionStateConflictError,
    ) as exc:
        _raise_domain_error(exc)
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    return result
