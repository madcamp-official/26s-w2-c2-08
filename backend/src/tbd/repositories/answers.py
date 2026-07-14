"""Locking queries for Answer state transitions and recovery reads."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.clustering import AIRepresentativeQuestion, Answer, AnswerTranscriptMapping
from tbd.models.materials import TranscriptSegment, TranscriptVersion
from tbd.models.questions import Question
from tbd.models.sessions import LectureSession


@dataclass(frozen=True)
class AnswerCursorPosition:
    started_at: datetime
    answer_id: UUID


class AnswerRepository:
    async def lock_session(self, session: AsyncSession, session_id: UUID) -> LectureSession | None:
        return await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )

    async def lock_answer(self, session: AsyncSession, answer_id: UUID) -> Answer | None:
        return await session.scalar(select(Answer).where(Answer.id == answer_id).with_for_update())

    async def lock_question(self, session: AsyncSession, question_id: UUID) -> Question | None:
        return await session.scalar(
            select(Question).where(Question.id == question_id).with_for_update()
        )

    async def lock_representative(
        self, session: AsyncSession, representative_id: UUID
    ) -> AIRepresentativeQuestion | None:
        return await session.scalar(
            select(AIRepresentativeQuestion)
            .where(AIRepresentativeQuestion.id == representative_id)
            .with_for_update()
        )

    async def existing_target_answer(
        self,
        session: AsyncSession,
        *,
        question_id: UUID | None = None,
        representative_id: UUID | None = None,
    ) -> Answer | None:
        column = (
            Answer.target_question_id
            if question_id is not None
            else Answer.target_representative_question_id
        )
        value = question_id if question_id is not None else representative_id
        return await session.scalar(select(Answer).where(column == value).with_for_update())

    async def capturing_answer(self, session: AsyncSession, session_id: UUID) -> Answer | None:
        return await session.scalar(
            select(Answer)
            .where(Answer.session_id == session_id, Answer.status == "CAPTURING")
            .with_for_update()
        )

    async def live_version(
        self, session: AsyncSession, session_id: UUID
    ) -> TranscriptVersion | None:
        return await session.scalar(
            select(TranscriptVersion)
            .where(TranscriptVersion.session_id == session_id, TranscriptVersion.source == "LIVE")
            .order_by(TranscriptVersion.version.desc())
            .with_for_update()
        )

    async def last_sequence(self, session: AsyncSession, transcript_version_id: UUID) -> int:
        value = await session.scalar(
            select(func.max(TranscriptSegment.sequence)).where(
                TranscriptSegment.transcript_version_id == transcript_version_id
            )
        )
        return int(value or 0)

    async def segment_by_sequence(
        self, session: AsyncSession, *, transcript_version_id: UUID, sequence: int
    ) -> TranscriptSegment | None:
        return await session.scalar(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.transcript_version_id == transcript_version_id,
                TranscriptSegment.sequence == sequence,
            )
            .with_for_update()
        )

    async def first_last_after(
        self, session: AsyncSession, *, transcript_version_id: UUID, sequence: int
    ) -> tuple[TranscriptSegment | None, TranscriptSegment | None]:
        segments = list(
            await session.scalars(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.transcript_version_id == transcript_version_id,
                    TranscriptSegment.sequence > sequence,
                )
                .order_by(TranscriptSegment.sequence.asc())
                .with_for_update()
            )
        )
        return (segments[0], segments[-1]) if segments else (None, None)

    async def canonical_mapping(
        self, session: AsyncSession, *, answer_id: UUID, version_id: UUID | None
    ) -> AnswerTranscriptMapping | None:
        if version_id is None:
            return None
        return await session.get(
            AnswerTranscriptMapping,
            {"answer_id": answer_id, "target_transcript_version_id": version_id},
        )

    async def list_answers(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        after: AnswerCursorPosition | None,
        limit: int,
    ) -> list[Answer]:
        statement = select(Answer).where(Answer.session_id == session_id)
        if after is not None:
            statement = statement.where(
                or_(
                    Answer.started_at > after.started_at,
                    and_(Answer.started_at == after.started_at, Answer.id > after.answer_id),
                )
            )
        return list(
            await session.scalars(
                statement.order_by(Answer.started_at.asc(), Answer.id.asc()).limit(limit)
            )
        )
