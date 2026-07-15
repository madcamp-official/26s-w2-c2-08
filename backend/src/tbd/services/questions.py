"""LIVE student Question and reaction policies."""

from __future__ import annotations

import base64
import hmac
import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tbd.jobs.kernel import JobKernel
from tbd.models.enums import AIJobStatus, AIJobType, AIJobVisibility
from tbd.models.questions import AIJob, Question, QuestionClusteringState
from tbd.models.sessions import LectureSession
from tbd.repositories.outbox import OutboxRepository
from tbd.repositories.questions import QuestionCursorPosition, QuestionRepository
from tbd.schemas.questions import (
    QuestionClusteringJobRef,
    QuestionClusteringStateResponse,
    QuestionResponse,
)


class QuestionNotFoundError(Exception):
    """The requested Question or its Session is not visible."""


class QuestionAccessDeniedError(Exception):
    """The caller is not a member for a collection-level read."""


class QuestionRoleRequiredError(Exception):
    """Only Course students can mutate live Questions and reactions."""


class QuestionSessionStateError(Exception):
    """Question creation or reaction is not allowed in the current Session."""


class SelfReactionError(Exception):
    """Students cannot vote for their own Question."""


@dataclass
class QuestionContentValidationError(Exception):
    reason: str
    actual_length: int


class InvalidQuestionCursorError(Exception):
    """A cursor was tampered with or reused with another list scope."""


