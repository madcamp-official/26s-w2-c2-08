"""Transactional Outbox persistence and best-effort realtime replay queries."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.consistency import OutboxEvent


class OutboxRepository:
    """Create durable, safe event records within a caller-owned transaction."""

    async def enqueue(
        self,
        session: AsyncSession,
        *,
        partition_key: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: UUID | None = None,
        resource_version: int | None = None,
        available_at: datetime | None = None,
    ) -> OutboxEvent:
        """Add an unpublished event; the caller controls commit or rollback."""

        event = OutboxEvent(
            session_id=session_id,
            partition_key=partition_key,
            event_type=event_type,
            payload=payload,
            resource_version=resource_version,
            available_at=available_at or datetime.now(UTC),
        )
        session.add(event)
        await session.flush()
        return event

    async def claim_available(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        limit: int,
    ) -> list[OutboxEvent]:
        """Claim unpublished rows once; delivery remains recoverable through replay."""

        rows = await session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.available_at <= now,
            )
            .order_by(
                OutboxEvent.available_at.asc(), OutboxEvent.created_at.asc(), OutboxEvent.id.asc()
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list(rows)
        for event in events:
            event.published_at = now
            event.publish_attempt += 1
        await session.flush()
        return events

    async def replay_after(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        cursor_event_id: UUID,
        limit: int,
    ) -> list[OutboxEvent] | None:
        """Read events after a known cursor within one Session's retained window."""

        cursor = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.id == cursor_event_id,
                OutboxEvent.session_id == session_id,
            )
        )
        if cursor is None:
            return None
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.session_id == session_id,
                    or_(
                        OutboxEvent.created_at > cursor.created_at,
                        and_(
                            OutboxEvent.created_at == cursor.created_at,
                            OutboxEvent.id > cursor.id,
                        ),
                    ),
                )
                .order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
                .limit(limit + 1)
            )
        )
        # A partial replay would leave the client believing its cursor caught
        # up. Force the documented REST resync instead of silently truncating.
        return events[:limit] if len(events) <= limit else None
