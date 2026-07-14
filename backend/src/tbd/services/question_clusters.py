"""Canonical REST reads for immutable LIVE Question cluster generations."""

from __future__ import annotations

import base64
import hmac
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.clustering import (
    AIRepresentativeQuestion,
    Answer,
    QuestionCluster,
    QuestionClusterMember,
)
from tbd.models.questions import Question, QuestionClusteringState
from tbd.repositories.questions import QuestionRepository
from tbd.schemas.clustering import (
    QuestionClusterListResponse,
    QuestionClusterMemberListResponse,
    QuestionClusterMemberResponse,
    QuestionClusterResponse,
    RepresentativeQuestionClusterMember,
    RepresentativeQuestionResponse,
    StudentQuestionClusterMember,
)
from tbd.services.questions import (
    QuestionAccessDeniedError,
    QuestionNotFoundError,
    QuestionService,
)


class InvalidClusterCursorError(Exception):
    """A cluster cursor is malformed or was used for another collection."""


@dataclass(frozen=True, slots=True)
class _ClusterCursor:
    ordinal: int
    row_id: UUID


class _CursorCodec:
    _PREFIX = b"goal/question-clusters/cursor/v1\x00"

    def __init__(self, secret: str) -> None:
        self._key = hmac.digest(secret.encode("utf-8"), self._PREFIX, "sha256")

    def encode(self, *, session_id: UUID, generation: int, kind: str, value: _ClusterCursor) -> str:
        raw = json.dumps(
            {
                "generation": generation,
                "id": str(value.row_id),
                "kind": kind,
                "ordinal": value.ordinal,
                "session_id": str(session_id),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        signature = hmac.digest(self._key, raw, "sha256")[:16]
        return base64.urlsafe_b64encode(raw + signature).decode().rstrip("=")

    def decode(
        self, *, cursor: str, session_id: UUID, generation: int, kind: str
    ) -> _ClusterCursor:
        try:
            raw_and_signature = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            raw, signature = raw_and_signature[:-16], raw_and_signature[-16:]
            if not hmac.compare_digest(hmac.digest(self._key, raw, "sha256")[:16], signature):
                raise ValueError
            payload = json.loads(raw)
            if (
                payload["session_id"] != str(session_id)
                or payload["generation"] != generation
                or payload["kind"] != kind
                or not isinstance(payload["ordinal"], int)
            ):
                raise ValueError
            return _ClusterCursor(ordinal=payload["ordinal"], row_id=UUID(payload["id"]))
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise InvalidClusterCursorError from exc


class QuestionClusterService:
    """Expose the REST source of truth; WebSocket only invalidates this data."""

    def __init__(self, *, auth_secret: str, repository: QuestionRepository | None = None) -> None:
        self.repository = repository or QuestionRepository()
        self.cursors = _CursorCodec(auth_secret)

    async def list_for_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        scope: str,
        cursor: str | None,
        limit: int,
    ) -> QuestionClusterListResponse:
        state = await self._visible_state(session, session_id=session_id, user_id=user_id)
        generation = state.current_generation if scope == "CURRENT" else state.final_generation
        active = await self.repository.active_clustering_job(session, session_id)
        projection = QuestionService.project_clustering_state(state, active=active)
        if generation is None:
            return QuestionClusterListResponse(
                scope=scope,
                clustering_state=projection,
                generation=None,
                items=[],
                next_cursor=None,
            )
        after = (
            self.cursors.decode(
                cursor=cursor,
                session_id=session_id,
                generation=generation,
                kind="clusters",
            )
            if cursor
            else None
        )
        member_count = func.count(QuestionClusterMember.position).label("member_count")
        statement = (
            select(QuestionCluster, member_count)
            .outerjoin(
                QuestionClusterMember, QuestionClusterMember.cluster_id == QuestionCluster.id
            )
            .where(
                QuestionCluster.session_id == session_id, QuestionCluster.generation == generation
            )
            .group_by(QuestionCluster.id)
            .order_by(QuestionCluster.ordinal.asc(), QuestionCluster.id.asc())
        )
        if after is not None:
            statement = statement.where(
                or_(
                    QuestionCluster.ordinal > after.ordinal,
                    (QuestionCluster.ordinal == after.ordinal)
                    & (QuestionCluster.id > after.row_id),
                )
            )
        rows = (await session.execute(statement.limit(limit + 1))).all()
        page, extra = rows[:limit], rows[limit:]
        items = [
            await self._project_cluster(
                session,
                cluster=cluster,
                member_count=int(count),
                revision=state.current_revision,
            )
            for cluster, count in page
        ]
        next_cursor = (
            self.cursors.encode(
                session_id=session_id,
                generation=generation,
                kind="clusters",
                value=_ClusterCursor(ordinal=page[-1][0].ordinal, row_id=page[-1][0].id),
            )
            if extra and page
            else None
        )
        return QuestionClusterListResponse(
            scope=scope,
            clustering_state=projection,
            generation=generation,
            items=items,
            next_cursor=next_cursor,
        )

    async def list_members_for_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        cluster_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> QuestionClusterMemberListResponse:
        state = await self._visible_state(session, session_id=session_id, user_id=user_id)
        if state.current_generation is None:
            raise QuestionNotFoundError
        cluster = await session.scalar(
            select(QuestionCluster).where(
                QuestionCluster.session_id == session_id,
                QuestionCluster.generation == state.current_generation,
                QuestionCluster.logical_cluster_id == cluster_id,
            )
        )
        if cluster is None:
            raise QuestionNotFoundError
        after = (
            self.cursors.decode(
                cursor=cursor,
                session_id=session_id,
                generation=state.current_generation,
                kind="members",
            )
            if cursor
            else None
        )
        statement = select(QuestionClusterMember).where(
            QuestionClusterMember.cluster_id == cluster.id
        )
        if after is not None:
            statement = statement.where(QuestionClusterMember.position > after.ordinal)
        rows = list(
            await session.scalars(
                statement.order_by(QuestionClusterMember.position.asc()).limit(limit + 1)
            )
        )
        page, extra = rows[:limit], rows[limit:]
        items: list[QuestionClusterMemberResponse] = []
        for member in page:
            if member.question_id is not None:
                question = await session.get(Question, member.question_id)
                if question is None:
                    raise QuestionNotFoundError
                reacted = await self.repository.reaction_exists(
                    session, question_id=question.id, user_id=user_id
                )
                items.append(
                    StudentQuestionClusterMember(
                        source_kind="STUDENT_QUESTION",
                        ordinal=member.position,
                        question=QuestionService.project_question(question, reacted_by_me=reacted),
                    )
                )
            else:
                assert member.representative_question_id is not None
                representative = await self._representative(
                    session, member.representative_question_id
                )
                if representative.lifecycle_status != "PRESERVED":
                    raise QuestionNotFoundError
                items.append(
                    RepresentativeQuestionClusterMember(
                        source_kind="AI_REPRESENTATIVE",
                        ordinal=member.position,
                        representative_question=representative,
                    )
                )
        next_cursor = (
            self.cursors.encode(
                session_id=session_id,
                generation=state.current_generation,
                kind="members",
                value=_ClusterCursor(ordinal=page[-1].position, row_id=cluster.id),
            )
            if extra and page
            else None
        )
        return QuestionClusterMemberListResponse(
            cluster_id=cluster_id, items=items, next_cursor=next_cursor
        )

    async def get_representative_for_member(
        self, session: AsyncSession, *, representative_id: UUID, user_id: UUID
    ) -> RepresentativeQuestionResponse:
        representative = await session.get(AIRepresentativeQuestion, representative_id)
        if representative is None or representative.lifecycle_status == "DISCARDED":
            raise QuestionNotFoundError
        await self._visible_state(session, session_id=representative.session_id, user_id=user_id)
        return await self._representative(session, representative_id)

    async def _visible_state(
        self, session: AsyncSession, *, session_id: UUID, user_id: UUID
    ) -> QuestionClusteringState:
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
        state = await session.get(QuestionClusteringState, session_id)
        if state is None:
            raise QuestionNotFoundError
        return state

    async def _project_cluster(
        self,
        session: AsyncSession,
        *,
        cluster: QuestionCluster,
        member_count: int,
        revision: int,
    ) -> QuestionClusterResponse:
        return QuestionClusterResponse(
            id=cluster.logical_cluster_id,
            session_id=cluster.session_id,
            generation=cluster.generation,
            revision=revision,
            ordinal=cluster.ordinal,
            representative_question=await self._representative(
                session, cluster.representative_question_id
            ),
            member_count=member_count,
            members_url=(
                f"/api/v1/sessions/{cluster.session_id}/question-clusters/"
                f"{cluster.logical_cluster_id}/members"
            ),
            is_final=cluster.is_final,
            finalized_at=cluster.finalized_at,
            created_by_job_id=cluster.created_by_job_id,
            created_by_job_attempt=cluster.created_by_job_attempt,
        )

    async def _representative(
        self, session: AsyncSession, representative_id: UUID
    ) -> RepresentativeQuestionResponse:
        representative = await session.get(AIRepresentativeQuestion, representative_id)
        if representative is None or representative.lifecycle_status == "DISCARDED":
            raise QuestionNotFoundError
        answer_id = await session.scalar(
            select(Answer.id).where(Answer.target_representative_question_id == representative.id)
        )
        return RepresentativeQuestionResponse(
            id=representative.id,
            session_id=representative.session_id,
            content=representative.text,
            lifecycle_status=representative.lifecycle_status,
            status=representative.status,
            version=representative.version,
            answer_id=answer_id,
            created_by_job_id=representative.created_by_job_id,
            created_by_job_attempt=representative.created_by_job_attempt,
            created_in_generation=representative.created_in_generation,
            created_at=representative.created_at,
        )
