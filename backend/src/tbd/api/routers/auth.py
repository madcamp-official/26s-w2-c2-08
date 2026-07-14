"""Google OAuth redirects and server session logout endpoints."""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_db_session,
    get_google_oidc_provider,
    get_settings,
    require_allowed_origin,
)
from tbd.core.config import Settings
from tbd.core.errors import ApiError
from tbd.models.users import User
from tbd.providers.google_oidc import (
    GoogleOIDCProvider,
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCProviderUnavailable,
)
from tbd.schemas.auth import (
    AuthenticatedUserResponse,
    EmailPasswordLoginRequest,
    EmailPasswordRegisterRequest,
)
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.users import UserResponse
from tbd.services.auth_sessions import (
    AuthSessionService,
    EmailAlreadyRegisteredError,
    IdentityEmailConflictError,
    InvalidCredentialsError,
)
from tbd.services.oauth import (
    InvalidOAuthTransactionError,
    InvalidReturnToError,
    OAuthFlowService,
)

router = APIRouter(prefix="/auth", tags=["Auth"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ProviderDependency = Annotated[GoogleOIDCProvider, Depends(get_google_oidc_provider)]
REQUEST_ID_RESPONSE_HEADER = {
    "X-Request-ID": {
        "description": "요청 추적용 식별자. 요청 값을 수용하거나 서버가 생성한다.",
        "schema": {"type": "string"},
    }
}


def _set_oauth_cookie(response: Response, value: str, settings: Settings) -> None:
    response.set_cookie(
        "goal_oauth",
        value,
        max_age=settings.auth_oauth_ttl_seconds,
        path="/api/v1/auth/google",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _clear_oauth_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        "goal_oauth",
        path="/api/v1/auth/google",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _set_session_cookie(response: Response, value: str, settings: Settings) -> None:
    response.set_cookie(
        "goal_session",
        value,
        max_age=settings.auth_session_ttl_seconds,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        "goal_session",
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _frontend_location(settings: Settings, return_to: str) -> str:
    return f"{settings.frontend_origin.rstrip('/')}{return_to}"


@router.get(
    "/google/start",
    status_code=302,
    responses={
        302: {"headers": REQUEST_ID_RESPONSE_HEADER},
        400: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
        503: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
    },
)
async def start_google_login(
    session: DatabaseSession,
    settings: SettingsDependency,
    provider: ProviderDependency,
    return_to: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Create an OAuth transaction and redirect the browser to Google."""

    try:
        started = await OAuthFlowService(settings).start(
            session,
            provider,
            return_to=return_to,
        )
    except InvalidReturnToError as exc:
        raise ApiError(
            400,
            "INVALID_RETURN_TO",
            "로그인 후 이동 경로가 유효하지 않습니다.",
        ) from exc
    except (OIDCConfigurationError, OIDCProviderUnavailable) as exc:
        raise ApiError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "로그인 서비스를 사용할 수 없습니다.",
        ) from exc

    response = RedirectResponse(started.authorization_url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    _set_oauth_cookie(response, started.browser_binding, settings)
    return response


@router.get(
    "/google/callback",
    status_code=302,
    responses={
        302: {"headers": REQUEST_ID_RESPONSE_HEADER},
        400: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
        503: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
    },
)
async def complete_google_login(
    session: DatabaseSession,
    settings: SettingsDependency,
    provider: ProviderDependency,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    goal_oauth: Annotated[str | None, Cookie()] = None,
    goal_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Consume an OAuth callback and rotate the server session."""

    flow = OAuthFlowService(settings)
    try:
        consumed = await flow.consume(
            session,
            browser_binding=goal_oauth,
            state=state,
        )
    except InvalidOAuthTransactionError as exc:
        raise ApiError(
            400,
            "INVALID_OAUTH_TRANSACTION",
            "로그인 요청이 만료되었거나 이미 사용되었습니다.",
        ) from exc

    if error is not None:
        query = urlencode({"auth_error": "cancelled", "return_to": consumed.return_to})
        response = RedirectResponse(
            f"{settings.frontend_origin.rstrip('/')}/login?{query}",
            status_code=302,
        )
        response.headers["Cache-Control"] = "no-store"
        _clear_oauth_cookie(response, settings)
        return response

    if not code:
        raise ApiError(
            400,
            "INVALID_OAUTH_TRANSACTION",
            "로그인 응답이 유효하지 않습니다.",
        )

    try:
        identity = await provider.exchange_code(code=code, code_verifier=consumed.code_verifier)
    except (OIDCConfigurationError, OIDCProviderUnavailable) as exc:
        raise ApiError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "로그인 서비스를 사용할 수 없습니다.",
        ) from exc
    except OIDCAuthenticationError as exc:
        raise ApiError(
            400,
            "INVALID_OAUTH_TRANSACTION",
            "로그인 응답이 유효하지 않습니다.",
        ) from exc

    if not flow.nonce_matches(consumed.nonce_hash, identity.nonce):
        raise ApiError(
            400,
            "INVALID_OAUTH_TRANSACTION",
            "로그인 응답이 유효하지 않습니다.",
        )

    try:
        established = await AuthSessionService(settings).establish(
            session,
            identity=identity,
            existing_token=goal_session,
        )
    except IdentityEmailConflictError as exc:
        raise ApiError(
            409,
            "IDENTITY_EMAIL_CONFLICT",
            "이 이메일은 다른 로그인 방식으로 이미 등록되어 있습니다.",
        ) from exc
    response = RedirectResponse(
        _frontend_location(settings, consumed.return_to),
        status_code=302,
    )
    response.headers["Cache-Control"] = "no-store"
    _clear_oauth_cookie(response, settings)
    _set_session_cookie(response, established.token, settings)
    return response


def _authenticated_user_response(user: User) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse(
        user=UserResponse.model_validate(
            {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.primary_email,
                "avatar_url": user.avatar_url,
            }
        )
    )


@router.post(
    "/email/register",
    status_code=201,
    response_model=AuthenticatedUserResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        403: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
        409: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
        422: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
    },
)
async def register_with_email_password(
    payload: EmailPasswordRegisterRequest,
    session: DatabaseSession,
    settings: SettingsDependency,
    goal_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Create a local account and establish the same server session as OAuth."""

    try:
        established = await AuthSessionService(settings).register_with_password(
            session,
            display_name=payload.display_name,
            email=payload.email,
            password=payload.password,
            existing_token=goal_session,
        )
    except (EmailAlreadyRegisteredError, IntegrityError) as exc:
        raise ApiError(
            409,
            "EMAIL_ALREADY_REGISTERED",
            "이미 등록된 이메일입니다. 기존 로그인 방식을 사용해 주세요.",
        ) from exc

    response = Response(
        content=_authenticated_user_response(established.user).model_dump_json(),
        status_code=201,
        media_type="application/json",
    )
    _set_session_cookie(response, established.token, settings)
    return response


@router.post(
    "/email/login",
    response_model=AuthenticatedUserResponse,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        401: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
        403: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
        422: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
    },
)
async def login_with_email_password(
    payload: EmailPasswordLoginRequest,
    session: DatabaseSession,
    settings: SettingsDependency,
    goal_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Verify a local credential and rotate the opaque browser session."""

    try:
        established = await AuthSessionService(settings).authenticate_password(
            session,
            email=payload.email,
            password=payload.password,
            existing_token=goal_session,
        )
    except InvalidCredentialsError as exc:
        raise ApiError(
            401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다."
        ) from exc

    response = Response(
        content=_authenticated_user_response(established.user).model_dump_json(),
        media_type="application/json",
    )
    _set_session_cookie(response, established.token, settings)
    return response


@router.post(
    "/logout",
    status_code=204,
    dependencies=[Depends(require_allowed_origin)],
    responses={
        204: {"headers": REQUEST_ID_RESPONSE_HEADER},
        403: {"model": ErrorResponse, "headers": REQUEST_ID_RESPONSE_HEADER},
    },
)
async def logout(
    session: DatabaseSession,
    settings: SettingsDependency,
    goal_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Revoke the server session and expire the browser cookie idempotently."""

    await AuthSessionService(settings).revoke(session, goal_session)
    response = Response(status_code=204)
    _clear_session_cookie(response, settings)
    return response
