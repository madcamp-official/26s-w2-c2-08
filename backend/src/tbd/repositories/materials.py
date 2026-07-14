"""Persistence queries for Session-attached PDF materials."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.courses import Course, CourseMember
from tbd.models.enums import AIJobStatus, AIJobType, AIJobVisibility
from tbd.models.materials import LectureMaterial
from tbd.models.questions import AIJob
from tbd.models.sessions import LectureSession

ACTIVE_SESSION_STATES = ("READY", "LIVE", "PROCESSING")


@dataclass(frozen=True)
class CourseMaterialArchivePosition:
    """Last flat Material row in the Course archive's mixed sort order."""

    phase: int
    session_started_at: datetime | None
    session_id: UUID
    material_created_at: datetime
    material_id: UUID


@dataclass(frozen=True)
class CourseMaterialArchiveRow:
    """Publicly projectable Session and its currently attached Material."""

    lecture_session: LectureSession
    material: LectureMaterial


class MaterialRepository:
    """Keep Material lookup, pagination, and lock ordering out of services."""

    async def lock_session(self, session: AsyncSession, session_id: UUID) -> LectureSession | None:
        return await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )

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

    async def get_active_course(self, session: AsyncSession, course_id: UUID) -> Course | None:
        """Return only an externally visible Course without taking a write lock."""

        return await session.scalar(
            select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
        )

    async def list_course_archive(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        after: CourseMaterialArchivePosition | None,
        limit: int,
    ) -> list[CourseMaterialArchiveRow]:
        """Read a bounded flat archive page in active-first, class-grouped order."""

        archive_phase = case(
            (LectureSession.status.in_(ACTIVE_SESSION_STATES), 0),
            else_=1,
        )
        statement = (
            select(LectureSession, LectureMaterial)
            .join(LectureMaterial, LectureMaterial.session_id == LectureSession.id)
            .where(
                LectureSession.course_id == course_id,
                LectureSession.status.in_((*ACTIVE_SESSION_STATES, "COMPLETED")),
                LectureMaterial.detached_at.is_(None),
            )
        )
        if after is not None:
            material_after = or_(
                LectureMaterial.created_at > after.material_created_at,
                and_(
                    LectureMaterial.created_at == after.material_created_at,
                    LectureMaterial.id > after.material_id,
                ),
            )
            if after.phase == 0:
                # Once an active-class cursor has been issued, keep that class
                # as the frozen first group even if it transitions to
                # COMPLETED between pages. Newly created active classes are
                # intentionally outside this cursor's snapshot.
                archive_phase = case(
                    (LectureSession.id == after.session_id, 0),
                    else_=1,
                )
                statement = statement.where(
                    or_(
                        and_(
                            LectureSession.id == after.session_id,
                            material_after,
                        ),
                        and_(
                            LectureSession.status == "COMPLETED",
                            LectureSession.id != after.session_id,
                        ),
                    )
                )
            else:
                assert after.session_started_at is not None
                statement = statement.where(
                    LectureSession.status == "COMPLETED",
                    or_(
                        LectureSession.started_at < after.session_started_at,
                        and_(
                            LectureSession.started_at == after.session_started_at,
                            LectureSession.id < after.session_id,
                        ),
                        and_(
                            LectureSession.id == after.session_id,
                            material_after,
                        ),
                    ),
                )

        rows = (
            await session.execute(
                statement.order_by(
                    archive_phase.asc(),
                    LectureSession.started_at.desc().nullslast(),
                    LectureSession.id.desc(),
                    LectureMaterial.created_at.asc(),
                    LectureMaterial.id.asc(),
                ).limit(limit)
            )
        ).all()
        return [CourseMaterialArchiveRow(lecture_session=row[0], material=row[1]) for row in rows]

    async def list_active_for_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[LectureMaterial]:
        statement: Select[tuple[LectureMaterial]] = (
            select(LectureMaterial)
            .join(LectureSession, LectureSession.id == LectureMaterial.session_id)
            .join(Course, Course.id == LectureSession.course_id)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(
                LectureMaterial.session_id == session_id,
                LectureMaterial.detached_at.is_(None),
                Course.deleted_at.is_(None),
                CourseMember.user_id == user_id,
            )
        )
        if after is not None:
            created_at, material_id = after
            statement = statement.where(
                or_(
                    LectureMaterial.created_at > created_at,
                    and_(
                        LectureMaterial.created_at == created_at, LectureMaterial.id > material_id
                    ),
                )
            )
        return list(
            await session.scalars(
                statement.order_by(LectureMaterial.created_at, LectureMaterial.id).limit(limit)
            )
        )

    async def get_active_for_member(
        self,
        session: AsyncSession,
        *,
        material_id: UUID,
        user_id: UUID,
    ) -> LectureMaterial | None:
        return await session.scalar(
            select(LectureMaterial)
            .join(LectureSession, LectureSession.id == LectureMaterial.session_id)
            .join(Course, Course.id == LectureSession.course_id)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(
                LectureMaterial.id == material_id,
                LectureMaterial.detached_at.is_(None),
                Course.deleted_at.is_(None),
                CourseMember.user_id == user_id,
            )
        )

    async def lock_active_for_member(
        self,
        session: AsyncSession,
        *,
        material_id: UUID,
        user_id: UUID,
    ) -> LectureMaterial | None:
        return await session.scalar(
            select(LectureMaterial)
            .join(LectureSession, LectureSession.id == LectureMaterial.session_id)
            .join(Course, Course.id == LectureSession.course_id)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(
                LectureMaterial.id == material_id,
                LectureMaterial.detached_at.is_(None),
                Course.deleted_at.is_(None),
                CourseMember.user_id == user_id,
            )
            .with_for_update(of=LectureMaterial)
        )

    async def lock_material(
        self, session: AsyncSession, material_id: UUID
    ) -> LectureMaterial | None:
        return await session.scalar(
            select(LectureMaterial).where(LectureMaterial.id == material_id).with_for_update()
        )

    async def lock_job(self, session: AsyncSession, job_id: UUID) -> AIJob | None:
        return await session.scalar(select(AIJob).where(AIJob.id == job_id).with_for_update())

    async def next_due_material_job(self, session: AsyncSession, now: datetime) -> AIJob | None:
        """Read one candidate without locking before the aggregate lock sequence."""

        return await session.scalar(
            select(AIJob)
            .where(
                AIJob.job_type == AIJobType.MATERIAL_PROCESSING,
                AIJob.visibility == AIJobVisibility.SHARED,
                AIJob.status == AIJobStatus.PENDING,
                AIJob.available_at <= now,
                AIJob.target_material_id.is_not(None),
            )
            .order_by(AIJob.available_at, AIJob.created_at, AIJob.id)
            .limit(1)
        )

    async def active_count(self, session: AsyncSession, session_id: UUID) -> int:
        rows = await session.scalars(
            select(LectureMaterial.id)
            .where(
                LectureMaterial.session_id == session_id,
                LectureMaterial.detached_at.is_(None),
            )
            .order_by(LectureMaterial.id)
            .with_for_update()
        )
        return len(list(rows))

    async def active_display_names(self, session: AsyncSession, session_id: UUID) -> set[str]:
        rows = await session.scalars(
            select(LectureMaterial.display_name)
            .where(
                LectureMaterial.session_id == session_id,
                LectureMaterial.detached_at.is_(None),
            )
            .order_by(LectureMaterial.id)
            .with_for_update()
        )
        return set(rows)

    async def material_job(self, session: AsyncSession, material_id: UUID) -> AIJob | None:
        return await session.scalar(
            select(AIJob)
            .where(AIJob.target_material_id == material_id, AIJob.job_type == "MATERIAL_PROCESSING")
            .order_by(AIJob.created_at.desc())
            .limit(1)
            .with_for_update()
        )
