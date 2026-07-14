"""Unit tests for the Google OpenID Connect provider boundary."""

import pytest

from tbd.core.config import AppEnvironment, Settings
from tbd.providers.google_oidc import GoogleOIDCClient, OIDCConfigurationError

pytestmark = pytest.mark.unit


def test_google_authorization_url_contains_oidc_and_pkce_parameters() -> None:
    """The provider redirect requests code flow, OIDC scopes, nonce, and S256 PKCE."""

    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        google_oidc_client_id="client-id",
        google_oidc_client_secret="client-secret",
    )

    url = GoogleOIDCClient(settings).authorization_url(
        state="state-value",
        nonce="nonce-value",
        code_challenge="challenge-value",
    )

    assert "response_type=code" in url
    assert "scope=openid+email+profile" in url
    assert "state=state-value" in url
    assert "nonce=nonce-value" in url
    assert "code_challenge=challenge-value" in url
    assert "code_challenge_method=S256" in url


def test_unconfigured_google_provider_fails_without_exposing_credentials() -> None:
    """Health can start without credentials, but login cannot silently proceed."""

    provider = GoogleOIDCClient(Settings(_env_file=None, app_env=AppEnvironment.TEST))

    with pytest.raises(OIDCConfigurationError):
        provider.authorization_url(state="state", nonce="nonce", code_challenge="challenge")
