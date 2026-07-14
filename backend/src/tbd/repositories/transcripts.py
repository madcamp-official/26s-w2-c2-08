"""Persistence queries for Course transcript archive projections."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.courses import Course, CourseMember
from tbd.models.materials import TranscriptGap, TranscriptSegment, TranscriptVersion
from tbd.models.sessions import LectureSession

COURSE_TRANSCRIPT_ACTIVE_STATES = ("LIVE", "PROCESSING")
COURSE_TRANSCRIPT_VISIBLE_STATES = (*COURSE_TRANSCRIPT_ACTIVE_STATES, "COMPLETED")


@dataclass(frozen=True, slots=True)
class CourseTranscriptArchivePosition:
    """The last class in an active-first Course transcript page."""

    phase: int
    session_started_at: datetime
    session_id: UUID


class CourseTranscriptArchiveRepository:
    """Keep Course scoping and bounded transcript archive reads in SQL."""

    async def get_active_course(self, session: AsyncSession, course_id: UUID) -> Course | None:
        return await session.scalar(
            select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
        )

    async def member_role(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
    ) -> str | None:
        return await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == course_id,
                CourseMember.user_id == user_id,
            )
        )

    async def list_course_sessions(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        after: CourseTranscriptArchivePosition | None,
        limit: int,
    ) -> list[LectureSession]:
        """Return one bounded page with a transition-safe active-class boundary."""

        archive_phase = case(
            (LectureSession.status.in_(COURSE_TRANSCRIPT_ACTIVE_STATES), 0),
            else_=1,
        )
        statement = select(LectureSession).where(
            LectureSession.course_id == course_id,
            LectureSession.status.in_(COURSE_TRANSCRIPT_VISIBLE_STATES),
        )
        if after is not None:
            if after.phase == 0:
                # The active class can become COMPLETED between pages. Exclude
                # its ID so the class already returned before the transition is
                # not repeated, and freeze any later active class out of this
                # cursor traversal.
                archive_phase = case(
                    (LectureSession.id == after.session_id, 0),
                    else_=1,
                )
                statement = statement.where(
                    LectureSession.status == "COMPLETED",
                    LectureSession.id != after.session_id,
                )
            else:
                statement = statement.where(
                    LectureSession.status == "COMPLETED",
                    or_(
                        LectureSession.started_at < after.session_started_at,
                        and_(
                            LectureSession.started_at == after.session_started_at,
                            LectureSession.id < after.session_id,
                        ),
                    ),
                )
        return list(
            await session.scalars(
                statement.order_by(
                    archive_phase.asc(),
                    LectureSession.started_at.desc().nullslast(),
                    LectureSession.id.desc(),
                ).limit(limit)
            )
        )

    async def versions_for_sessions(
        self,
        session: AsyncSession,
        session_ids: Sequence[UUID],
        canonical_version_ids: Sequence[UUID],
    ) -> dict[UUID, list[TranscriptVersion]]:
        if not session_ids:
            return {}
        ranked = (
            select(
                TranscriptVersion.id.label("version_id"),
                func.row_number()
                .over(
                    partition_by=TranscriptVersion.session_id,
                    order_by=(TranscriptVersion.version.desc(), TranscriptVersion.id.desc()),
                )
                .label("position"),
            )
            .where(TranscriptVersion.session_id.in_(session_ids))
            .subquery()
        )
        versions = list(
            await session.scalars(
                select(TranscriptVersion)
                .join(ranked, ranked.c.version_id == TranscriptVersion.id)
                .where(
                    or_(
                        ranked.c.position == 1,
                        TranscriptVersion.id.in_(canonical_version_ids),
                    )
                )
                .order_by(
                    TranscriptVersion.session_id,
                    TranscriptVersion.version.desc(),
                    TranscriptVersion.id.desc(),
                )
            )
        )
        result: dict[UUID, list[TranscriptVersion]] = {}
        for version in versions:
            result.setdefault(version.session_id, []).append(version)
        return result

    async def selected_item_counts(
        self,
        session: AsyncSession,
        version_ids: Sequence[UUID],
    ) -> tuple[dict[UUID, int], dict[UUID, int]]:
        """Count only the selected public version; never scan staging rows for output."""

        if not version_ids:
            return {}, {}
        segment_rows = (
            await session.execute(
                select(TranscriptSegment.transcript_version_id, func.count())
                .where(TranscriptSegment.transcript_version_id.in_(version_ids))
                .group_by(TranscriptSegment.transcript_version_id)
            )
        ).all()
        gap_rows = (
            await session.execute(
                select(TranscriptGap.transcript_version_id, func.count())
                .where(TranscriptGap.transcript_version_id.in_(version_ids))
                .group_by(TranscriptGap.transcript_version_id)
            )
        ).all()
        return (
            {row[0]: int(row[1]) for row in segment_rows},
            {row[0]: int(row[1]) for row in gap_rows},
        )
