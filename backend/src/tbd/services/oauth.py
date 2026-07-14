"""One-time OAuth transaction creation and callback consumption."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.auth.security import AuthCrypto, InvalidCiphertextError
from tbd.core.config import Settings
from tbd.models.auth import OAuthTransaction
from tbd.providers.google_oidc import GoogleOIDCProvider


class InvalidReturnToError(Exception):
    """Raised when a post-login route could leave the trusted frontend."""


class InvalidOAuthTransactionError(Exception):
    """Raised for missing, expired, consumed, or cryptographically invalid callbacks."""


@dataclass(frozen=True)
class OAuthStart:
    """Values returned to the browser and provider after creating a transaction."""

    authorization_url: str
    browser_binding: str


@dataclass(frozen=True)
class ConsumedOAuthTransaction:
    """Validated callback inputs retained after the one-time row is consumed."""

    return_to: str
    code_verifier: str
    nonce_hash: bytes


class OAuthFlowService:
    """Persist OAuth anti-forgery material without storing plaintext secrets."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())

    @staticmethod
    def validate_return_to(value: str | None) -> str:
        """Return a canonical frontend-relative route or reject it."""

        candidate = value or "/"
        if any(ord(character) < 32 for character in candidate) or "\\" in candidate:
            raise InvalidReturnToError

        parsed = urlsplit(candidate)
        if (
            parsed.scheme
            or parsed.netloc
            or not parsed.path.startswith("/")
            or parsed.path.startswith("//")
            or parsed.path == "/api"
            or parsed.path.startswith("/api/")
        ):
            raise InvalidReturnToError
        return urlunsplit(("", "", parsed.path, parsed.query, parsed.fragment))

    async def start(
        self,
        session: AsyncSession,
        provider: GoogleOIDCProvider,
        *,
        return_to: str | None,
    ) -> OAuthStart:
        """Create a short-lived transaction and provider authorization redirect."""

        safe_return_to = self.validate_return_to(return_to)
        browser_binding = self._crypto.opaque_token()
        state = self._crypto.opaque_token()
        nonce = self._crypto.opaque_token()
        code_verifier = self._crypto.opaque_token()
        ciphertext, encryption_nonce = self._crypto.encrypt_pkce_verifier(code_verifier)
        authorization_url = provider.authorization_url(
            state=state,
            nonce=nonce,
            code_challenge=self._crypto.pkce_challenge(code_verifier),
        )
        now = datetime.now(UTC)

        async with session.begin():
            session.add(
                OAuthTransaction(
                    browser_binding_hash=self._crypto.hash_token(
                        "oauth-browser-binding", browser_binding
                    ),
                    state_hash=self._crypto.hash_token("oauth-state", state),
                    nonce_hash=self._crypto.hash_token("oauth-nonce", nonce),
                    pkce_verifier_ciphertext=ciphertext,
                    pkce_verifier_nonce=encryption_nonce,
                    encryption_key_version=1,
                    return_to=safe_return_to,
                    expires_at=now + timedelta(seconds=self._settings.auth_oauth_ttl_seconds),
                    created_at=now,
                )
            )

        return OAuthStart(
            authorization_url=authorization_url,
            browser_binding=browser_binding,
        )

    async def consume(
        self,
        session: AsyncSession,
        *,
        browser_binding: str | None,
        state: str | None,
    ) -> ConsumedOAuthTransaction:
        """Atomically consume a callback before any external provider request."""

        if not browser_binding or not state:
            raise InvalidOAuthTransactionError

        now = datetime.now(UTC)
        async with session.begin():
            transaction = await session.scalar(
                select(OAuthTransaction)
                .where(
                    OAuthTransaction.browser_binding_hash
                    == self._crypto.hash_token("oauth-browser-binding", browser_binding),
                    OAuthTransaction.state_hash == self._crypto.hash_token("oauth-state", state),
                    OAuthTransaction.expires_at > now,
                    OAuthTransaction.consumed_at.is_(None),
                )
                .with_for_update()
            )
            if transaction is None:
                raise InvalidOAuthTransactionError
            transaction.consumed_at = now
            try:
                code_verifier = self._crypto.decrypt_pkce_verifier(
                    transaction.pkce_verifier_ciphertext,
                    transaction.pkce_verifier_nonce,
                )
            except (InvalidCiphertextError, UnicodeDecodeError) as exc:
                raise InvalidOAuthTransactionError from exc
            result = ConsumedOAuthTransaction(
                return_to=transaction.return_to,
                code_verifier=code_verifier,
                nonce_hash=transaction.nonce_hash,
            )

        return result

    def nonce_matches(self, expected_hash: bytes, nonce: str) -> bool:
        """Compare a verified ID token nonce with the stored one-way value."""

        return self._crypto.hash_token("oauth-nonce", nonce) == expected_hash