class QuestionCursorCodec:
    """Sign keyset positions without exposing a reusable raw database cursor."""

    _PREFIX = b"goal/questions/cursor/v1\x00"

    def __init__(self, secret: str) -> None:
        self._key = hmac.digest(secret.encode("utf-8"), self._PREFIX, "sha256")

    def encode(
        self,
        *,
        session_id: UUID,
        status: str | None,
        sort: str,
        position: QuestionCursorPosition,
    ) -> str:
        payload = {
            "created_at": position.created_at.isoformat(),
            "id": str(position.question_id),
            "reaction_count": position.reaction_count,
            "session_id": str(session_id),
            "sort": sort,
            "status": status,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.digest(self._key, raw, "sha256")[:16]
        return base64.urlsafe_b64encode(raw + signature).decode("ascii").rstrip("=")

    def decode(
        self, *, cursor: str, session_id: UUID, status: str | None, sort: str
    ) -> QuestionCursorPosition:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            encoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            raw, signature = encoded[:-16], encoded[-16:]
            if not hmac.compare_digest(hmac.digest(self._key, raw, "sha256")[:16], signature):
                raise ValueError
            payload = json.loads(raw)
            if (
                payload["session_id"] != str(session_id)
                or payload["status"] != status
                or payload["sort"] != sort
            ):
                raise ValueError
            reaction_count = payload["reaction_count"]
            if sort == "POPULAR" and (not isinstance(reaction_count, int) or reaction_count < 0):
                raise ValueError
            if sort == "RECENT" and reaction_count is not None:
                raise ValueError
            return QuestionCursorPosition(
                created_at=datetime.fromisoformat(payload["created_at"]),
                question_id=UUID(payload["id"]),
                reaction_count=reaction_count,
            )
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise InvalidQuestionCursorError from exc


class QuestionService:
    """Apply author-anonymous Question policies inside caller-owned transactions."""

    def __init__(
        self,
        *,
        auth_secret: str,
        repository: QuestionRepository | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self.repository = repository or QuestionRepository()
        self.outbox = outbox or OutboxRepository()
        self.cursors = QuestionCursorCodec(auth_secret)

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        status: str | None,
        sort: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[tuple[Question, bool]], str | None]:
        lecture_session = await self.repository.get_session(session, session_id)
        if lecture_session is None:
            raise QuestionNotFoundError
        if (
            await self.repository.member_role(
                session, course_id=lecture_session.course_id, user_id=user_id
            )
            is None
        ):
            raise QuestionAccessDeniedError
        after = (
            self.cursors.decode(cursor=cursor, session_id=session_id, status=status, sort=sort)
            if cursor is not None
            else None
        )
        rows = await self.repository.list_questions(
            session,
            session_id=session_id,
            user_id=user_id,
            status=status,
            sort=sort,
            after=after,
            limit=limit + 1,
        )
        page, extra = rows[:limit], rows[limit:]
        if not extra or not page:
            return page, None
        last_question = page[-1][0]
        return (
            page,
            self.cursors.encode(
                session_id=session_id,
                status=status,
                sort=sort,
                position=QuestionCursorPosition(
                    created_at=last_question.created_at,
                    question_id=last_question.id,
                    reaction_count=last_question.reaction_count if sort == "POPULAR" else None,
                ),
            ),
        )

    async def get_for_member(
        self, session: AsyncSession, *, question_id: UUID, user_id: UUID
    ) -> tuple[Question, bool]:
        question = await self.repository.get_question(session, question_id)
        if question is None:
            raise QuestionNotFoundError
        lecture_session = await self.repository.get_session(session, question.session_id)
        if (
            lecture_session is None
            or await self.repository.member_role(
                session, course_id=lecture_session.course_id, user_id=user_id
            )
            is None
        ):
            raise QuestionNotFoundError
        return question, await self.repository.reaction_exists(
            session, question_id=question.id, user_id=user_id
        )

    async def create(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        content: str,
        now: datetime | None = None,
    ) -> tuple[Question, QuestionClusteringStateResponse]:
        normalized = self.normalize_content(content)
        timestamp = now or datetime.now(UTC)
        lecture_session = await self.repository.lock_session(session, session_id)
        if lecture_session is None:
            raise QuestionNotFoundError
        role = await self.repository.member_role(
            session, course_id=lecture_session.course_id, user_id=user_id
        )
        self._require_question_author(role=role, status=lecture_session.status)
        state = await self.repository.lock_clustering_state(session, session_id)
        if state is None:
            raise QuestionNotFoundError
        live = lecture_session.status == "LIVE"
        if live:
            state.requested_sequence += 1
            sequence = state.requested_sequence
        else:
            # The Session lock serializes post-class inserts. Their sequence stays
            # beyond the frozen FINAL clustering watermark, so the final Cluster question list
            # remains an immutable snapshot of questions asked during LIVE.
            sequence = await self.repository.latest_sequence(session, session_id) + 1
        question = Question(
            session_id=session_id,
            author_user_id=user_id,
            clustering_sequence=sequence,
            content=normalized,
            status="OPEN",
            reaction_count=0,
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(question)
        await session.flush()

        active = await self.repository.active_clustering_job(session, session_id) if live else None
        if live and active is not None and active.status == AIJobStatus.PENDING:
            active.input_through_sequence = state.requested_sequence
            active.available_at = timestamp + LIVE_CLUSTERING_DEBOUNCE
            active.version += 1
        if live and active is None and state.retry_job_id is None:
            active = AIJob(
                session_id=session_id,
                job_type=AIJobType.QUESTION_CLUSTERING,
                visibility=AIJobVisibility.SHARED,
                status=AIJobStatus.PENDING,
                attempt=1,
                version=1,
                clustering_mode="LIVE_INCREMENTAL",
                input_through_sequence=state.requested_sequence,
                base_revision=state.current_revision,
                blocks_session_completion=False,
                retryable=True,
                available_at=timestamp + LIVE_CLUSTERING_DEBOUNCE,
            )
            await JobKernel(outbox=self.outbox).enqueue(session, active)
            state.last_job_id = active.id
            state.last_job_attempt = active.attempt
            state.last_job_status = str(active.status)
        await session.flush()
        question_response = self.project_question(question, reacted_by_me=False)
        clustering_response = self.project_clustering_state(state, active=active)
        await self.outbox.enqueue(
            session,
            session_id=session_id,
            partition_key=f"session:{session_id}",
            event_type="question.created",
            resource_version=question.version,
            payload=question_response.model_dump(mode="json"),
        )
        await self._emit_clustering_updated(session, session_id, clustering_response)
        return question, clustering_response

    async def add_reaction(
        self,
        session: AsyncSession,
        *,
        question_id: UUID,
        user_id: UUID,
        now: datetime | None = None,
    ) -> tuple[Question, bool]:
        question, lecture_session = await self._lock_reaction_scope(
            session, question_id=question_id, user_id=user_id
        )
        if question.author_user_id == user_id:
            raise SelfReactionError
        inserted = await self.repository.add_reaction(
            session, question_id=question.id, user_id=user_id, now=now or datetime.now(UTC)
        )
        if inserted:
            question.reaction_count += 1
            question.version += 1
            await session.flush()
            await self._emit_reaction_updated(session, question)
        return question, True

    async def remove_reaction(
        self, session: AsyncSession, *, question_id: UUID, user_id: UUID
    ) -> tuple[Question, bool]:
        question, _ = await self._lock_reaction_scope(
            session, question_id=question_id, user_id=user_id
        )
        removed = await self.repository.remove_reaction(
            session, question_id=question.id, user_id=user_id
        )
        if removed:
            question.reaction_count -= 1
            question.version += 1
            await session.flush()
            await self._emit_reaction_updated(session, question)
        return question, removed

    async def _lock_reaction_scope(
        self, session: AsyncSession, *, question_id: UUID, user_id: UUID
    ) -> tuple[Question, LectureSession]:
        visible = await self.repository.get_question(session, question_id)
        if visible is None:
            raise QuestionNotFoundError
        lecture_session = await self.repository.lock_session(session, visible.session_id)
        if lecture_session is None:
            raise QuestionNotFoundError
        self._require_live_student(
            role=await self.repository.member_role(
                session, course_id=lecture_session.course_id, user_id=user_id
            ),
            status=lecture_session.status,
        )
        question = await self.repository.lock_question(session, question_id)
        if question is None:
            raise QuestionNotFoundError
        return question, lecture_session

    async def _emit_reaction_updated(self, session: AsyncSession, question: Question) -> None:
        await self.outbox.enqueue(
            session,
            session_id=question.session_id,
            partition_key=f"session:{question.session_id}",
            event_type="reaction.updated",
            resource_version=question.version,
            payload={"question_id": str(question.id), "reaction_count": question.reaction_count},
        )

    async def _emit_clustering_updated(
        self,
        session: AsyncSession,
        session_id: UUID,
        state: QuestionClusteringStateResponse,
    ) -> None:
        await self.outbox.enqueue(
            session,
            session_id=session_id,
            partition_key=f"session:{session_id}",
            event_type="clustering.updated",
            # A fresh clustering state starts at revision 0, while the Outbox
            # requires a positive resource version.  The requested watermark
            # is monotonically increased with this update and is the value a
            # client needs to know before an AI revision exists.
            resource_version=max(1, state.requested_through_sequence),
            payload={"clustering_state": state.model_dump(mode="json")},
        )

    @staticmethod
    def normalize_content(content: str) -> str:
        normalized = unicodedata.normalize("NFC", content.strip())
        length = len(normalized)
        if length == 0:
            raise QuestionContentValidationError("EMPTY_AFTER_NORMALIZATION", length)
        if length > 300:
            raise QuestionContentValidationError("MAX_LENGTH_EXCEEDED", length)
        return normalized

    @staticmethod
    def project_question(question: Question, *, reacted_by_me: bool) -> QuestionResponse:
        return QuestionResponse(
            id=question.id,
            session_id=question.session_id,
            content=question.content,
            status=str(question.status),
            version=question.version,
            clustering_sequence=question.clustering_sequence,
            reaction_count=question.reaction_count,
            reacted_by_me=reacted_by_me,
            cluster_id=None,
            created_at=question.created_at,
            updated_at=question.updated_at,
        )

    @staticmethod
    def project_clustering_state(
        state: QuestionClusteringState,
        *,
        active: AIJob | None,
        last: AIJob | None = None,
    ) -> QuestionClusteringStateResponse:
        projected_job = (
            last
            if last is not None and last.id == state.last_job_id
            else active
            if active is not None and active.id == state.last_job_id
            else None
        )
        last_job = (
            QuestionClusteringJobRef(
                id=state.last_job_id,
                attempt=state.last_job_attempt,
                status=state.last_job_status,
                mode=(
                    str(projected_job.clustering_mode)
                    if projected_job is not None and projected_job.clustering_mode is not None
                    else "LIVE_INCREMENTAL"
                ),
            )
            if state.last_job_id is not None
            and state.last_job_attempt is not None
            and state.last_job_status is not None
            else None
        )
        return QuestionClusteringStateResponse(
            pending=state.requested_sequence > state.applied_sequence,
            requested_through_sequence=state.requested_sequence,
            applied_through_sequence=state.applied_sequence,
            current_revision=state.current_revision,
            current_generation=state.current_generation,
            final_generation=state.final_generation,
            active_job_id=active.id if active is not None else None,
            retry_job_id=state.retry_job_id,
            last_job=last_job,
        )

    @staticmethod
    def _require_live_student(*, role: str | None, status: str) -> None:
        if role is None:
            raise QuestionAccessDeniedError
        if role != "STUDENT":
            raise QuestionRoleRequiredError
        if status != "LIVE":
            raise QuestionSessionStateError

    @staticmethod
    def _require_question_author(*, role: str | None, status: str) -> None:
        if role is None:
            raise QuestionAccessDeniedError
        if role != "STUDENT":
            raise QuestionRoleRequiredError
        if status not in {"LIVE", "PROCESSING", "COMPLETED"}:
            raise QuestionSessionStateError


LIVE_CLUSTERING_DEBOUNCE = timedelta(seconds=5)
