"""Persistence queries for Course aggregates and per-Course membership."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.courses import Course, CourseMember
from tbd.models.sessions import LectureSession

ACTIVE_SESSION_STATES = ("READY", "LIVE", "PROCESSING")


@dataclass(frozen=True)
class CourseView:
    """A Course projected for one member, with its optional active class."""

    course: Course
    role: str
    current_session: LectureSession | None


class CourseRepository:
    """Keep Course lookup, membership, and row-lock details out of services."""

    async def get_view_for_user(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
    ) -> CourseView | None:
        row = (
            await session.execute(
                select(Course, CourseMember.role, LectureSession)
                .join(
                    CourseMember,
                    and_(
                        CourseMember.course_id == Course.id,
                        CourseMember.user_id == user_id,
                    ),
                )
                .outerjoin(
                    LectureSession,
                    and_(
                        LectureSession.course_id == Course.id,
                        LectureSession.status.in_(ACTIVE_SESSION_STATES),
                    ),
                )
                .where(Course.id == course_id)
            )
        ).one_or_none()
        if row is None:
            return None
        course, role, current_session = row
        return CourseView(course=course, role=role, current_session=current_session)

    async def course_exists(self, session: AsyncSession, course_id: UUID) -> bool:
        return (await session.scalar(select(Course.id).where(Course.id == course_id))) is not None

    async def lock_by_join_code_hash(
        self,
        session: AsyncSession,
        lookup_hash: bytes,
    ) -> Course | None:
        return await session.scalar(
            select(Course).where(Course.join_code_lookup_hash == lookup_hash).with_for_update()
        )

    async def lock_course(self, session: AsyncSession, course_id: UUID) -> Course | None:
        return await session.scalar(select(Course).where(Course.id == course_id).with_for_update())

    async def get_membership(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
    ) -> CourseMember | None:
        return await session.get(CourseMember, (course_id, user_id))

    async def lookup_hash_exists(self, session: AsyncSession, lookup_hash: bytes) -> bool:
        return (
            await session.scalar(
                select(Course.id).where(Course.join_code_lookup_hash == lookup_hash)
            )
        ) is not None
