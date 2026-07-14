"""Publish committed Outbox events to local WebSocket subscribers."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from tbd.core.config import Settings
from tbd.db import Database, transaction
from tbd.models.consistency import OutboxEvent
from tbd.realtime.cursors import RealtimeCursorCodec
from tbd.realtime.hub import RealtimeHub
from tbd.repositories.outbox import OutboxRepository
from tbd.schemas.realtime import RealtimeEvent

# These are lightweight invalidation hints, not a public event ledger.  Every
# payload must remain safe for every Course member: in particular, Question
# events never expose ``author_user_id`` and private AI results are omitted.
PUBLIC_EVENT_TYPES = frozenset(
    {
        "session.updated",
        "job.updated",
        "question.created",
        "question.updated",
        "reaction.updated",
        "clustering.updated",
    }
)


def project_event(
    event: OutboxEvent, cursor_codec: RealtimeCursorCodec
) -> dict[str, object] | None:
    """Return only public Course-event shapes; internal Outbox work stays private."""

    if event.session_id is None or event.event_type not in PUBLIC_EVENT_TYPES:
        return None
    return RealtimeEvent(
        event_id=event.id,
        type=event.event_type,
        session_id=event.session_id,
        cursor=cursor_codec.encode(event.id),
        resource_version=event.resource_version,
        correlation_id=None,
        occurred_at=event.created_at,
        data=event.payload,
    ).model_dump(mode="json")


class RealtimeOutboxPublisher:
    """Poll the durable Outbox and publish after the owning transaction commits."""

    def __init__(
        self,
        *,
        database: Database,
        hub: RealtimeHub,
        settings: Settings,
        repository: OutboxRepository | None = None,
    ) -> None:
        self._database = database
        self._hub = hub
        self._repository = repository or OutboxRepository()
        self._cursor_codec = RealtimeCursorCodec(settings.auth_secret_key.get_secret_value())
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="goal-realtime-outbox-publisher")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def publish_available(self) -> int:
        """Claim a small batch durably, then fan it out after commit."""

        async with self._database.session_factory() as session:
            async with transaction(session):
                events = await self._repository.claim_available(
                    session, now=datetime.now(UTC), limit=100
                )
        for event in events:
            envelope = project_event(event, self._cursor_codec)
            if envelope is not None:
                await self._hub.publish(envelope)
        return len(events)

    async def _run(self) -> None:
        while True:
            try:
                published = await self.publish_available()
            except Exception:
                # A later poll and REST resync recover delivery. Public responses
                # intentionally never include a database/provider exception here.
                await asyncio.sleep(1)
                continue
            await asyncio.sleep(0 if published else 0.25)
