"""Authenticated current-user endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from tbd.api.dependencies import get_current_user
from tbd.models.users import User
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.users import UserResponse

router = APIRouter(tags=["Users"])
CurrentUser = Annotated[User, Depends(get_current_user)]
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
