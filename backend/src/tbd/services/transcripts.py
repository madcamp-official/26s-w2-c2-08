"""Course-authorized REST recovery for durable Transcript versions and timelines."""

import base64
import hmac
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.auth.security import AuthCrypto
from tbd.core.config import Settings
from tbd.models.courses import CourseMember
from tbd.models.materials import TranscriptGap, TranscriptSegment, TranscriptVersion
from tbd.models.sessions import LectureSession
from tbd.schemas.transcripts import (
    TranscriptAggregateResponse,
    TranscriptGapResponse,
    TranscriptSegmentResponse,
    TranscriptTimelinePageResponse,
    TranscriptVersionResponse,
)


class TranscriptSessionNotFoundError(Exception):
    """The requested Session is absent."""


class TranscriptAccessDeniedError(Exception):
    """The user is not a member of the Session's Course."""


class TranscriptNotFoundError(Exception):
    """The selected version, segment, or anchor is out of the Session scope."""


class InvalidTranscriptCursorError(Exception):
    """The cursor is malformed or belongs to a different immutable timeline scope."""


class InvalidTranscriptAnchorError(Exception):
    """Sequence anchor fields are incomplete or cannot bind the selected version."""


@dataclass(frozen=True)
class _TimelineItem:
    kind: str
    start_ms: int
    item_id: UUID
    value: TranscriptSegment | TranscriptGap


@dataclass(frozen=True)
class TranscriptVersionPage:
    """A version page whose cursor cannot be replayed for another Session."""

    items: list[TranscriptVersionResponse]
    next_cursor: str | None


class TranscriptCursorCodec:
    """Sign a small timeline position so a cursor cannot switch transcript versions."""

    def __init__(self, settings: Settings) -> None:
        self._crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())

    def encode(self, payload: dict[str, object]) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        body = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        signature = (
            base64.urlsafe_b64encode(self._crypto.hash_token("transcript-timeline-cursor", body))
            .decode()
            .rstrip("=")
        )
        return f"{body}.{signature}"

    def decode(self, cursor: str) -> dict[str, object] | None:
        try:
            body, signature = cursor.split(".", 1)
            expected = (
                base64.urlsafe_b64encode(
                    self._crypto.hash_token("transcript-timeline-cursor", body)
                )
                .decode()
                .rstrip("=")
            )
            if not hmac.compare_digest(expected, signature):
                return None
            padded = body + ("=" * (-len(body) % 4))
            value = json.loads(base64.urlsafe_b64decode(padded))
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None


