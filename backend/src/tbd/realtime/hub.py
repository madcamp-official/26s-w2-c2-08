"""Process-local fan-out hub; PostgreSQL Outbox remains the replay source."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(eq=False)
class RealtimeConnection:
    """One connected member waiting for safe public event envelopes."""

    session_id: UUID
    user_id: UUID
    role: str
    events: asyncio.Queue[dict[str, object]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=100)
    )
    resync_required: asyncio.Event = field(default_factory=asyncio.Event)


class RealtimeHub:
    """Deliver notifications to local sockets without treating memory as state."""

    def __init__(self) -> None:
        self._connections: dict[UUID, set[RealtimeConnection]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def add(self, connection: RealtimeConnection) -> None:
        async with self._lock:
            self._connections[connection.session_id].add(connection)

    async def remove(self, connection: RealtimeConnection) -> None:
        async with self._lock:
            connections = self._connections.get(connection.session_id)
            if connections is None:
                return
            connections.discard(connection)
            if not connections:
                self._connections.pop(connection.session_id, None)

    async def publish(self, envelope: dict[str, object]) -> None:
        """Fan out without blocking a publisher on one slow browser connection."""

        session_id = UUID(str(envelope["session_id"]))
        async with self._lock:
            targets = tuple(self._connections.get(session_id, ()))
        for connection in targets:
            try:
                connection.events.put_nowait(envelope)
            except asyncio.QueueFull:
                # Dropping an invalidation is safe only when the client is told to
                # reload canonical REST state before it processes further events.
                connection.resync_required.set()
