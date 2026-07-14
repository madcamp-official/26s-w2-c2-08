"""One-time ticket HTTP API and Course member event WebSocket."""

import asyncio
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_current_user_id,
    get_db_session,
    get_settings,
    require_allowed_origin,
)
from tbd.core.config import Settings
from tbd.core.errors import ApiError
from tbd.db import transaction
from tbd.realtime.cursors import RealtimeCursorCodec
from tbd.realtime.hub import RealtimeConnection, RealtimeHub
from tbd.realtime.publisher import project_event
from tbd.repositories.outbox import OutboxRepository
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.realtime import (
    RealtimeEvent,
    RealtimeTicketCreateRequest,
    RealtimeTicketResponse,
)
from tbd.services.realtime import (
    RealtimeAccessDeniedError,
    RealtimeScopeDeniedError,
    RealtimeSessionNotFoundError,
    RealtimeTicketInvalidError,
    RealtimeTicketService,
)

router = APIRouter(tags=["Realtime"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

RESYNC_RESOURCES = ["SESSION", "TRANSCRIPT", "QUESTIONS", "CLUSTERS", "ANSWERS", "JOBS"]


@router.post(
    "/realtime-tickets",
    status_code=201,
    response_model=RealtimeTicketResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def create_realtime_ticket(
    payload: RealtimeTicketCreateRequest,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> RealtimeTicketResponse:
    """Issue a cache-forbidden, short-lived secret for one channel upgrade."""

    try:
        async with transaction(session):
            issued = await RealtimeTicketService(settings).issue(
                session,
                user_id=user_id,
                session_id=payload.session_id,
                scope=payload.scope,
                resume_cursor=payload.resume_cursor,
            )
    except RealtimeSessionNotFoundError as exc:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 class를 찾을 수 없습니다.") from exc
    except RealtimeAccessDeniedError as exc:
        raise ApiError(403, "COURSE_ACCESS_DENIED", "이 class에 접근할 권한이 없습니다.") from exc
    except RealtimeScopeDeniedError as exc:
        raise ApiError(403, "ROLE_REQUIRED", "이 실시간 연결을 사용할 권한이 없습니다.") from exc

    response.headers["Cache-Control"] = "no-store"
    return RealtimeTicketResponse(
        ticket=issued.ticket,
        session_id=issued.session_id,
        scope=issued.scope,
        expires_at=issued.expires_at,
    )


def _connection_event(
    *,
    session_id: UUID,
    event_type: str,
    data: dict[str, object],
) -> dict[str, object]:
    """Build a non-durable connection control envelope."""

    return RealtimeEvent(
        event_id=uuid4(),
        type=event_type,
        session_id=session_id,
        cursor=None,
        resource_version=None,
        correlation_id=None,
        occurred_at=datetime.now(UTC),
        data=data,
    ).model_dump(mode="json")


async def _replay(
    websocket: WebSocket,
    *,
    session_id: UUID,
    resume_cursor: str | None,
) -> tuple[str, list[dict[str, object]]]:
    """Return replayed public events or request canonical REST recovery."""

    if resume_cursor is None:
        return "FRESH", []
    codec = RealtimeCursorCodec(websocket.app.state.settings.auth_secret_key.get_secret_value())
    cursor_id = codec.decode(resume_cursor)
    if cursor_id is None:
        return "RESYNC_REQUIRED", []
    database = websocket.app.state.database
    async with database.session_factory() as session:
        events = await OutboxRepository().replay_after(
            session,
            session_id=session_id,
            cursor_event_id=cursor_id,
            limit=500,
        )
    if events is None:
        return "RESYNC_REQUIRED", []
    return (
        "REPLAYED",
        [envelope for event in events if (envelope := project_event(event, codec)) is not None],
    )


async def _consume_event_ticket(
    websocket: WebSocket,
    *,
    session_id: UUID,
    token: str | None,
):
    database = websocket.app.state.database
    try:
        async with database.session_factory() as session:
            async with transaction(session):
                return await RealtimeTicketService(
                    websocket.app.state.settings
                ).consume_event_ticket(
                    session,
                    token=token,
                    session_id=session_id,
                )
    except RealtimeTicketInvalidError:
        await websocket.close(code=4401)
    except RealtimeSessionNotFoundError:
        await websocket.close(code=4404)
    except RealtimeAccessDeniedError:
        await websocket.close(code=4403)
    return None


async def _serve_connection(
    websocket: WebSocket,
    *,
    connection: RealtimeConnection,
) -> None:
    """Wait for server notifications while still detecting client disconnects."""

    while True:
        incoming = asyncio.create_task(websocket.receive())
        next_event = asyncio.create_task(connection.events.get())
        resync = asyncio.create_task(connection.resync_required.wait())
        done, pending = await asyncio.wait(
            {incoming, next_event, resync}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if incoming in done:
            message = incoming.result()
            if message["type"] == "websocket.disconnect":
                return
        if resync in done:
            connection.resync_required.clear()
            await websocket.send_json(
                _connection_event(
                    session_id=connection.session_id,
                    event_type="resync.required",
                    data={"reason": "CURSOR_EXPIRED", "resources": RESYNC_RESOURCES},
                )
            )
        if next_event in done:
            await websocket.send_json(next_event.result())


@router.websocket("/ws/sessions/{session_id}")
async def session_event_websocket(
    websocket: WebSocket,
    session_id: UUID,
    ticket: str | None = None,
) -> None:
    """Connect one Course member to public, replayable Session invalidations."""

    access = await _consume_event_ticket(websocket, session_id=session_id, token=ticket)
    if access is None:
        return
    await websocket.accept()
    resume_status, replayed = await _replay(
        websocket, session_id=session_id, resume_cursor=access.resume_cursor
    )
    hub: RealtimeHub = websocket.app.state.realtime_hub
    connection = RealtimeConnection(
        session_id=session_id,
        user_id=access.user_id,
        role=access.role,
    )
    await hub.add(connection)
    try:
        await websocket.send_json(
            _connection_event(
                session_id=session_id,
                event_type="connection.ready",
                data={
                    "connection_id": str(uuid4()),
                    "role": access.role,
                    "server_time": datetime.now(UTC).isoformat(),
                    "heartbeat_interval_ms": 20000,
                    "resume_status": resume_status,
                },
            )
        )
        if resume_status == "RESYNC_REQUIRED":
            await websocket.send_json(
                _connection_event(
                    session_id=session_id,
                    event_type="resync.required",
                    data={"reason": "CURSOR_UNKNOWN", "resources": RESYNC_RESOURCES},
                )
            )
        else:
            for event in replayed:
                await websocket.send_json(event)
        await _serve_connection(websocket, connection=connection)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return
    finally:
        await hub.remove(connection)
