"""Persistence queries and locks for the lecture-session lifecycle."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.courses import Course, CourseMember
from tbd.models.materials import LectureMaterial
from tbd.models.sessions import LectureSession

ACTIVE_SESSION_STATES = ("READY", "LIVE", "PROCESSING")


class SessionRepository:
    """Keep lifecycle locking and Course membership joins out of services."""

    async def lock_course(self, session: AsyncSession, course_id: UUID) -> Course | None:
        return await session.scalar(
            select(Course)
            .where(Course.id == course_id, Course.deleted_at.is_(None))
            .with_for_update()
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

    async def lock_session(self, session: AsyncSession, session_id: UUID) -> LectureSession | None:
        return await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )

    async def get_session(self, session: AsyncSession, session_id: UUID) -> LectureSession | None:
        return await session.get(LectureSession, session_id)

    async def active_session_exists(self, session: AsyncSession, course_id: UUID) -> bool:
        return (
            await session.scalar(
                select(LectureSession.id).where(
                    LectureSession.course_id == course_id,
                    LectureSession.status.in_(ACTIVE_SESSION_STATES),
                )
            )
        ) is not None

    async def list_for_course(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        status: str | None,
        limit: int,
    ) -> list[LectureSession]:
        statement = select(LectureSession).where(LectureSession.course_id == course_id)
        if status is not None:
            statement = statement.where(LectureSession.status == status)
        return list(
            await session.scalars(
                statement.order_by(
                    LectureSession.lecture_date.desc(),
                    LectureSession.started_at.desc().nullsfirst(),
                    LectureSession.id.desc(),
                ).limit(limit)
            )
        )

    async def processing_material_count(self, session: AsyncSession, session_id: UUID) -> int:
        rows = await session.scalars(
            select(LectureMaterial.id)
            .where(
                LectureMaterial.session_id == session_id,
                LectureMaterial.detached_at.is_(None),
                LectureMaterial.processing_status == "PROCESSING",
            )
            .order_by(LectureMaterial.id)
            .with_for_update()
        )
        return len(list(rows))

    async def create(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
        title: str,
        lecture_date: date,
        now: datetime,
    ) -> LectureSession:
        lecture_session = LectureSession(
            course_id=course_id,
            created_by_user_id=user_id,
            title=title,
            lecture_date=lecture_date,
            status="READY",
            version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(lecture_session)
        await session.flush()
        return lecture_session
