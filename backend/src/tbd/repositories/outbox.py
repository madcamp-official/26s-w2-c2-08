"""Transactional Outbox persistence independent of the later delivery transport."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

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
