"""Course-wide Transcript archive with opaque, transition-safe pagination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.materials import TranscriptVersion
from tbd.models.sessions import LectureSession
from tbd.repositories.transcripts import (
    CourseTranscriptArchivePosition,
    CourseTranscriptArchiveRepository,
)
from tbd.schemas.records import CourseTranscriptArchiveItem, RecordTranscriptIndex
from tbd.schemas.transcripts import TranscriptAggregateResponse
from tbd.services.course_archives import (
    CourseArchiveCursorCodec,
    InvalidCourseArchiveCursorError,
    JsonValue,
)
from tbd.services.courses import CourseAccessDeniedError, CourseNotFoundError
from tbd.services.transcripts import TranscriptService

COURSE_TRANSCRIPT_ARCHIVE_RESOURCE = "course_transcripts"
COURSE_TRANSCRIPT_ARCHIVE_SCOPE: dict[str, JsonValue] = {
    "session_statuses": ["LIVE", "PROCESSING", "COMPLETED"],
    "sort": ["active_first", "session_started_at_desc", "session_id_desc"],
    "projection": "record_transcript_index",
}


class InvalidCourseTranscriptArchiveCursorError(Exception):
    """The cursor is malformed or belongs to another Course archive scope."""


@dataclass(frozen=True, slots=True)
class CourseTranscriptArchiveResult:
    """One bounded class page and the next signed position."""

    items: list[CourseTranscriptArchiveItem]
    next_cursor: str | None


def _decode_position(position: list[JsonValue]) -> CourseTranscriptArchivePosition:
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
        return CourseTranscriptArchivePosition(
            phase=phase_value,
            session_started_at=started_at,
            session_id=UUID(session_id_value),
        )
    except (TypeError, ValueError) as exc:
        raise InvalidCourseArchiveCursorError from exc


def _encode_position(lecture_session: LectureSession) -> list[JsonValue]:
    if lecture_session.started_at is None:
        raise RuntimeError("visible Transcript archive classes require started_at")
    return [
        1 if lecture_session.status == "COMPLETED" else 0,
        lecture_session.started_at.isoformat(),
        str(lecture_session.id),
    ]


class CourseTranscriptArchiveService:
    """Authorize and project only compact, Course-visible Transcript state."""

    def __init__(
        self,
        *,
        auth_secret: str,
        repository: CourseTranscriptArchiveRepository | None = None,
        archive_cursors: CourseArchiveCursorCodec | None = None,
    ) -> None:
        self.repository = repository or CourseTranscriptArchiveRepository()
        self.archive_cursors = archive_cursors or CourseArchiveCursorCodec(auth_secret)

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> CourseTranscriptArchiveResult:
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
                position = self.archive_cursors.decode(
                    cursor=cursor,
                    course_id=course_id,
                    resource=COURSE_TRANSCRIPT_ARCHIVE_RESOURCE,
                    scope=COURSE_TRANSCRIPT_ARCHIVE_SCOPE,
                )
                after = _decode_position(position)
            except InvalidCourseArchiveCursorError as exc:
                raise InvalidCourseTranscriptArchiveCursorError from exc

        rows = await self.repository.list_course_sessions(
            session,
            course_id=course_id,
            after=after,
            limit=limit + 1,
        )
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            next_cursor = self.archive_cursors.encode(
                course_id=course_id,
                resource=COURSE_TRANSCRIPT_ARCHIVE_RESOURCE,
                scope=COURSE_TRANSCRIPT_ARCHIVE_SCOPE,
                position=_encode_position(page[-1]),
            )

        versions_by_session = await self.repository.versions_for_sessions(
            session,
            [lecture_session.id for lecture_session in page],
            [
                lecture_session.canonical_transcript_version_id
                for lecture_session in page
                if lecture_session.canonical_transcript_version_id is not None
            ],
        )
        selected_by_session: dict[UUID, TranscriptVersion] = {}
        for lecture_session in page:
            versions = versions_by_session.get(lecture_session.id, [])
            selected = self._selected_version(lecture_session, versions)
            if selected is not None:
                selected_by_session[lecture_session.id] = selected
        segment_counts, gap_counts = await self.repository.selected_item_counts(
            session,
            [version.id for version in selected_by_session.values()],
        )

        return CourseTranscriptArchiveResult(
            items=[
                CourseTranscriptArchiveItem(
                    session=lecture_session,
                    transcript=self._project_index(
                        lecture_session,
                        versions_by_session.get(lecture_session.id, []),
                        selected_by_session.get(lecture_session.id),
                        segment_counts=segment_counts,
                        gap_counts=gap_counts,
                    ),
                )
                for lecture_session in page
            ],
            next_cursor=next_cursor,
        )

    @staticmethod
    def _selected_version(
        lecture_session: LectureSession,
        versions: list[TranscriptVersion],
    ) -> TranscriptVersion | None:
        if not versions:
            return None
        canonical = next(
            (
                version
                for version in versions
                if version.id == lecture_session.canonical_transcript_version_id
            ),
            None,
        )
        if canonical is not None:
            return canonical
        current = versions[0]
        if current.source == "RECORDING" and current.status == "FINALIZING":
            return None
        return current

    @staticmethod
    def _project_index(
        lecture_session: LectureSession,
        versions: list[TranscriptVersion],
        selected: TranscriptVersion | None,
        *,
        segment_counts: dict[UUID, int],
        gap_counts: dict[UUID, int],
    ) -> RecordTranscriptIndex:
        base = f"/api/v1/sessions/{lecture_session.id}/transcript"
        if not versions or selected is None:
            return RecordTranscriptIndex(
                state=None,
                selected_version_id=None,
                segment_count=0,
                gap_count=0,
                timeline_url=base,
                versions_url=f"{base}/versions",
            )

        current = versions[0]
        canonical = next(
            (
                version
                for version in versions
                if version.id == lecture_session.canonical_transcript_version_id
            ),
            None,
        )
        aggregate = TranscriptAggregateResponse(
            session_id=lecture_session.id,
            status=current.status,
            current_version=TranscriptService._project_version(current, lecture_session),
            canonical_version_id=lecture_session.canonical_transcript_version_id,
            canonical_version=(
                TranscriptService._project_version(canonical, lecture_session)
                if canonical is not None
                else None
            ),
            updated_at=max(current.updated_at, lecture_session.updated_at),
        )
        return RecordTranscriptIndex(
            state=aggregate,
            selected_version_id=selected.id,
            segment_count=segment_counts.get(selected.id, 0),
            gap_count=gap_counts.get(selected.id, 0),
            timeline_url=f"{base}?transcript_version_id={selected.id}",
            versions_url=f"{base}/versions",
        )
