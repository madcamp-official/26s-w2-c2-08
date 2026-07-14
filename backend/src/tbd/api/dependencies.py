"""Request-scoped dependencies shared by API routers."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.core.config import Settings
from tbd.core.crypto import CourseJoinCodeCodec
from tbd.core.errors import ApiError
from tbd.db import Database
from tbd.models.users import User
from tbd.providers.google_oidc import GoogleOIDCProvider
from tbd.repositories.courses import CourseRepository, CourseView
from tbd.repositories.idempotency import IdempotencyRepository
from tbd.services.auth_sessions import AuthSessionService, InvalidSessionError
from tbd.storage import Storage


def get_database(request: Request) -> Database:
    """Return the database resource owned by the current application."""

    return request.app.state.database


def get_settings(request: Request) -> Settings:
    """Return immutable process settings owned by the application."""

    return request.app.state.settings


def get_storage(request: Request) -> Storage:
    """Return the private object storage owned by the current application."""

    return request.app.state.storage


def get_google_oidc_provider(request: Request) -> GoogleOIDCProvider:
    """Return the configured or test-injected Google provider."""

    return request.app.state.google_oidc_provider


def require_allowed_origin(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Reject state-changing browser requests outside the exact allowlist."""

    if request.headers.get("Origin") not in settings.allowed_origins:
        raise ApiError(
            status_code=403,
            code="ORIGIN_NOT_ALLOWED",
            message="허용되지 않은 요청 출처입니다.",
        )


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a session without assigning commit ownership to the router."""

    database = get_database(request)
    async with database.session_factory() as session:
        yield session


async def get_course_authorization_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Use an isolated read session so mutation transactions start cleanly."""

    database = get_database(request)
    async with database.session_factory() as session:
        yield session


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    goal_session: Annotated[str | None, Cookie()] = None,
) -> User:
    """Resolve the current active user from the HttpOnly server session cookie."""

    if not goal_session:
        raise ApiError(
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
            message="로그인이 필요합니다.",
        )
    try:
        return await AuthSessionService(settings).authenticate(session, goal_session)
    except InvalidSessionError as exc:
        raise ApiError(
            status_code=401,
            code="INVALID_SESSION",
            message="로그인 세션이 만료되었거나 유효하지 않습니다.",
        ) from exc


async def get_current_user_id(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UUID:
    """Project the verified server-session user to the ID expected by services."""

    return current_user.id


def get_idempotency_repository(request: Request) -> IdempotencyRepository:
    """Return the configured encrypted response repository or fail closed."""

    repository = request.app.state.idempotency_repository
    if repository is None:
        raise ApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="멱등성 응답 암호화 설정을 사용할 수 없습니다.",
        )
    return repository


def get_optional_idempotency_repository(request: Request) -> IdempotencyRepository | None:
    """Return optional idempotency support for endpoints with an optional header."""

    return request.app.state.idempotency_repository


def get_course_join_code_codec(request: Request) -> CourseJoinCodeCodec:
    """Return independent Course join-code crypto or fail closed."""

    codec = request.app.state.course_join_code_codec
    if codec is None:
        raise ApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="Course 참여 코드 보안 설정을 사용할 수 없습니다.",
        )
    return codec


async def require_course_member(
    course_id: str,
    session: Annotated[AsyncSession, Depends(get_course_authorization_session)],
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> CourseView:
    """Authorize an existing Course through the current user's membership."""

    try:
        parsed_course_id = UUID(course_id)
    except ValueError as exc:
        raise ApiError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="요청한 리소스를 찾을 수 없습니다.",
        ) from exc
    repository = CourseRepository()
    view = await repository.get_view_for_user(
        session,
        course_id=parsed_course_id,
        user_id=user_id,
    )
    if view is not None:
        return view
    if await repository.course_exists(session, parsed_course_id):
        raise ApiError(
            status_code=403,
            code="COURSE_ACCESS_DENIED",
            message="이 Course에 접근할 권한이 없습니다.",
        )
    raise ApiError(
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        message="요청한 리소스를 찾을 수 없습니다.",
    )


async def require_course_professor(
    view: Annotated[CourseView, Depends(require_course_member)],
) -> CourseView:
    """Require the immutable Course professor role for owner controls."""

    if view.role != "PROFESSOR":
        raise ApiError(
            status_code=403,
            code="ROLE_REQUIRED",
            message="Course를 처음 생성한 교수자만 수행할 수 있습니다.",
            details={"required_role": "COURSE_CREATOR_PROFESSOR"},
        )
    return view
