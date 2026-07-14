"""Request-scoped dependencies shared by API routers."""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.core.errors import ApiError
from tbd.db import Database
from tbd.repositories.idempotency import IdempotencyRepository


def get_database(request: Request) -> Database:
    """Return the database resource owned by the current application."""

    return request.app.state.database


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a session without assigning commit ownership to the router."""

    database = get_database(request)
    async with database.session_factory() as session:
        yield session


async def get_current_user_id() -> UUID:
    """Require the authentication PR to provide a verified current user identity.

    PR-05 replaces this boundary with the server-session dependency.  Keeping
    the default closed prevents Job state from being exposed before that work
    lands, while application and integration tests can override the dependency.
    """

    raise ApiError(
        status_code=401,
        code="AUTHENTICATION_REQUIRED",
        message="로그인이 필요합니다.",
    )


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
