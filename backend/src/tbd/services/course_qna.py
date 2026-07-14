"""Authorization, cursor, and projection policies for the Course Q&A archive."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tbd.repositories.course_qna import (
    AI_REPRESENTATIVE_QUESTION,
    STUDENT_QUESTION,
    CourseQnaArchivePosition,
    CourseQnaArchiveRepository,
    CourseQnaArchiveRow,
)
from tbd.schemas.course_qna import (
    CourseArchiveAnswerOrganization,
    CourseArchiveCompletedAnswer,
    CourseQnaArchiveItem,
    CourseRepresentativeQuestionArchiveItem,
    CourseStudentQuestionArchiveItem,
)
from tbd.schemas.courses import LectureSessionSummary
from tbd.services.course_archives import (
    CourseArchiveCursorCodec,
    InvalidCourseArchiveCursorError,
    JsonValue,
)
from tbd.services.courses import CourseAccessDeniedError, CourseNotFoundError
from tbd.services.questions import QuestionService

COURSE_QNA_ARCHIVE_RESOURCE: Final = "course_qna"
COURSE_QNA_ARCHIVE_SCOPE: Final[dict[str, JsonValue]] = {
    "answer_status": "COMPLETED_ONLY",
    "representative_questions": "ANSWERED_ONLY",
    "session_statuses": ["READY", "LIVE", "PROCESSING", "COMPLETED"],
    "sort": [
        "active_first",
        "session_started_at_desc",
        "session_id_desc",
        "target_occurred_at_desc",
        "target_id_desc",
    ],
    "student_questions": "ALL",
}


class InvalidCourseQnaCursorError(Exception):
    """The cursor is malformed or belongs to another Course archive scope."""


@dataclass(frozen=True)
class CourseQnaArchiveResult:
    items: list[CourseQnaArchiveItem]
    next_cursor: str | None


def _decode_position(position: list[JsonValue]) -> CourseQnaArchivePosition:
    try:
        if len(position) != 6:
            raise ValueError
        (
            phase_value,
            started_at_value,
            session_id_value,
            occurred_at_value,
            target_id_value,
            frozen_session_id_value,
        ) = position
        if type(phase_value) is not int or phase_value not in {0, 1}:
            raise ValueError
        if started_at_value is None:
            started_at = None
        elif isinstance(started_at_value, str):
            started_at = datetime.fromisoformat(started_at_value)
            if started_at.tzinfo is None or started_at.utcoffset() is None:
                raise ValueError
        else:
            raise ValueError
        if phase_value == 1 and started_at is None:
            raise ValueError
        if not isinstance(occurred_at_value, str):
            raise ValueError
        occurred_at = datetime.fromisoformat(occurred_at_value)
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError
        if not isinstance(session_id_value, str) or not isinstance(target_id_value, str):
            raise ValueError
        if frozen_session_id_value is not None and not isinstance(frozen_session_id_value, str):
            raise ValueError
        return CourseQnaArchivePosition(
            phase=phase_value,
            session_started_at=started_at,
            session_id=UUID(session_id_value),
            occurred_at=occurred_at,
            target_id=UUID(target_id_value),
            frozen_session_id=(
                UUID(frozen_session_id_value) if frozen_session_id_value is not None else None
            ),
        )
    except (TypeError, ValueError) as exc:
        raise InvalidCourseQnaCursorError from exc


def _encode_position(
    row: CourseQnaArchiveRow,
    *,
    frozen_session_id: UUID | None,
) -> list[JsonValue]:
    return [
        row.phase,
        (
            row.lecture_session.started_at.isoformat()
            if row.lecture_session.started_at is not None
            else None
        ),
        str(row.lecture_session.id),
        row.occurred_at.isoformat(),
        str(row.target_id),
        str(frozen_session_id) if frozen_session_id is not None else None,
    ]


class CourseQnaArchiveService:
    """Expose read-only Q&A targets while reusing existing public projections."""

    def __init__(
        self,
        *,
        auth_secret: str,
        repository: CourseQnaArchiveRepository | None = None,
        cursors: CourseArchiveCursorCodec | None = None,
    ) -> None:
        self.repository = repository or CourseQnaArchiveRepository()
        self.cursors = cursors or CourseArchiveCursorCodec(auth_secret)

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> CourseQnaArchiveResult:
        course = await self.repository.get_active_course(session, course_id)
        if course is None:
            raise CourseNotFoundError
        role = await self.repository.member_role(
            session,
            course_id=course_id,
            user_id=user_id,
        )
        if role is None:
            raise CourseAccessDeniedError

        after = None
        if cursor is not None:
            try:
                after = _decode_position(
                    self.cursors.decode(
                        cursor=cursor,
                        course_id=course_id,
                        resource=COURSE_QNA_ARCHIVE_RESOURCE,
                        scope=COURSE_QNA_ARCHIVE_SCOPE,
                    )
                )
            except InvalidCourseArchiveCursorError as exc:
                raise InvalidCourseQnaCursorError from exc

        rows = await self.repository.list_course_archive(
            session,
            course_id=course_id,
            user_id=user_id,
            after=after,
            limit=limit + 1,
        )
        page, extra = rows[:limit], rows[limit:]
        items = [await self._project(session, row) for row in page]
        frozen_session_id = (
            after.frozen_session_id
            if after is not None
            else next(
                (row.lecture_session.id for row in rows if row.phase == 0),
                None,
            )
        )
        next_cursor = None
        if extra and page:
            next_cursor = self.cursors.encode(
                course_id=course_id,
                resource=COURSE_QNA_ARCHIVE_RESOURCE,
                scope=COURSE_QNA_ARCHIVE_SCOPE,
                position=_encode_position(
                    page[-1],
                    frozen_session_id=frozen_session_id,
                ),
            )
        return CourseQnaArchiveResult(items=items, next_cursor=next_cursor)

    async def _project(
        self,
        session: AsyncSession,
        row: CourseQnaArchiveRow,
    ) -> CourseQnaArchiveItem:
        session_summary = LectureSessionSummary.model_validate(row.lecture_session)
        record_url = f"/sessions/{row.lecture_session.id}"
        answer = None
        if row.answer is not None:
            if row.answer.completed_at is None:
                raise RuntimeError("completed archive Answer is missing completed_at")
            answer = CourseArchiveCompletedAnswer(
                id=row.answer.id,
                answer_type=(
                    "VOICE" if row.answer.source_transcript_version_id is not None else "TEXT"
                ),
                status="COMPLETED",
                text_content=row.answer.text_content,
                organization=(
                    CourseArchiveAnswerOrganization(content=row.organization_content)
                    if row.organization_content is not None
                    else None
                ),
                completed_at=row.answer.completed_at,
            )

        if row.target_type == STUDENT_QUESTION:
            if row.question is None:
                raise RuntimeError("student archive target is missing its Question")
            question = QuestionService.project_question(
                row.question,
                reacted_by_me=row.reacted_by_me,
            )
            return CourseStudentQuestionArchiveItem(
                target_type="STUDENT_QUESTION",
                session=session_summary,
                question=question,
                target_text_snapshot=(
                    row.answer.target_text_snapshot
                    if row.answer is not None
                    else row.question.content
                ),
                answer=answer,
                record_url=record_url,
                occurred_at=row.occurred_at,
            )

        if row.target_type != AI_REPRESENTATIVE_QUESTION or answer is None:
            raise RuntimeError("representative archive target is missing its completed Answer")
        return CourseRepresentativeQuestionArchiveItem(
            target_type="AI_REPRESENTATIVE_QUESTION",
            session=session_summary,
            representative_question_id=row.target_id,
            target_text_snapshot=row.answer.target_text_snapshot,
            answer=answer,
            record_url=record_url,
            occurred_at=row.occurred_at,
        )
