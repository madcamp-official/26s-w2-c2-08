"""Question, reaction, and keyset-query persistence operations."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.courses import CourseMember
from tbd.models.questions import AIJob, Question, QuestionClusteringState, QuestionReaction
from tbd.models.sessions import LectureSession


@dataclass(frozen=True)
class QuestionCursorPosition:
    created_at: datetime
    question_id: UUID
    reaction_count: int | None = None


class QuestionRepository:
    """Keep locking, membership joins, and keyset pagination out of services."""

    async def get_session(self, session: AsyncSession, session_id: UUID) -> LectureSession | None:
        return await session.get(LectureSession, session_id)

    async def lock_session(self, session: AsyncSession, session_id: UUID) -> LectureSession | None:
        return await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )

    async def member_role(
        self, session: AsyncSession, *, course_id: UUID, user_id: UUID
    ) -> str | None:
        return await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == course_id,
                CourseMember.user_id == user_id,
            )
        )

    async def get_question(self, session: AsyncSession, question_id: UUID) -> Question | None:
        return await session.get(Question, question_id)

    async def lock_question(self, session: AsyncSession, question_id: UUID) -> Question | None:
        return await session.scalar(
            select(Question).where(Question.id == question_id).with_for_update()
        )

    async def lock_clustering_state(
        self, session: AsyncSession, session_id: UUID
    ) -> QuestionClusteringState | None:
        return await session.scalar(
            select(QuestionClusteringState)
            .where(QuestionClusteringState.session_id == session_id)
            .with_for_update()
        )

    async def active_clustering_job(self, session: AsyncSession, session_id: UUID) -> AIJob | None:
        return await session.scalar(
            select(AIJob)
            .where(
                AIJob.session_id == session_id,
                AIJob.job_type == "QUESTION_CLUSTERING",
                AIJob.status.in_(("PENDING", "RUNNING")),
            )
            .order_by(AIJob.created_at.desc(), AIJob.id.desc())
            .with_for_update()
        )

    async def latest_sequence(self, session: AsyncSession, session_id: UUID) -> int:
        return int(
            await session.scalar(
                select(func.coalesce(func.max(Question.clustering_sequence), 0)).where(
                    Question.session_id == session_id
                )
            )
            or 0
        )

    async def list_questions(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        status: str | None,
        sort: str,
        after: QuestionCursorPosition | None,
        limit: int,
    ) -> list[tuple[Question, bool]]:
        reacted_by_me = exists(
            select(QuestionReaction.question_id).where(
                QuestionReaction.question_id == Question.id,
                QuestionReaction.user_id == user_id,
            )
        ).label("reacted_by_me")
        statement = select(Question, reacted_by_me).where(Question.session_id == session_id)
        if status is not None:
            statement = statement.where(Question.status == status)
        if after is not None:
            if sort == "POPULAR":
                assert after.reaction_count is not None
                statement = statement.where(
                    or_(
                        Question.reaction_count < after.reaction_count,
                        and_(
                            Question.reaction_count == after.reaction_count,
                            Question.created_at < after.created_at,
                        ),
                        and_(
                            Question.reaction_count == after.reaction_count,
                            Question.created_at == after.created_at,
                            Question.id < after.question_id,
                        ),
                    )
                )
            else:
                statement = statement.where(
                    or_(
                        Question.created_at < after.created_at,
                        and_(
                            Question.created_at == after.created_at,
                            Question.id < after.question_id,
                        ),
                    )
                )
        if sort == "POPULAR":
            statement = statement.order_by(
                Question.reaction_count.desc(), Question.created_at.desc(), Question.id.desc()
            )
        else:
            statement = statement.order_by(Question.created_at.desc(), Question.id.desc())
        return [
            (row[0], bool(row[1])) for row in (await session.execute(statement.limit(limit))).all()
        ]

    async def reaction_exists(
        self, session: AsyncSession, *, question_id: UUID, user_id: UUID
    ) -> bool:
        return (
            await session.get(QuestionReaction, {"question_id": question_id, "user_id": user_id})
        ) is not None

    async def add_reaction(
        self, session: AsyncSession, *, question_id: UUID, user_id: UUID, now: datetime
    ) -> bool:
        if await self.reaction_exists(session, question_id=question_id, user_id=user_id):
            return False
        session.add(QuestionReaction(question_id=question_id, user_id=user_id, created_at=now))
        return True

    async def remove_reaction(
        self, session: AsyncSession, *, question_id: UUID, user_id: UUID
    ) -> bool:
        reaction = await session.get(
            QuestionReaction, {"question_id": question_id, "user_id": user_id}
        )
        if reaction is None:
            return False
        await session.delete(reaction)
        return True