class TranscriptService:
    """Keep REST data canonical while WebSocket events remain best-effort hints."""

    def __init__(self, settings: Settings) -> None:
        self._cursor_codec = TranscriptCursorCodec(settings)

    async def timeline(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        transcript_version_id: UUID | None,
        start_sequence: int | None,
        end_sequence: int | None,
        cursor: str | None,
        limit: int,
    ) -> TranscriptTimelinePageResponse:
        lecture_session = await self._require_member(
            session, session_id=session_id, user_id=user_id
        )
        if (
            start_sequence is not None or end_sequence is not None
        ) and transcript_version_id is None:
            raise InvalidTranscriptAnchorError
        selected, aggregate = await self._select_version(
            session,
            lecture_session=lecture_session,
            transcript_version_id=transcript_version_id,
        )
        anchor = await self._resolve_anchor(
            session,
            selected=selected,
            start_sequence=start_sequence,
            end_sequence=end_sequence,
        )
        scope = {
            "version": str(selected.id),
            "start": start_sequence,
            "end": end_sequence,
        }
        after = self._decode_timeline_cursor(cursor, scope=scope)
        segments = list(
            await session.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_version_id == selected.id)
                .order_by(TranscriptSegment.start_ms.asc(), TranscriptSegment.id.asc())
            )
        )
        gaps = list(
            await session.scalars(
                select(TranscriptGap)
                .where(TranscriptGap.transcript_version_id == selected.id)
                .order_by(TranscriptGap.start_ms.asc(), TranscriptGap.id.asc())
            )
        )
        if anchor is not None:
            start_ms, end_ms = anchor
            segments = [
                item
                for item in segments
                if start_sequence is not None
                and end_sequence is not None
                and start_sequence <= item.sequence <= end_sequence
            ]
            gaps = [
                item
                for item in gaps
                if item.start_ms <= end_ms and (item.end_ms is None or item.end_ms >= start_ms)
            ]
        items = [
            *(_TimelineItem("SEGMENT", item.start_ms, item.id, item) for item in segments),
            *(_TimelineItem("GAP", item.start_ms, item.id, item) for item in gaps),
        ]
        items.sort(
            key=lambda item: (item.start_ms, 0 if item.kind == "SEGMENT" else 1, str(item.item_id))
        )
        if after is not None:
            items = [item for item in items if self._item_key(item) > after]
        page = items[:limit]
        next_cursor = None
        if len(items) > limit and page:
            last = page[-1]
            next_cursor = self._cursor_codec.encode(
                {
                    **scope,
                    "position": [last.start_ms, last.kind, str(last.item_id)],
                }
            )
        return TranscriptTimelinePageResponse(
            transcript=aggregate,
            selected_version=self._project_version(selected, lecture_session),
            segments=[self._project_segment(item.value) for item in page if item.kind == "SEGMENT"],
            gaps=[self._project_gap(item.value) for item in page if item.kind == "GAP"],
            next_cursor=next_cursor,
        )

    async def list_versions(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> TranscriptVersionPage:
        lecture_session = await self._require_member(
            session, session_id=session_id, user_id=user_id
        )
        scope = {"kind": "versions", "session": str(session_id)}
        after = self._decode_version_cursor(cursor, scope=scope)
        statement = (
            select(TranscriptVersion)
            .where(TranscriptVersion.session_id == session_id)
            .order_by(TranscriptVersion.version.desc(), TranscriptVersion.id.desc())
        )
        if after is not None:
            try:
                after_id = UUID(after[1])
            except ValueError as exc:
                raise InvalidTranscriptCursorError from exc
            statement = statement.where(
                or_(
                    TranscriptVersion.version < after[0],
                    and_(
                        TranscriptVersion.version == after[0],
                        TranscriptVersion.id < after_id,
                    ),
                )
            )
        versions = list(await session.scalars(statement.limit(limit + 1)))
        page = versions[:limit]
        next_cursor = None
        if len(versions) > limit and page:
            last = page[-1]
            next_cursor = self._cursor_codec.encode(
                {**scope, "position": [last.version, str(last.id)]}
            )
        return TranscriptVersionPage(
            items=[self._project_version(version, lecture_session) for version in page],
            next_cursor=next_cursor,
        )

    async def get_segment(
        self,
        session: AsyncSession,
        *,
        segment_id: UUID,
        user_id: UUID,
    ) -> TranscriptSegmentResponse:
        segment = await session.get(TranscriptSegment, segment_id)
        if segment is None:
            raise TranscriptNotFoundError
        lecture_session = await session.get(LectureSession, segment.session_id)
        if lecture_session is None:
            raise TranscriptNotFoundError
        role = await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == lecture_session.course_id,
                CourseMember.user_id == user_id,
            )
        )
        if role is None:
            raise TranscriptNotFoundError
        return self._project_segment(segment)

    async def _require_member(
        self, session: AsyncSession, *, session_id: UUID, user_id: UUID
    ) -> LectureSession:
        lecture_session = await session.get(LectureSession, session_id)
        if lecture_session is None:
            raise TranscriptSessionNotFoundError
        role = await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == lecture_session.course_id,
                CourseMember.user_id == user_id,
            )
        )
        if role is None:
            raise TranscriptAccessDeniedError
        return lecture_session

    async def _select_version(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        transcript_version_id: UUID | None,
    ) -> tuple[TranscriptVersion, TranscriptAggregateResponse]:
        versions = list(
            await session.scalars(
                select(TranscriptVersion)
                .where(TranscriptVersion.session_id == lecture_session.id)
                .order_by(TranscriptVersion.version.desc(), TranscriptVersion.id.desc())
            )
        )
        if not versions:
            raise TranscriptNotFoundError
        current = versions[0]
        canonical = next(
            (
                item
                for item in versions
                if item.id == lecture_session.canonical_transcript_version_id
            ),
            None,
        )
        selected = (
            next((item for item in versions if item.id == transcript_version_id), None)
            if transcript_version_id is not None
            else canonical or current
        )
        if selected is None:
            raise TranscriptNotFoundError
        aggregate = TranscriptAggregateResponse(
            session_id=lecture_session.id,
            status=current.status,
            current_version=self._project_version(current, lecture_session),
            canonical_version_id=lecture_session.canonical_transcript_version_id,
            canonical_version=self._project_version(canonical, lecture_session)
            if canonical is not None
            else None,
            updated_at=max(current.updated_at, lecture_session.updated_at),
        )
        return selected, aggregate

    async def _resolve_anchor(
        self,
        session: AsyncSession,
        *,
        selected: TranscriptVersion,
        start_sequence: int | None,
        end_sequence: int | None,
    ) -> tuple[int, int] | None:
        if start_sequence is None and end_sequence is None:
            return None
        if start_sequence is None or end_sequence is None or start_sequence > end_sequence:
            raise InvalidTranscriptAnchorError
        rows = list(
            await session.scalars(
                select(TranscriptSegment).where(
                    TranscriptSegment.transcript_version_id == selected.id,
                    TranscriptSegment.sequence.in_((start_sequence, end_sequence)),
                )
            )
        )
        by_sequence = {row.sequence: row for row in rows}
        if start_sequence not in by_sequence or end_sequence not in by_sequence:
            raise TranscriptNotFoundError
        return by_sequence[start_sequence].start_ms, by_sequence[end_sequence].end_ms

    def _decode_timeline_cursor(
        self, cursor: str | None, *, scope: dict[str, object]
    ) -> tuple[int, int, str] | None:
        if cursor is None:
            return None
        payload = self._cursor_codec.decode(cursor)
        if payload is None or any(payload.get(key) != value for key, value in scope.items()):
            raise InvalidTranscriptCursorError
        position = payload.get("position")
        if (
            not isinstance(position, list)
            or len(position) != 3
            or not isinstance(position[0], int)
            or position[1] not in {"SEGMENT", "GAP"}
            or not isinstance(position[2], str)
        ):
            raise InvalidTranscriptCursorError
        return position[0], 0 if position[1] == "SEGMENT" else 1, position[2]

    def _decode_version_cursor(
        self, cursor: str | None, *, scope: dict[str, object]
    ) -> tuple[int, str] | None:
        if cursor is None:
            return None
        payload = self._cursor_codec.decode(cursor)
        if payload is None or any(payload.get(key) != value for key, value in scope.items()):
            raise InvalidTranscriptCursorError
        position = payload.get("position")
        if (
            not isinstance(position, list)
            or len(position) != 2
            or not isinstance(position[0], int)
            or position[0] < 1
            or not isinstance(position[1], str)
        ):
            raise InvalidTranscriptCursorError
        return position[0], position[1]

    @staticmethod
    def _item_key(item: _TimelineItem) -> tuple[int, int, str]:
        return item.start_ms, 0 if item.kind == "SEGMENT" else 1, str(item.item_id)

    @staticmethod
    def _project_version(
        version: TranscriptVersion, lecture_session: LectureSession
    ) -> TranscriptVersionResponse:
        return TranscriptVersionResponse(
            id=version.id,
            session_id=version.session_id,
            source=version.source,
            status=version.status,
            version=version.version,
            last_sequence=version.last_sequence,
            is_canonical=version.id == lecture_session.canonical_transcript_version_id,
            recording_id=version.recording_id,
            created_by_job_id=version.created_by_job_id,
            created_by_job_attempt=version.created_by_job_attempt,
            finalized_at=version.finalized_at,
            failed_at=version.failed_at,
            created_at=version.created_at,
            updated_at=version.updated_at,
        )

    @staticmethod
    def _project_segment(segment: TranscriptSegment | TranscriptGap) -> TranscriptSegmentResponse:
        assert isinstance(segment, TranscriptSegment)
        return TranscriptSegmentResponse(
            id=segment.id,
            session_id=segment.session_id,
            transcript_version_id=segment.transcript_version_id,
            sequence=segment.sequence,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            recording_start_ms=segment.recording_start_ms,
            recording_end_ms=segment.recording_end_ms,
            text=segment.text,
            created_at=segment.created_at,
        )

    @staticmethod
    def _project_gap(gap: TranscriptSegment | TranscriptGap) -> TranscriptGapResponse:
        assert isinstance(gap, TranscriptGap)
        return TranscriptGapResponse(
            id=gap.id,
            session_id=gap.session_id,
            transcript_version_id=gap.transcript_version_id,
            start_ms=gap.start_ms,
            end_ms=gap.end_ms,
            is_final=gap.is_final,
            reason=gap.reason,
            created_at=gap.created_at,
        )
