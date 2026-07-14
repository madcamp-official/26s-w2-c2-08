"""One-time realtime ticket issuance and upgrade-time authorization."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.auth.security import AuthCrypto
from tbd.core.config import Settings
from tbd.models.auth import RealtimeTicket
from tbd.models.courses import CourseMember
from tbd.models.enums import RealtimeTicketScope
from tbd.models.sessions import LectureSession

TICKET_TTL = timedelta(seconds=60)


class RealtimeSessionNotFoundError(Exception):
    """The requested class no longer exists."""


class RealtimeAccessDeniedError(Exception):
    """The current user is not an allowed Course member."""


class RealtimeScopeDeniedError(Exception):
    """A member cannot request the selected realtime capability."""


class RealtimeTicketInvalidError(Exception):
    """A ticket is malformed, expired, consumed, or for another channel."""


@dataclass(frozen=True)
class IssuedRealtimeTicket:
    ticket: str
    session_id: UUID
    scope: RealtimeTicketScope
    expires_at: datetime


@dataclass(frozen=True)
class RealtimeTicketAccess:
    session_id: UUID
    user_id: UUID
    role: str
    resume_cursor: str | None


class RealtimeTicketService:
    """Keep ticket plaintext outside PostgreSQL and re-check membership on upgrade."""

    def __init__(self, settings: Settings) -> None:
        self._crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())

    async def issue(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        session_id: UUID,
        scope: RealtimeTicketScope,
        resume_cursor: str | None,
        now: datetime | None = None,
    ) -> IssuedRealtimeTicket:
        lecture_session, role = await self._require_member(
            session, session_id=session_id, user_id=user_id
        )
        if scope == RealtimeTicketScope.SESSION_AUDIO_WRITE:
            if role != "PROFESSOR" or lecture_session.status != "LIVE":
                raise RealtimeScopeDeniedError
        timestamp = now or datetime.now(UTC)
        token = self._crypto.opaque_token()
        expires_at = timestamp + TICKET_TTL
        session.add(
            RealtimeTicket(
                ticket_hash=self._crypto.hash_token("realtime-ticket", token),
                user_id=user_id,
                session_id=session_id,
                scope=scope,
                resume_cursor=resume_cursor,
                expires_at=expires_at,
                created_at=timestamp,
            )
        )
        await session.flush()
        return IssuedRealtimeTicket(
            ticket=token,
            session_id=session_id,
            scope=scope,
            expires_at=expires_at,
        )

    async def consume_event_ticket(
        self,
        session: AsyncSession,
        *,
        token: str | None,
        session_id: UUID,
        now: datetime | None = None,
    ) -> RealtimeTicketAccess:
        if not token:
            raise RealtimeTicketInvalidError
        timestamp = now or datetime.now(UTC)
        ticket = await session.scalar(
            select(RealtimeTicket)
            .where(RealtimeTicket.ticket_hash == self._crypto.hash_token("realtime-ticket", token))
            .with_for_update()
        )
        if (
            ticket is None
            or ticket.used_at is not None
            or ticket.expires_at <= timestamp
            or ticket.session_id != session_id
            or ticket.scope != RealtimeTicketScope.SESSION_EVENTS_READ
        ):
            raise RealtimeTicketInvalidError
        lecture_session, role = await self._require_member(
            session, session_id=session_id, user_id=ticket.user_id
        )
        del lecture_session
        ticket.used_at = timestamp
        await session.flush()
        return RealtimeTicketAccess(
            session_id=session_id,
            user_id=ticket.user_id,
            role=role,
            resume_cursor=ticket.resume_cursor,
        )

    async def _require_member(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
    ) -> tuple[LectureSession, str]:
        lecture_session = await session.get(LectureSession, session_id)
        if lecture_session is None:
            raise RealtimeSessionNotFoundError
        role = await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == lecture_session.course_id,
                CourseMember.user_id == user_id,
            )
        )
        if role is None:
            raise RealtimeAccessDeniedError
        return lecture_session, str(role)
