"""Request-scoped dependencies shared by API routers."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.core.config import Settings
from tbd.core.errors import ApiError
from tbd.db import Database
from tbd.models.users import User
from tbd.providers.google_oidc import GoogleOIDCProvider
from tbd.repositories.idempotency import IdempotencyRepository
from tbd.services.auth_sessions import AuthSessionService, InvalidSessionError


def get_database(request: Request) -> Database:
    """Return the database resource owned by the current application."""

    return request.app.state.database


def get_settings(request: Request) -> Settings:
    """Return immutable process settings owned by the application."""

    return request.app.state.settings


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
