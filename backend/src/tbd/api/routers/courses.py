"""Course, membership, and join-code HTTP endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_course_join_code_codec,
    get_current_user_id,
    get_db_session,
    get_idempotency_repository,
    get_optional_idempotency_repository,
    require_allowed_origin,
    require_course_member,
    require_course_professor,
)
from tbd.core.crypto import CourseJoinCodeCodec
from tbd.core.errors import ApiError
from tbd.core.request_hash import canonical_request_hash, idempotency_key_hash
from tbd.db import transaction
from tbd.repositories.courses import CourseView
from tbd.repositories.idempotency import (
    AcquiredIdempotencyRecord,
    IdempotencyKeyReusedError,
    IdempotencyRepository,
    IdempotencyRequest,
    ProcessingIdempotencyRecord,
    ReplayIdempotencyRecord,
)
from tbd.schemas.courses import (
    CourseCreateRequest,
    CourseJoinRequest,
    CourseListResponse,
    CourseResponse,
    CourseRoleFilter,
)
from tbd.schemas.errors import ErrorResponse
from tbd.services.courses import (
    CourseAccessDeniedError,
    CourseNotFoundError,
    CourseRoleRequiredError,
    CourseService,
    InvalidCourseCursorError,
    JoinCodeGenerationError,
    MembershipConflictError,
)

router = APIRouter(prefix="/courses", tags=["Courses"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
JoinCodeCodec = Annotated[CourseJoinCodeCodec, Depends(get_course_join_code_codec)]
OptionalIdempotency = Annotated[
    IdempotencyRepository | None,
    Depends(get_optional_idempotency_repository),
]
RequiredIdempotency = Annotated[IdempotencyRepository, Depends(get_idempotency_repository)]
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
RequiredIdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key")]
PROCESSING_LEASE = timedelta(seconds=60)


def _project_course(
    service: CourseService,
    view: CourseView,
    *,
    join_code: str | None = None,
) -> CourseResponse:
    visible_code = join_code
    if view.role == "PROFESSOR" and visible_code is None:
        visible_code = service.reveal_join_code(view.course)
    fields = {
        "id": view.course.id,
        "title": view.course.title,
        "semester": view.course.semester,
        "role": view.role,
        "current_session": view.current_session,
        "created_at": view.course.created_at,
    }
    if view.role == "PROFESSOR":
        fields["join_code"] = visible_code
    return CourseResponse.model_validate(fields)


def _raise_idempotency_in_progress() -> None:
    raise ApiError(
        status_code=409,
        code="IDEMPOTENCY_REQUEST_IN_PROGRESS",
        message="동일한 요청을 처리하고 있습니다. 잠시 후 다시 시도해 주세요.",
    )


async def _acquire_optional_idempotency(
    session: AsyncSession,
    repository: IdempotencyRepository | None,
    *,
    user_id: UUID,
    key: str | None,
    route_key: str,
    body: dict[str, str],
    now: datetime,
) -> AcquiredIdempotencyRecord | ReplayIdempotencyRecord | None:
    if key is None:
        return None
    if repository is None:
        raise ApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="멱등성 응답 암호화 설정을 사용할 수 없습니다.",
        )
    try:
        key_hash = idempotency_key_hash(key)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.") from exc
    acquired = await repository.acquire(
        session,
        IdempotencyRequest(
            user_id=user_id,
            method="POST",
            route_key=route_key,
            key_hash=key_hash,
            request_hash=canonical_request_hash("POST", route_key, body),
        ),
        now=now,
        processing_lease=PROCESSING_LEASE,
    )
    if isinstance(acquired, ProcessingIdempotencyRecord):
        _raise_idempotency_in_progress()
    assert isinstance(acquired, (AcquiredIdempotencyRecord, ReplayIdempotencyRecord))
    return acquired


@router.get(
    "",
    response_model=CourseListResponse,
    response_model_exclude_unset=True,
    responses={503: {"model": ErrorResponse}},
)
async def list_courses(
    session: DatabaseSession,
    user_id: CurrentUserId,
    codec: JoinCodeCodec,
    role: Annotated[CourseRoleFilter, Query()] = "ALL",
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CourseListResponse:
    """Return only the current user's Courses in a stable keyset order."""

    service = CourseService(codec)
    try:
        result = await service.list_for_user(
            session,
            user_id=user_id,
            role=role,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCourseCursorError as exc:
        raise ApiError(400, "INVALID_CURSOR", "목록 커서를 다시 확인해 주세요.") from exc
    return CourseListResponse(
        items=[_project_course(service, view) for view in result.views],
        next_cursor=result.next_cursor,
    )


@router.post(
    "",
    status_code=201,
    response_model=CourseResponse,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def create_course(
    payload: CourseCreateRequest,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUserId,
    codec: JoinCodeCodec,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader = None,
) -> CourseResponse | JSONResponse:
    """Create one Course and its immutable professor membership atomically."""

    service = CourseService(codec)
    now = datetime.now(UTC)
    body = payload.model_dump(mode="json")
    try:
        async with transaction(session):
            acquired = await _acquire_optional_idempotency(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                route_key="/api/v1/courses",
                body=body,
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return JSONResponse(status_code=acquired.status_code, content=acquired.body)
            view, join_code = await service.create(session, user_id=user_id, **body)
            result = _project_course(service, view, join_code=join_code)
            if isinstance(acquired, AcquiredIdempotencyRecord):
                assert idempotency is not None
                await idempotency.complete(
                    session,
                    record_id=acquired.record_id,
                    status_code=201,
                    body=result.model_dump(mode="json", exclude_unset=True),
                    now=now,
                )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except JoinCodeGenerationError as exc:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "참여 코드를 발급하지 못했습니다.") from exc
    response.headers["Location"] = f"/api/v1/courses/{result.id}"
    return result


@router.post(
    "/join",
    status_code=201,
    response_model=CourseResponse,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def join_course(
    payload: CourseJoinRequest,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUserId,
    codec: JoinCodeCodec,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader = None,
) -> CourseResponse | JSONResponse:
    """Create a student membership or return an existing student membership."""

    service = CourseService(codec)
    now = datetime.now(UTC)
    body = payload.model_dump(mode="json")
    try:
        async with transaction(session):
            acquired = await _acquire_optional_idempotency(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                route_key="/api/v1/courses/join",
                body=body,
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return JSONResponse(status_code=acquired.status_code, content=acquired.body)
            joined = await service.join(
                session,
                user_id=user_id,
                raw_join_code=payload.join_code,
            )
            result = _project_course(service, joined.view)
            status_code = 201 if joined.created else 200
            if isinstance(acquired, AcquiredIdempotencyRecord):
                assert idempotency is not None
                await idempotency.complete(
                    session,
                    record_id=acquired.record_id,
                    status_code=status_code,
                    body=result.model_dump(mode="json", exclude_unset=True),
                    now=now,
                )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except CourseNotFoundError as exc:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "참여 코드를 확인해 주세요.") from exc
    except MembershipConflictError as exc:
        raise ApiError(
            409,
            "MEMBERSHIP_CONFLICT",
            "이미 이 Course의 교수자입니다.",
            details={"existing_role": "PROFESSOR"},
        ) from exc
    if joined.created:
        response.headers["Location"] = f"/api/v1/courses/{result.id}"
    else:
        response.status_code = 200
    return result


@router.get(
    "/{course_id}",
    response_model=CourseResponse,
    response_model_exclude_unset=True,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def get_course(
    view: Annotated[CourseView, Depends(require_course_member)],
    codec: JoinCodeCodec,
) -> CourseResponse:
    """Return Course detail while omitting the code from student responses."""

    return _project_course(CourseService(codec), view)


@router.post(
    "/{course_id}/join-code/rotate",
    response_model=CourseResponse,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def rotate_course_join_code(
    professor_view: Annotated[CourseView, Depends(require_course_professor)],
    session: DatabaseSession,
    user_id: CurrentUserId,
    codec: JoinCodeCodec,
    idempotency: RequiredIdempotency,
    idempotency_key: RequiredIdempotencyHeader,
) -> CourseResponse | JSONResponse:
    """Replace the owner-visible code and invalidate the previous code atomically."""

    service = CourseService(codec)
    now = datetime.now(UTC)
    route_key = "/api/v1/courses/{course_id}/join-code/rotate"
    try:
        key_hash = idempotency_key_hash(idempotency_key)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.") from exc
    request = IdempotencyRequest(
        user_id=user_id,
        method="POST",
        route_key=route_key,
        key_hash=key_hash,
        request_hash=canonical_request_hash("POST", route_key, {}),
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
                _raise_idempotency_in_progress()
            assert isinstance(acquired, AcquiredIdempotencyRecord)
            view, join_code = await service.rotate_join_code(
                session,
                course_id=professor_view.course.id,
                user_id=user_id,
            )
            result = _project_course(service, view, join_code=join_code)
            await idempotency.complete(
                session,
                record_id=acquired.record_id,
                status_code=200,
                body=result.model_dump(mode="json", exclude_unset=True),
                now=now,
            )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except CourseNotFoundError as exc:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 리소스를 찾을 수 없습니다.") from exc
    except CourseAccessDeniedError as exc:
        raise ApiError(403, "COURSE_ACCESS_DENIED", "이 Course에 접근할 권한이 없습니다.") from exc
    except CourseRoleRequiredError as exc:
        raise ApiError(
            403,
            "ROLE_REQUIRED",
            "Course를 처음 생성한 교수자만 참여 코드를 회전할 수 있습니다.",
            details={"required_role": "COURSE_CREATOR_PROFESSOR"},
        ) from exc
    except JoinCodeGenerationError as exc:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "참여 코드를 발급하지 못했습니다.") from exc
    return result
