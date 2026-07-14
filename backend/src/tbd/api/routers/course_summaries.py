"""Course-wide shared FINAL Summary archive endpoint."""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import get_current_user_id, get_db_session, get_settings
from tbd.core.config import Settings
from tbd.core.errors import ApiError
from tbd.models.materials import TranscriptSegment
from tbd.schemas.course_summaries import (
    CourseFinalSummaryResponse,
    CourseSummaryArchiveItemResponse,
    CourseSummaryArchiveResponse,
)
from tbd.schemas.errors import ErrorResponse
from tbd.services.course_summaries import (
    CourseSummaryService,
    InvalidCourseSummaryCursorError,
)
from tbd.services.courses import CourseAccessDeniedError, CourseNotFoundError
from tbd.services.personal_ai import summary_response

router = APIRouter(tags=["Courses", "Summaries"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def _raise_archive_error(error: Exception) -> NoReturn:
    if isinstance(error, CourseNotFoundError):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 Course를 찾을 수 없습니다.") from error
    if isinstance(error, CourseAccessDeniedError):
        raise ApiError(
            403,
            "COURSE_ACCESS_DENIED",
            "이 Course에 접근할 권한이 없습니다.",
        ) from error
    if isinstance(error, InvalidCourseSummaryCursorError):
        raise ApiError(400, "INVALID_CURSOR", "AI 요약 목록 cursor를 확인해 주세요.") from error
    raise error


async def _summary_response(
    session: AsyncSession,
    summary: object,
) -> CourseFinalSummaryResponse:
    start_sequence = await session.scalar(
        select(TranscriptSegment.sequence).where(
            TranscriptSegment.id == summary.source_start_segment_id
        )
    )
    end_sequence = await session.scalar(
        select(TranscriptSegment.sequence).where(
            TranscriptSegment.id == summary.source_end_segment_id
        )
    )
    if start_sequence is None or end_sequence is None:
        raise RuntimeError("FINAL Summary segment provenance is unavailable")
    projected = summary_response(
        summary,
        start_sequence=int(start_sequence),
        end_sequence=int(end_sequence),
    )
    return CourseFinalSummaryResponse.model_validate(projected.model_dump())


@router.get(
    "/courses/{course_id}/summaries",
    operation_id="listCourseSummaryArchive",
    response_model=CourseSummaryArchiveResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def list_course_summary_archive(
    course_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CourseSummaryArchiveResponse:
    """Return public FINAL Summary state without private LIVE or Chat data."""

    try:
        result = await CourseSummaryService(
            auth_secret=settings.auth_secret_key.get_secret_value()
        ).list_for_member(
            session,
            course_id=course_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )
    except (CourseNotFoundError, CourseAccessDeniedError, InvalidCourseSummaryCursorError) as exc:
        _raise_archive_error(exc)

    items: list[CourseSummaryArchiveItemResponse] = []
    for item in result.items:
        projected = (
            await _summary_response(session, item.summary) if item.summary is not None else None
        )
        items.append(
            CourseSummaryArchiveItemResponse(
                session=item.lecture_session,
                state=item.state,
                summary=projected,
                summary_url=(
                    f"/api/v1/summaries/{projected.id}" if projected is not None else None
                ),
            )
        )
    return CourseSummaryArchiveResponse(items=items, next_cursor=result.next_cursor)
