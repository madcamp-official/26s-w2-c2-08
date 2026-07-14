"""Course-level archive of shared FINAL Summary state and results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.knowledge import LectureSummary
from tbd.models.sessions import LectureSession
from tbd.repositories.course_summaries import (
    CourseSummaryArchivePosition,
    CourseSummaryRepository,
)
from tbd.schemas.records import FinalSummaryReason, FinalSummaryState
from tbd.services.course_archives import (
    CourseArchiveCursorCodec,
    InvalidCourseArchiveCursorError,
    JsonValue,
)
from tbd.services.courses import CourseAccessDeniedError, CourseNotFoundError
from tbd.services.personal_ai import PersonalAIService

COURSE_SUMMARY_ARCHIVE_RESOURCE: Final = "course_summaries"
COURSE_SUMMARY_ARCHIVE_SCOPE: Final[dict[str, JsonValue]] = {
    "requester_user_id": None,
    "session_statuses": ["PROCESSING", "COMPLETED"],
    "sort": ["processing_first", "session_started_at_desc", "session_id_desc"],
    "summary_type": "FINAL",
    "visibility": "COURSE_MEMBERS",
}


class InvalidCourseSummaryCursorError(Exception):
    """The cursor does not belong to this Course Summary archive."""


@dataclass(frozen=True, slots=True)
class CourseSummaryArchiveItem:
    """One class and its safely projected shared FINAL Summary state."""

    lecture_session: LectureSession
    state: FinalSummaryState
    summary: LectureSummary | None


@dataclass(frozen=True, slots=True)
class CourseSummaryArchiveResult:
    """One bounded Course Summary page."""

    items: list[CourseSummaryArchiveItem]
    next_cursor: str | None


def _decode_position(position: list[JsonValue]) -> CourseSummaryArchivePosition:
    try:
        if len(position) != 3:
            raise ValueError
        phase_value, started_at_value, session_id_value = position
        if type(phase_value) is not int or phase_value not in {0, 1}:
            raise ValueError
        if not isinstance(started_at_value, str) or not isinstance(session_id_value, str):
            raise ValueError
        started_at = datetime.fromisoformat(started_at_value)
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValueError
        return CourseSummaryArchivePosition(
            phase=phase_value,
            session_started_at=started_at,
            session_id=UUID(session_id_value),
        )
    except (TypeError, ValueError) as exc:
        raise InvalidCourseArchiveCursorError from exc


def _encode_position(lecture_session: LectureSession) -> list[JsonValue]:
    if lecture_session.started_at is None:
        raise RuntimeError("PROCESSING and COMPLETED Sessions require started_at")
    return [
        0 if lecture_session.status == "PROCESSING" else 1,
        lecture_session.started_at.isoformat(),
        str(lecture_session.id),
    ]


def _reason(reason: dict[str, str] | None) -> FinalSummaryReason | None:
    if reason is None:
        return None
    code = reason.get("code")
    if code == "NO_FINAL_TRANSCRIPT":
        return FinalSummaryReason(code=code, message="요약할 강의 내용이 없습니다.")
    if code == "SUMMARY_SOURCE_UNAVAILABLE":
        return FinalSummaryReason(
            code=code,
            message="Transcript 처리 문제로 요약을 만들지 못했습니다.",
        )
    # Provider and internal errors are intentionally reduced to a null reason.
    return None


class CourseSummaryService:
    """Authorize and project shared FINAL Summaries without private AI joins."""

    def __init__(
        self,
        *,
        auth_secret: str,
        repository: CourseSummaryRepository | None = None,
        archive_cursors: CourseArchiveCursorCodec | None = None,
        personal_ai: PersonalAIService | None = None,
    ) -> None:
        self.repository = repository or CourseSummaryRepository()
        self.archive_cursors = archive_cursors or CourseArchiveCursorCodec(auth_secret)
        self.personal_ai = personal_ai or PersonalAIService()

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> CourseSummaryArchiveResult:
        """Return public FINAL state for PROCESSING and COMPLETED classes."""

        if await self.repository.get_active_course(session, course_id) is None:
            raise CourseNotFoundError
        if (
            await self.repository.member_role(
                session,
                course_id=course_id,
                user_id=user_id,
            )
            is None
        ):
            raise CourseAccessDeniedError

        after = None
        if cursor is not None:
            try:
                after = _decode_position(
                    self.archive_cursors.decode(
                        cursor=cursor,
                        course_id=course_id,
                        resource=COURSE_SUMMARY_ARCHIVE_RESOURCE,
                        scope=COURSE_SUMMARY_ARCHIVE_SCOPE,
                    )
                )
            except InvalidCourseArchiveCursorError as exc:
                raise InvalidCourseSummaryCursorError from exc

        rows = await self.repository.list_archive_sessions(
            session,
            course_id=course_id,
            after=after,
            limit=limit + 1,
        )
        page, extra = rows[:limit], rows[limit:]
        items: list[CourseSummaryArchiveItem] = []
        for lecture_session in page:
            summaries, status, reason = await self.personal_ai.final_summary_state(
                session,
                lecture_session,
            )
            summary = summaries[0] if status == "AVAILABLE" and summaries else None
            items.append(
                CourseSummaryArchiveItem(
                    lecture_session=lecture_session,
                    state=FinalSummaryState(status=status, reason=_reason(reason)),
                    summary=summary,
                )
            )

        next_cursor = None
        if extra and page:
            next_cursor = self.archive_cursors.encode(
                course_id=course_id,
                resource=COURSE_SUMMARY_ARCHIVE_RESOURCE,
                scope=COURSE_SUMMARY_ARCHIVE_SCOPE,
                position=_encode_position(page[-1]),
            )
        return CourseSummaryArchiveResult(items=items, next_cursor=next_cursor)
