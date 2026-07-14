"""Compact record-manifest HTTP endpoint."""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import get_current_user_id, get_db_session
from tbd.core.errors import ApiError
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.records import SessionRecordResponse
from tbd.services.records import (
    RecordAccessDeniedError,
    RecordNotFoundError,
    RecordService,
    RecordSessionStateError,
)

router = APIRouter(tags=["Records"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def _raise_record_error(error: Exception) -> NoReturn:
    if isinstance(error, RecordNotFoundError):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 class를 찾을 수 없습니다.") from error
    if isinstance(error, RecordAccessDeniedError):
        raise ApiError(403, "COURSE_ACCESS_DENIED", "이 Course에 접근할 권한이 없습니다.") from error
    if isinstance(error, RecordSessionStateError):
        raise ApiError(
            409,
            "SESSION_STATE_CONFLICT",
            "수업 기록은 정리 중이거나 완료된 class에서만 조회할 수 있습니다.",
        ) from error
    raise error


@router.get(
    "/sessions/{session_id}/record",
    response_model=SessionRecordResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def get_session_record(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> SessionRecordResponse:
    """Return a bounded record manifest; each linked collection loads independently."""

    try:
        return await RecordService().get_for_member(
            session, session_id=session_id, user_id=user_id
        )
    except Exception as exc:
        _raise_record_error(exc)
