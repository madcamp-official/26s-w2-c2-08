"""Integration checks for one-time OAuth state, nonce, and PKCE storage."""

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from fakes import FakeGoogleOIDCProvider
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.models.auth import OAuthTransaction
from tbd.services.oauth import (
    InvalidOAuthTransactionError,
    InvalidReturnToError,
    OAuthFlowService,
)

pytestmark = pytest.mark.integration


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
        auth_secret_key="test-auth-secret-that-is-longer-than-thirty-two-bytes",
    )


def test_oauth_transaction_stores_only_protected_material(
    migrated_database_url: str,
) -> None:
    """State, nonce, browser binding, and PKCE verifier plaintext never enter PostgreSQL."""

    async def exercise() -> None:
        settings = _settings(migrated_database_url)
        database = create_database(settings)
        provider = FakeGoogleOIDCProvider()
        service = OAuthFlowService(settings)
        try:
            async with database.session_factory() as session:
                started = await service.start(session, provider, return_to="/account?tab=security")
                transaction = await session.scalar(select(OAuthTransaction))

            assert transaction is not None
            request = provider.authorization_requests[0]
            assert transaction.return_to == "/account?tab=security"
            assert transaction.browser_binding_hash != started.browser_binding.encode()
            assert transaction.state_hash != request["state"].encode()
            assert transaction.nonce_hash != request["nonce"].encode()
            assert request["code_challenge"] not in transaction.pkce_verifier_ciphertext.hex()

            parsed_state = parse_qs(urlsplit(started.authorization_url).query)["state"][0]
            async with database.session_factory() as session:
                consumed = await service.consume(
                    session,
                    browser_binding=started.browser_binding,
                    state=parsed_state,
                )

            assert consumed.return_to == "/account?tab=security"
            assert service.nonce_matches(consumed.nonce_hash, request["nonce"])
            assert AuthCryptoChallenge.matches(consumed.code_verifier, request["code_challenge"])
        finally:
            await database.dispose()

    asyncio.run(exercise())


class AuthCryptoChallenge:
    """Avoid exposing verifier values while asserting the persisted PKCE round trip."""

    @staticmethod
    def matches(verifier: str, challenge: str) -> bool:
        from tbd.auth.security import AuthCrypto

        return AuthCrypto.pkce_challenge(verifier) == challenge


def test_oauth_state_cannot_be_consumed_twice(migrated_database_url: str) -> None:
    """A replay is rejected after the first callback transaction commits."""

    async def exercise() -> None:
        settings = _settings(migrated_database_url)
        database = create_database(settings)
        provider = FakeGoogleOIDCProvider()
        service = OAuthFlowService(settings)
        try:
            async with database.session_factory() as session:
                started = await service.start(session, provider, return_to="/")
            state = provider.authorization_requests[0]["state"]

            async with database.session_factory() as session:
                await service.consume(
                    session,
                    browser_binding=started.browser_binding,
                    state=state,
                )
            async with database.session_factory() as session:
                with pytest.raises(InvalidOAuthTransactionError):
                    await service.consume(
                        session,
                        browser_binding=started.browser_binding,
                        state=state,
                    )
        finally:
            await database.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "return_to",
    ["https://evil.example", "//evil.example/path", "/api/v1/me", "/safe\\evil"],
)
def test_return_to_rejects_external_and_backend_routes(return_to: str) -> None:
    """Login completion cannot become an open redirect or enter an API route."""

    with pytest.raises(InvalidReturnToError):
        OAuthFlowService.validate_return_to(return_to)
