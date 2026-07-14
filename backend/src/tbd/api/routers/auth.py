"""Google OAuth redirects and server session logout endpoints."""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.api.dependencies import (
    get_db_session,
    get_google_oidc_provider,
    get_settings,
    require_allowed_origin,
)
from tbd.core.config import Settings
from tbd.core.errors import ApiError
from tbd.providers.google_oidc import (
    GoogleOIDCProvider,
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCProviderUnavailable,
)
from tbd.schemas.errors import ErrorResponse
from tbd.services.auth_sessions import AuthSessionService
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

    established = await AuthSessionService(settings).establish(
        session,
        identity=identity,
        existing_token=goal_session,
    )
    response = RedirectResponse(
        _frontend_location(settings, consumed.return_to),
        status_code=302,
    )
    response.headers["Cache-Control"] = "no-store"
    _clear_oauth_cookie(response, settings)
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
