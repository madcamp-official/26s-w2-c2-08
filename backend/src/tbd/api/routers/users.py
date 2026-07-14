"""Authenticated current-user endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import get_current_user, get_db_session, require_allowed_origin
from tbd.core.errors import ApiError
from tbd.db import transaction
from tbd.models.users import User
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.users import UserResponse
from tbd.services.lifecycle import (
    AccountOwnedCourseError,
    LifecycleResourceNotFoundError,
    LifecycleService,
)

router = APIRouter(tags=["Users"])
CurrentUser = Annotated[User, Depends(get_current_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
REQUEST_ID_RESPONSE_HEADER = {
    "X-Request-ID": {
        "description": "요청 추적용 식별자. 요청 값을 수용하거나 서버가 생성한다.",
        "schema": {"type": "string"},
    }
}


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        200: {"headers": REQUEST_ID_RESPONSE_HEADER},
        401: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
    },
)
async def get_me(user: CurrentUser) -> UserResponse:
    """Return the current user without deriving an account-wide course role."""

    return UserResponse(
        id=user.id,
        display_name=user.display_name,
        email=user.primary_email,
        avatar_url=user.avatar_url,
    )


@router.delete(
    "/me",
    status_code=204,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
        403: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
        409: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
    },
)
async def withdraw_me(
    response: Response,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    """Irreversibly anonymize the account after its owner Courses are removed."""

    try:
        async with transaction(session):
            await LifecycleService().withdraw_account(
                session,
                user_id=user.id,
                now=datetime.now(UTC),
            )
    except AccountOwnedCourseError as exc:
        raise ApiError(
            409,
            "OWNED_COURSE_REQUIRES_DELETION",
            "생성한 Course를 먼저 삭제한 뒤 계정을 탈퇴할 수 있습니다.",
        ) from exc
    except LifecycleResourceNotFoundError as exc:
        raise ApiError(
            401, "INVALID_SESSION", "로그인 세션이 만료되었거나 유효하지 않습니다."
        ) from exc
    response.delete_cookie(key="goal_session", path="/")
    response.status_code = 204
    return response
