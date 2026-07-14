"""REST-only requester-scoped Summary and Chat endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_current_user_id,
    get_db_session,
    get_idempotency_repository,
    require_allowed_origin,
)
from tbd.core.errors import ApiError
from tbd.core.request_hash import canonical_request_hash, idempotency_key_hash
from tbd.db import transaction
from tbd.models.materials import TranscriptSegment
from tbd.repositories.idempotency import (
    AcquiredIdempotencyRecord,
    IdempotencyKeyReusedError,
    IdempotencyRepository,
    IdempotencyRequest,
    ProcessingIdempotencyRecord,
    ReplayIdempotencyRecord,
)
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.jobs import AIJobAcceptedResponse, project_ai_job
from tbd.schemas.personal_ai import (
    ChatCreateRequest,
    ChatListResponse,
    ChatMessageCreateRequest,
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatResponse,
    ChatTurnAcceptedResponse,
    LectureSummaryResponse,
    SummaryCreateRequest,
    SummaryListResponse,
)
from tbd.services.personal_ai import (
    ChatResponseInProgressError,
    PersonalAIContentValidationError,
    PersonalAINotFoundError,
    PersonalAIService,
    PersonalAIStateConflictError,
    SummarySourceUnavailableError,
    SummaryTranscriptNotReadyError,
    chat_response,
    summary_response,
)

router = APIRouter(tags=["Summaries", "Chats"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
Idempotency = Annotated[IdempotencyRepository, Depends(get_idempotency_repository)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1)]
AllowedOrigin = Annotated[None, Depends(require_allowed_origin)]
PROCESSING_LEASE = timedelta(seconds=60)


def _service() -> PersonalAIService:
    return PersonalAIService()


async def _acquire(
    session: AsyncSession,
    repository: IdempotencyRepository,
    *,
    user_id: UUID,
    session_id: UUID,
    route_key: str,
    key: str,
    body: dict[str, object],
    purge_on_session_end: bool,
    now: datetime,
) -> AcquiredIdempotencyRecord | ReplayIdempotencyRecord:
    try:
        key_hash = idempotency_key_hash(key)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.") from exc
    acquired = await repository.acquire(
        session,
        IdempotencyRequest(
            user_id=user_id,
            session_id=session_id,
            purge_on_session_end=purge_on_session_end,
            method="POST",
            route_key=route_key,
            key_hash=key_hash,
            request_hash=canonical_request_hash("POST", route_key, body),
        ),
        now=now,
        processing_lease=PROCESSING_LEASE,
    )
    if isinstance(acquired, ProcessingIdempotencyRecord):
        raise ApiError(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS", "동일한 요청을 처리하고 있습니다.")
    assert isinstance(acquired, (AcquiredIdempotencyRecord, ReplayIdempotencyRecord))
    return acquired


def _raise(error: Exception) -> NoReturn:
    if isinstance(error, PersonalAINotFoundError):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 리소스를 찾을 수 없습니다.") from error
    if isinstance(error, PersonalAIStateConflictError):
        raise ApiError(
            409, "SESSION_STATE_CONFLICT", "현재 class 상태에서는 요청을 수행할 수 없습니다."
        ) from error
    if isinstance(error, SummaryTranscriptNotReadyError):
        raise ApiError(
            409,
            "SUMMARY_TRANSCRIPT_NOT_READY",
            "아직 확정된 강의 내용이 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from error
    if isinstance(error, SummarySourceUnavailableError):
        raise ApiError(
            409,
            "SUMMARY_SOURCE_UNAVAILABLE",
            "Transcript 처리 문제로 요약을 만들지 못했습니다.",
        ) from error
    if isinstance(error, ChatResponseInProgressError):
        raise ApiError(
            409, "CHAT_RESPONSE_IN_PROGRESS", "이 대화의 답변을 생성하고 있습니다."
        ) from error
    if isinstance(error, PersonalAIContentValidationError):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Chat 메시지 내용을 확인해 주세요.",
            details={
                "field": "content",
                "reason": error.reason,
                "max_length": 2000,
                "actual_length": error.actual_length,
            },
        ) from error
    raise error


async def _project_summary(session: AsyncSession, summary: object) -> LectureSummaryResponse:
    start = await session.scalar(
        select(TranscriptSegment.sequence).where(
            TranscriptSegment.id == summary.source_start_segment_id
        )
    )
    end = await session.scalar(
        select(TranscriptSegment.sequence).where(
            TranscriptSegment.id == summary.source_end_segment_id
        )
    )
    assert start is not None and end is not None
    return summary_response(summary, start_sequence=int(start), end_sequence=int(end))


def _replay_or_purged(record: ReplayIdempotencyRecord) -> JSONResponse:
    if record.status_code == 410:
        raise ApiError(
            410,
            "LIVE_AI_RESULT_PURGED",
            "수업 종료로 개인 AI 결과가 삭제되었습니다.",
        )
    return JSONResponse(status_code=record.status_code, content=record.body)


@router.get(
    "/sessions/{session_id}/summaries",
    response_model=SummaryListResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def list_summaries(
    session_id: UUID,
    summary_type: Annotated[str, Query(pattern="^(LIVE|FINAL)$")],
    session: DatabaseSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SummaryListResponse:
    try:
        summaries, status, reason = await _service().list_summaries(
            session,
            session_id=session_id,
            user_id=user_id,
            summary_type=summary_type,
            limit=limit,
        )
        return SummaryListResponse(
            summary_status=status,
            summary_reason=reason,
            items=[await _project_summary(session, summary) for summary in summaries],
            next_cursor=None,
        )
    except Exception as exc:
        _raise(exc)


@router.post(
    "/sessions/{session_id}/summaries",
    status_code=202,
    response_model=AIJobAcceptedResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def request_summary(
    session_id: UUID,
    request_body: SummaryCreateRequest,
    idempotency_key: IdempotencyKey,
    session: DatabaseSession,
    user_id: CurrentUserId,
    idempotency: Idempotency,
    _allowed_origin: AllowedOrigin,
) -> AIJobAcceptedResponse | JSONResponse:
    now = datetime.now(UTC)
    route_key = "/api/v1/sessions/{session_id}/summaries"
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                session_id=session_id,
                route_key=route_key,
                key=idempotency_key,
                body=request_body.model_dump(mode="json"),
                purge_on_session_end=True,
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return _replay_or_purged(acquired)
            result = await _service().request_live_summary(
                session,
                session_id=session_id,
                user_id=user_id,
                requested_range=request_body.range,
                now=now,
            )
            response = AIJobAcceptedResponse(job=project_ai_job(result.job))
            await idempotency.complete(
                session,
                record_id=acquired.record_id,
                status_code=202,
                body=response.model_dump(mode="json"),
                now=now,
            )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except Exception as exc:
        _raise(exc)
    return response


@router.get(
    "/summaries/{summary_id}",
    response_model=LectureSummaryResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_summary(
    summary_id: UUID, session: DatabaseSession, user_id: CurrentUserId
) -> LectureSummaryResponse:
    try:
        summary = await _service().get_summary(session, summary_id=summary_id, user_id=user_id)
        return await _project_summary(session, summary)
    except Exception as exc:
        _raise(exc)


@router.get(
    "/sessions/{session_id}/chats",
    response_model=ChatListResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def list_chats(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ChatListResponse:
    try:
        chats = await _service().list_chats(
            session, session_id=session_id, user_id=user_id, limit=limit
        )
        return ChatListResponse(items=[chat_response(chat) for chat in chats], next_cursor=None)
    except Exception as exc:
        _raise(exc)


@router.post(
    "/sessions/{session_id}/chats",
    status_code=201,
    response_model=ChatResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_chat(
    session_id: UUID,
    request_body: ChatCreateRequest,
    idempotency_key: IdempotencyKey,
    session: DatabaseSession,
    user_id: CurrentUserId,
    idempotency: Idempotency,
    _allowed_origin: AllowedOrigin,
    response: Response,
) -> ChatResponse | JSONResponse:
    now = datetime.now(UTC)
    route_key = "/api/v1/sessions/{session_id}/chats"
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                session_id=session_id,
                route_key=route_key,
                key=idempotency_key,
                body=request_body.model_dump(mode="json"),
                purge_on_session_end=request_body.mode == "LIVE",
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return _replay_or_purged(acquired)
            chat = await _service().create_chat(
                session, session_id=session_id, user_id=user_id, mode=request_body.mode
            )
            result = chat_response(chat)
            await idempotency.complete(
                session,
                record_id=acquired.record_id,
                status_code=201,
                body=result.model_dump(mode="json"),
                now=now,
            )
            response.headers["Location"] = f"/api/v1/chats/{chat.id}"
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except Exception as exc:
        _raise(exc)
    return result


@router.get(
    "/chats/{chat_id}",
    response_model=ChatResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_chat(chat_id: UUID, session: DatabaseSession, user_id: CurrentUserId) -> ChatResponse:
    try:
        return chat_response(await _service().get_chat(session, chat_id=chat_id, user_id=user_id))
    except Exception as exc:
        _raise(exc)


@router.get(
    "/chats/{chat_id}/messages",
    response_model=ChatMessageListResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def list_messages(
    chat_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ChatMessageListResponse:
    try:
        messages = await _service().list_messages(
            session, chat_id=chat_id, user_id=user_id, limit=limit
        )
        return ChatMessageListResponse(
            items=[await _service().project_message(session, message) for message in messages],
            next_cursor=None,
        )
    except Exception as exc:
        _raise(exc)


@router.post(
    "/chats/{chat_id}/messages",
    status_code=202,
    response_model=ChatTurnAcceptedResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_message(
    chat_id: UUID,
    request_body: ChatMessageCreateRequest,
    idempotency_key: IdempotencyKey,
    session: DatabaseSession,
    user_id: CurrentUserId,
    idempotency: Idempotency,
    _allowed_origin: AllowedOrigin,
) -> ChatTurnAcceptedResponse | JSONResponse:
    now = datetime.now(UTC)
    route_key = "/api/v1/chats/{chat_id}/messages"
    try:
        async with transaction(session):
            chat = await _service().get_chat(session, chat_id=chat_id, user_id=user_id)
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                session_id=chat.session_id,
                route_key=route_key,
                key=idempotency_key,
                body=request_body.model_dump(mode="json"),
                purge_on_session_end=chat.mode == "LIVE",
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return _replay_or_purged(acquired)
            created = await _service().create_chat_turn(
                session, chat_id=chat_id, user_id=user_id, content=request_body.content, now=now
            )
            result = ChatTurnAcceptedResponse(
                user_message=await _service().project_message(session, created.user_message),
                job=project_ai_job(created.job),
            )
            await idempotency.complete(
                session,
                record_id=acquired.record_id,
                status_code=202,
                body=result.model_dump(mode="json"),
                now=now,
            )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except Exception as exc:
        _raise(exc)
    return result


@router.get(
    "/chat-messages/{message_id}",
    response_model=ChatMessageResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_message(
    message_id: UUID, session: DatabaseSession, user_id: CurrentUserId
) -> ChatMessageResponse:
    try:
        message = await _service().get_message(session, message_id=message_id, user_id=user_id)
        return await _service().project_message(session, message)
    except Exception as exc:
        _raise(exc)
