"""REST recovery endpoints for durable final Transcript data."""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import get_current_user_id, get_db_session, get_settings
from tbd.core.config import Settings
from tbd.core.errors import ApiError
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.transcripts import (
    TranscriptSegmentResponse,
    TranscriptTimelinePageResponse,
    TranscriptVersionListResponse,
)
from tbd.services.transcripts import (
    InvalidTranscriptAnchorError,
    InvalidTranscriptCursorError,
    TranscriptAccessDeniedError,
    TranscriptNotFoundError,
    TranscriptService,
    TranscriptSessionNotFoundError,
)

router = APIRouter(tags=["Transcript"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def _service(settings: Settings) -> TranscriptService:
    return TranscriptService(settings)


def _raise_timeline_error(error: Exception) -> NoReturn:
    if isinstance(error, TranscriptSessionNotFoundError):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 class를 찾을 수 없습니다.") from error
    if isinstance(error, TranscriptAccessDeniedError):
        raise ApiError(
            403, "COURSE_ACCESS_DENIED", "이 Course에 접근할 권한이 없습니다."
        ) from error
    if isinstance(error, TranscriptNotFoundError):
        raise ApiError(
            404, "RESOURCE_NOT_FOUND", "요청한 Transcript를 찾을 수 없습니다."
        ) from error
    if isinstance(error, (InvalidTranscriptCursorError, InvalidTranscriptAnchorError)):
        raise ApiError(400, "INVALID_CURSOR", "Transcript 조회 기준을 확인해 주세요.") from error
    raise error


@router.get(
    "/sessions/{session_id}/transcript",
    response_model=TranscriptTimelinePageResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def list_session_transcript_timeline(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    transcript_version_id: Annotated[UUID | None, Query()] = None,
    start_sequence: Annotated[int | None, Query(ge=1)] = None,
    end_sequence: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TranscriptTimelinePageResponse:
    """Return final Segment and Gap state from one immutable version scope."""

    try:
        return await _service(settings).timeline(
            session,
            session_id=session_id,
            user_id=user_id,
            transcript_version_id=transcript_version_id,
            start_sequence=start_sequence,
            end_sequence=end_sequence,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_timeline_error(exc)


@router.get(
    "/sessions/{session_id}/transcript/versions",
    response_model=TranscriptVersionListResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def list_session_transcript_versions(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TranscriptVersionListResponse:
    """List visible provenance metadata with a Session-bound stable cursor."""

    try:
        page = await _service(settings).list_versions(
            session,
            session_id=session_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_timeline_error(exc)
    return TranscriptVersionListResponse(items=page.items, next_cursor=page.next_cursor)


@router.get(
    "/transcript-segments/{segment_id}",
    response_model=TranscriptSegmentResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_transcript_segment(
    segment_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> TranscriptSegmentResponse:
    """Resolve one final Segment without revealing out-of-course resource existence."""

    try:
        return await _service(settings).get_segment(session, segment_id=segment_id, user_id=user_id)
    except (
        TranscriptNotFoundError,
        TranscriptSessionNotFoundError,
        TranscriptAccessDeniedError,
    ) as exc:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 Transcript를 찾을 수 없습니다.") from exc
