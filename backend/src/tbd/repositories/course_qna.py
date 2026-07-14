"""Persistence queries for the Course-wide, read-only Q&A archive."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, exists, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from tbd.models.clustering import AIRepresentativeQuestion, Answer, AnswerOrganization
from tbd.models.courses import Course, CourseMember
from tbd.models.questions import Question, QuestionReaction
from tbd.models.sessions import LectureSession

ACTIVE_SESSION_STATES = ("READY", "LIVE", "PROCESSING")
ARCHIVE_SESSION_STATES = (*ACTIVE_SESSION_STATES, "COMPLETED")
STUDENT_QUESTION = "STUDENT_QUESTION"
AI_REPRESENTATIVE_QUESTION = "AI_REPRESENTATIVE_QUESTION"


@dataclass(frozen=True)
class CourseQnaArchivePosition:
    """The final row position in the Course archive's mixed class/target order."""

    phase: int
    session_started_at: datetime | None
    session_id: UUID
    occurred_at: datetime
    target_id: UUID
    frozen_session_id: UUID | None


@dataclass(frozen=True)
class CourseQnaArchiveRow:
    """ORM objects required for one public student or representative target."""

    phase: int
    lecture_session: LectureSession
    target_type: str
    target_id: UUID
    occurred_at: datetime
    question: Question | None
    answer: Answer | None
    organization_content: str | None
    reacted_by_me: bool


class CourseQnaArchiveRepository:
    """Keep authorization reads and union keyset pagination outside the service."""

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

    async def list_course_archive(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
        after: CourseQnaArchivePosition | None,
        limit: int,
    ) -> list[CourseQnaArchiveRow]:
        """Return a bounded target page with no author or provider joins."""

        student_targets = select(
            Question.session_id.label("session_id"),
            literal(STUDENT_QUESTION).label("target_type"),
            Question.id.label("target_id"),
            Question.created_at.label("occurred_at"),
        )
        representative_targets = (
            select(
                Answer.session_id.label("session_id"),
                literal(AI_REPRESENTATIVE_QUESTION).label("target_type"),
                Answer.target_representative_question_id.label("target_id"),
                Answer.completed_at.label("occurred_at"),
            )
            .join(
                AIRepresentativeQuestion,
                and_(
                    AIRepresentativeQuestion.id == Answer.target_representative_question_id,
                    AIRepresentativeQuestion.session_id == Answer.session_id,
                ),
            )
            .where(
                Answer.status == "COMPLETED",
                Answer.target_representative_question_id.is_not(None),
                Answer.completed_at.is_not(None),
                AIRepresentativeQuestion.lifecycle_status.in_(("ACTIVE", "PRESERVED")),
            )
        )
        targets = union_all(student_targets, representative_targets).subquery("course_qna_targets")
        completed_answer = aliased(Answer, name="course_qna_completed_answer")
        reacted_by_me = exists(
            select(QuestionReaction.question_id).where(
                QuestionReaction.question_id == targets.c.target_id,
                QuestionReaction.user_id == user_id,
            )
        ).label("reacted_by_me")

        archive_phase = (
            case((LectureSession.id == after.session_id, 0), else_=1)
            if after is not None and after.phase == 0
            else case(
                (LectureSession.status.in_(ACTIVE_SESSION_STATES), 0),
                else_=1,
            )
        )
        statement = (
            select(
                archive_phase.label("archive_phase"),
                LectureSession,
                targets.c.target_type,
                targets.c.target_id,
                targets.c.occurred_at,
                Question,
                completed_answer,
                AnswerOrganization.content,
                reacted_by_me,
            )
            .join(targets, targets.c.session_id == LectureSession.id)
            .join(
                Course,
                and_(
                    Course.id == LectureSession.course_id,
                    Course.deleted_at.is_(None),
                ),
            )
            .join(
                CourseMember,
                and_(
                    CourseMember.course_id == Course.id,
                    CourseMember.user_id == user_id,
                ),
            )
            .outerjoin(
                Question,
                and_(
                    targets.c.target_type == STUDENT_QUESTION,
                    Question.id == targets.c.target_id,
                ),
            )
            .outerjoin(
                completed_answer,
                and_(
                    completed_answer.status == "COMPLETED",
                    or_(
                        and_(
                            targets.c.target_type == STUDENT_QUESTION,
                            completed_answer.target_question_id == targets.c.target_id,
                        ),
                        and_(
                            targets.c.target_type == AI_REPRESENTATIVE_QUESTION,
                            completed_answer.target_representative_question_id
                            == targets.c.target_id,
                        ),
                    ),
                ),
            )
            .outerjoin(
                AnswerOrganization,
                AnswerOrganization.answer_id == completed_answer.id,
            )
            .where(
                Course.id == course_id,
                LectureSession.status.in_(ARCHIVE_SESSION_STATES),
            )
        )

        if after is not None:
            target_after = or_(
                targets.c.occurred_at < after.occurred_at,
                and_(
                    targets.c.occurred_at == after.occurred_at,
                    targets.c.target_id < after.target_id,
                ),
            )
            if after.phase == 0:
                # Preserve the class that issued the active cursor as the
                # first group after it transitions to COMPLETED. This avoids
                # both repeats and omissions when another completed class has
                # a newer started_at value.
                statement = statement.where(
                    or_(
                        and_(LectureSession.id == after.session_id, target_after),
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
                    (
                        LectureSession.id != after.frozen_session_id
                        if after.frozen_session_id is not None
                        else True
                    ),
                    or_(
                        LectureSession.started_at < after.session_started_at,
                        and_(
                            LectureSession.started_at == after.session_started_at,
                            LectureSession.id < after.session_id,
                        ),
                        and_(LectureSession.id == after.session_id, target_after),
                    ),
                )

        rows = (
            await session.execute(
                statement.order_by(
                    archive_phase.asc(),
                    LectureSession.started_at.desc().nullslast(),
                    LectureSession.id.desc(),
                    targets.c.occurred_at.desc(),
                    targets.c.target_id.desc(),
                ).limit(limit)
            )
        ).all()
        result: list[CourseQnaArchiveRow] = []
        for row in rows:
            occurred_at = row[4]
            target_id = row[3]
            if not isinstance(occurred_at, datetime) or not isinstance(target_id, UUID):
                raise RuntimeError("Course Q&A archive target has an invalid persisted position")
            result.append(
                CourseQnaArchiveRow(
                    phase=int(row[0]),
                    lecture_session=row[1],
                    target_type=str(row[2]),
                    target_id=target_id,
                    occurred_at=occurred_at,
                    question=row[5],
                    answer=row[6],
                    organization_content=(str(row[7]) if row[7] is not None else None),
                    reacted_by_me=bool(row[8]),
                )
            )
        return result
