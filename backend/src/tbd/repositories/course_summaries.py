"""Persistence queries for the Course-level shared FINAL Summary archive."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.courses import Course, CourseMember
from tbd.models.sessions import LectureSession


@dataclass(frozen=True, slots=True)
class CourseSummaryArchivePosition:
    """The final Session in an active-first Course Summary page."""

    phase: int
    session_started_at: datetime
    session_id: UUID


class CourseSummaryRepository:
    """Keep Course authorization and stable Session pagination in SQL."""

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

    async def list_archive_sessions(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        after: CourseSummaryArchivePosition | None,
        limit: int,
    ) -> list[LectureSession]:
        """Return PROCESSING first, then stable completed history."""

        archive_phase = case((LectureSession.status == "PROCESSING", 0), else_=1)
        statement = select(LectureSession).where(
            LectureSession.course_id == course_id,
            LectureSession.status.in_(("PROCESSING", "COMPLETED")),
        )
        if after is not None:
            if after.phase == 0:
                # A Course can have only one active Session.  Once that Session
                # has been returned, freeze it out of this cursor even if it
                # moves to COMPLETED before the next page is read.  A new active
                # Session belongs to a later archive snapshot.
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
                    LectureSession.started_at.desc(),
                    LectureSession.id.desc(),
                ).limit(limit)
            )
        )
