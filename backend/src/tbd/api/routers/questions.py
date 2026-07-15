"""Anonymous LIVE Question and reaction endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_current_user_id,
    get_db_session,
    get_llm_provider,
    get_optional_idempotency_repository,
    get_settings,
    require_allowed_origin,
)
from tbd.core.config import Settings
from tbd.core.errors import ApiError
from tbd.core.request_hash import canonical_request_hash, idempotency_key_hash
from tbd.db import transaction
from tbd.providers.ai import LLMProvider
from tbd.repositories.idempotency import (
    AcquiredIdempotencyRecord,
    IdempotencyKeyReusedError,
    IdempotencyRepository,
    IdempotencyRequest,
    ProcessingIdempotencyRecord,
    ReplayIdempotencyRecord,
)
from tbd.schemas.clustering import (
    QuestionClusterListResponse,
    QuestionClusterMemberListResponse,
    RepresentativeQuestionResponse,
)
from tbd.schemas.course_qna import CourseQnaArchiveResponse
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.questions import (
    QuestionCreateRequest,
    QuestionCreateResponse,
    QuestionDraftRequest,
    QuestionDraftResponse,
    QuestionListResponse,
    QuestionReactionState,
    QuestionResponse,
)
from tbd.services.course_qna import (
    CourseQnaArchiveService,
    InvalidCourseQnaCursorError,
)
from tbd.services.courses import CourseAccessDeniedError, CourseNotFoundError
from tbd.services.question_clusters import (
    InvalidClusterCursorError,
    QuestionClusterService,
)
from tbd.services.question_drafts import (
    QuestionDraftProviderError,
    QuestionDraftService,
    QuestionDraftValidationError,
)
from tbd.services.questions import (
    InvalidQuestionCursorError,
    QuestionAccessDeniedError,
    QuestionContentValidationError,
    QuestionNotFoundError,
    QuestionRoleRequiredError,
    QuestionService,
    QuestionSessionStateError,
    SelfReactionError,
)

router = APIRouter(tags=["Questions"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
LLMProviderDependency = Annotated[LLMProvider, Depends(get_llm_provider)]
OptionalIdempotency = Annotated[
    IdempotencyRepository | None,
    Depends(get_optional_idempotency_repository),
]
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
PROCESSING_LEASE = timedelta(seconds=60)
QuestionStatus = Literal["OPEN", "SELECTED", "ANSWERED"]
QuestionSort = Literal["POPULAR", "RECENT"]
QuestionClusterScope = Literal["CURRENT", "FINAL"]


def _service(settings: Settings) -> QuestionService:
    return QuestionService(auth_secret=settings.auth_secret_key.get_secret_value())


def _cluster_service(settings: Settings) -> QuestionClusterService:
    return QuestionClusterService(auth_secret=settings.auth_secret_key.get_secret_value())


def _draft_service(provider: LLMProvider) -> QuestionDraftService:
    return QuestionDraftService(provider=provider)


def _course_qna_service(settings: Settings) -> CourseQnaArchiveService:
    return CourseQnaArchiveService(auth_secret=settings.auth_secret_key.get_secret_value())


def _project(question: object, *, reacted_by_me: bool) -> QuestionResponse:
    return QuestionService.project_question(question, reacted_by_me=reacted_by_me)


def _raise_error(error: Exception, *, hide_access: bool = False) -> None:
    if isinstance(error, CourseNotFoundError):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 Course를 찾을 수 없습니다.") from error
    if isinstance(error, CourseAccessDeniedError):
        raise ApiError(
            403, "COURSE_ACCESS_DENIED", "이 Course에 접근할 권한이 없습니다."
        ) from error
    if isinstance(error, InvalidCourseQnaCursorError):
        raise ApiError(400, "INVALID_CURSOR", "Q&A archive cursor를 다시 확인해 주세요.") from error
    if isinstance(error, QuestionNotFoundError) or (
        hide_access and isinstance(error, QuestionAccessDeniedError)
    ):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "요청한 질문을 찾을 수 없습니다.") from error
    if isinstance(error, QuestionAccessDeniedError):
        raise ApiError(
            403, "COURSE_ACCESS_DENIED", "이 Course에 접근할 권한이 없습니다."
        ) from error
    if isinstance(error, QuestionRoleRequiredError):
        raise ApiError(
            403, "ROLE_REQUIRED", "Course 학생만 질문과 반응을 변경할 수 있습니다."
        ) from error
    if isinstance(error, QuestionSessionStateError):
        raise ApiError(
            409,
            "SESSION_STATE_CONFLICT",
            "질문은 진행 중이거나 종료된 class에서 등록하고, 반응은 LIVE class에서만 변경할 수 있습니다.",
        ) from error
    if isinstance(error, SelfReactionError):
        raise ApiError(409, "SELF_REACTION_FORBIDDEN", "내 질문에는 반응할 수 없습니다.") from error
    if isinstance(error, InvalidQuestionCursorError):
        raise ApiError(400, "INVALID_CURSOR", "질문 목록 커서를 다시 확인해 주세요.") from error
    if isinstance(error, InvalidClusterCursorError):
        raise ApiError(400, "INVALID_CURSOR", "클러스터 목록 커서를 다시 확인해 주세요.") from error
    if isinstance(error, QuestionContentValidationError):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "질문 내용을 확인해 주세요.",
            details={
                "field": "content",
                "reason": error.reason,
                "max_length": 300,
                "actual_length": error.actual_length,
            },
        ) from error
    if isinstance(error, QuestionDraftValidationError):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "질문 초안을 확인해 주세요.",
            details={
                "field": "draft",
                "reason": error.reason,
                "max_length": 500,
                "actual_length": error.actual_length,
            },
        ) from error
    if isinstance(error, QuestionDraftProviderError):
        raise ApiError(
            503,
            "AI_PROVIDER_UNAVAILABLE",
            "AI 질문 작성 도움을 지금 사용할 수 없습니다.",
        ) from error
    raise error


@router.get(
    "/courses/{course_id}/qna",
    operation_id="listCourseQnaArchive",
    response_model=CourseQnaArchiveResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def list_course_qna_archive(
    course_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CourseQnaArchiveResponse:
    """Return the Course's anonymous student questions and answered AI targets."""

    try:
        result = await _course_qna_service(settings).list_for_member(
            session,
            course_id=course_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_error(exc)
    return CourseQnaArchiveResponse(items=result.items, next_cursor=result.next_cursor)


@router.get(
    "/sessions/{session_id}/question-clusters",
    response_model=QuestionClusterListResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def list_question_clusters(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    scope: Annotated[QuestionClusterScope, Query()] = "CURRENT",
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> QuestionClusterListResponse:
    try:
        return await _cluster_service(settings).list_for_member(
            session,
            session_id=session_id,
            user_id=user_id,
            scope=scope,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_error(exc)


@router.get(
    "/sessions/{session_id}/question-clusters/{cluster_id}/members",
    response_model=QuestionClusterMemberListResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def list_question_cluster_members(
    session_id: UUID,
    cluster_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> QuestionClusterMemberListResponse:
    try:
        return await _cluster_service(settings).list_members_for_member(
            session,
            session_id=session_id,
            cluster_id=cluster_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_error(exc, hide_access=True)


@router.get(
    "/representative-questions/{representative_question_id}",
    response_model=RepresentativeQuestionResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_representative_question(
    representative_question_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> RepresentativeQuestionResponse:
    try:
        return await _cluster_service(settings).get_representative_for_member(
            session, representative_id=representative_question_id, user_id=user_id
        )
    except Exception as exc:
        _raise_error(exc, hide_access=True)


async def _acquire(
    session: AsyncSession,
    repository: IdempotencyRepository | None,
    *,
    user_id: UUID,
    key: str | None,
    body: dict[str, object],
    now: datetime,
) -> AcquiredIdempotencyRecord | ReplayIdempotencyRecord | None:
    if key is None:
        return None
    if repository is None:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "멱등성 응답 설정을 사용할 수 없습니다.")
    try:
        key_hash = idempotency_key_hash(key)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key를 확인해 주세요.") from exc
    acquired = await repository.acquire(
        session,
        IdempotencyRequest(
            user_id=user_id,
            method="POST",
            route_key="/api/v1/sessions/{session_id}/questions",
            key_hash=key_hash,
            request_hash=canonical_request_hash(
                "POST", "/api/v1/sessions/{session_id}/questions", body
            ),
        ),
        now=now,
        processing_lease=PROCESSING_LEASE,
    )
    if isinstance(acquired, ProcessingIdempotencyRecord):
        raise ApiError(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS", "동일한 요청을 처리하고 있습니다.")
    assert isinstance(acquired, (AcquiredIdempotencyRecord, ReplayIdempotencyRecord))
    return acquired


@router.get(
    "/sessions/{session_id}/questions",
    response_model=QuestionListResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def list_questions(
    session_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    status: Annotated[QuestionStatus | None, Query()] = None,
    sort: Annotated[QuestionSort, Query()] = "POPULAR",
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> QuestionListResponse:
    try:
        items, next_cursor = await _service(settings).list_for_member(
            session,
            session_id=session_id,
            user_id=user_id,
            status=status,
            sort=sort,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_error(exc)
    return QuestionListResponse(
        items=[_project(question, reacted_by_me=reacted) for question, reacted in items],
        next_cursor=next_cursor,
    )


@router.post(
    "/sessions/{session_id}/questions",
    status_code=201,
    response_model=QuestionCreateResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_question(
    session_id: UUID,
    payload: QuestionCreateRequest,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
    idempotency: OptionalIdempotency,
    idempotency_key: IdempotencyHeader = None,
) -> QuestionCreateResponse | JSONResponse:
    now = datetime.now(UTC)
    try:
        async with transaction(session):
            acquired = await _acquire(
                session,
                idempotency,
                user_id=user_id,
                key=idempotency_key,
                body=payload.model_dump(mode="json"),
                now=now,
            )
            if isinstance(acquired, ReplayIdempotencyRecord):
                return JSONResponse(status_code=acquired.status_code, content=acquired.body)
            question, clustering_state = await _service(settings).create(
                session,
                session_id=session_id,
                user_id=user_id,
                content=payload.content,
                now=now,
            )
            result = QuestionCreateResponse(
                question=_project(question, reacted_by_me=False), clustering_state=clustering_state
            )
            if isinstance(acquired, AcquiredIdempotencyRecord):
                assert idempotency is not None
                await idempotency.complete(
                    session,
                    record_id=acquired.record_id,
                    status_code=201,
                    body=result.model_dump(mode="json"),
                    now=now,
                )
    except IdempotencyKeyReusedError as exc:
        raise ApiError(
            409, "IDEMPOTENCY_KEY_REUSED", "같은 멱등 키가 다른 요청에 사용되었습니다."
        ) from exc
    except Exception as exc:
        _raise_error(exc)
    response.headers["Location"] = f"/api/v1/questions/{result.question.id}"
    return result


@router.post(
    "/sessions/{session_id}/question-drafts",
    response_model=QuestionDraftResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def suggest_question_drafts(
    session_id: UUID,
    payload: QuestionDraftRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
    provider: LLMProviderDependency,
) -> QuestionDraftResponse:
    """Return one ephemeral candidate without creating a Question or AIJob."""

    try:
        return await _draft_service(provider).suggest(
            session,
            session_id=session_id,
            user_id=user_id,
            draft=payload.draft,
        )
    except Exception as exc:
        _raise_error(exc)


@router.get(
    "/questions/{question_id}",
    response_model=QuestionResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_question(
    question_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> QuestionResponse:
    try:
        question, reacted_by_me = await _service(settings).get_for_member(
            session, question_id=question_id, user_id=user_id
        )
    except Exception as exc:
        _raise_error(exc, hide_access=True)
    return _project(question, reacted_by_me=reacted_by_me)


@router.put(
    "/questions/{question_id}/reaction",
    response_model=QuestionReactionState,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def add_question_reaction(
    question_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> QuestionReactionState:
    try:
        async with transaction(session):
            question, _ = await _service(settings).add_reaction(
                session, question_id=question_id, user_id=user_id
            )
    except Exception as exc:
        _raise_error(exc, hide_access=True)
    return QuestionReactionState(
        question_id=question.id, reaction_count=question.reaction_count, reacted_by_me=True
    )


@router.delete(
    "/questions/{question_id}/reaction",
    status_code=204,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def remove_question_reaction(
    question_id: UUID,
    session: DatabaseSession,
    user_id: CurrentUserId,
    settings: SettingsDependency,
) -> Response:
    try:
        async with transaction(session):
            await _service(settings).remove_reaction(
                session, question_id=question_id, user_id=user_id
            )
    except Exception as exc:
        _raise_error(exc, hide_access=True)
    return Response(status_code=204)
