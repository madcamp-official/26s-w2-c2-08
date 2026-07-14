"""Google OpenID Connect boundary with a replaceable test interface."""

import asyncio
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token

from tbd.core.config import Settings

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class OIDCConfigurationError(Exception):
    """Raised when Google OIDC credentials are not configured."""


class OIDCAuthenticationError(Exception):
    """Raised when a provider response cannot authenticate an identity."""


class OIDCProviderUnavailable(Exception):
    """Raised when the external provider cannot complete a request."""


@dataclass(frozen=True)
class GoogleIdentity:
    """Verified claims needed to map one Google subject to a GOAL user."""

    subject: str
    nonce: str
    display_name: str
    email: str | None
    avatar_url: str | None


class GoogleOIDCProvider(Protocol):
    """Minimal provider interface owned by the authentication service."""

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        """Build the provider authorization redirect."""

    async def exchange_code(self, *, code: str, code_verifier: str) -> GoogleIdentity:
        """Exchange a code and return locally verified identity claims."""


class GoogleOIDCClient:
    """Production Google provider implementation using code flow and ID tokens."""

    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.google_oidc_client_id
        self._client_secret = (
            settings.google_oidc_client_secret.get_secret_value()
            if settings.google_oidc_client_secret is not None
            else None
        )
        self._redirect_uri = settings.google_oidc_redirect_uri

    def _require_configuration(self) -> tuple[str, str]:
        if not self._client_id or not self._client_secret:
            raise OIDCConfigurationError
        return self._client_id, self._client_secret

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        client_id, _ = self._require_configuration()
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> GoogleIdentity:
        client_id, client_secret = self._require_configuration()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    GOOGLE_TOKEN_ENDPOINT,
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": self._redirect_uri,
                        "grant_type": "authorization_code",
                        "code_verifier": code_verifier,
                    },
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise OIDCProviderUnavailable from exc

        if response.status_code >= 500:
            raise OIDCProviderUnavailable
        if response.status_code >= 400:
            raise OIDCAuthenticationError

        try:
            encoded_id_token = response.json()["id_token"]
            claims = await asyncio.to_thread(
                google_id_token.verify_oauth2_token,
                encoded_id_token,
                GoogleAuthRequest(),
                client_id,
            )
            subject = claims["sub"]
            nonce = claims["nonce"]
        except google_auth_exceptions.TransportError as exc:
            raise OIDCProviderUnavailable from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise OIDCAuthenticationError from exc

        if not isinstance(subject, str) or not subject or not isinstance(nonce, str) or not nonce:
            raise OIDCAuthenticationError

        email = claims.get("email") if claims.get("email_verified") is True else None
        display_name = claims.get("name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = email or "Google 사용자"
        avatar_url = claims.get("picture")

        return GoogleIdentity(
            subject=subject,
            nonce=nonce,
            display_name=display_name.strip(),
            email=email if isinstance(email, str) else None,
            avatar_url=avatar_url if isinstance(avatar_url, str) else None,
        )
