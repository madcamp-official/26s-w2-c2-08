"""Internal user mapping and opaque server session lifecycle."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.auth.security import AuthCrypto
from tbd.core.config import Settings
from tbd.models.auth import AuthSession
from tbd.models.users import User, UserAuthIdentity
from tbd.providers.google_oidc import GoogleIdentity


@dataclass(frozen=True)
class EstablishedSession:
    """New browser token and the internal user it authenticates."""

    token: str
    user: User


class InvalidSessionError(Exception):
    """Raised when an opaque token does not resolve to an active user session."""


class AuthSessionService:
    """Issue, rotate, and revoke hashed server-side sessions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())

    async def establish(
        self,
        session: AsyncSession,
        *,
        identity: GoogleIdentity,
        existing_token: str | None,
    ) -> EstablishedSession:
        """Map a verified Google subject and rotate any existing browser session."""

        now = datetime.now(UTC)
        token = self._crypto.opaque_token()
        async with session.begin():
            auth_identity = await session.scalar(
                select(UserAuthIdentity).where(
                    UserAuthIdentity.provider == "GOOGLE",
                    UserAuthIdentity.provider_subject == identity.subject,
                )
            )
            if auth_identity is None:
                user = User(
                    display_name=identity.display_name,
                    primary_email=identity.email,
                    avatar_url=identity.avatar_url,
                )
                session.add(user)
                await session.flush()
                auth_identity = UserAuthIdentity(
                    user_id=user.id,
                    provider="GOOGLE",
                    provider_subject=identity.subject,
                    email_snapshot=identity.email,
                )
                session.add(auth_identity)
            else:
                user = await session.get(User, auth_identity.user_id)
                if user is None or user.deleted_at is not None:
                    raise RuntimeError("verified identity is not linked to an active user")
                user.display_name = identity.display_name
                user.primary_email = identity.email
                user.avatar_url = identity.avatar_url
                auth_identity.email_snapshot = identity.email

            if existing_token:
                await session.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.token_hash
                        == self._crypto.hash_token("session", existing_token),
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )

            session.add(
                AuthSession(
                    user_id=user.id,
                    token_hash=self._crypto.hash_token("session", token),
                    expires_at=now + timedelta(seconds=self._settings.auth_session_ttl_seconds),
                    last_seen_at=now,
                )
            )

        return EstablishedSession(token=token, user=user)

    async def revoke(self, session: AsyncSession, token: str | None) -> None:
        """Idempotently revoke the presented session token."""

        if not token:
            return
        async with session.begin():
            await session.execute(
                update(AuthSession)
                .where(
                    AuthSession.token_hash == self._crypto.hash_token("session", token),
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )

    async def authenticate(self, session: AsyncSession, token: str) -> User:
        """Resolve an active session and throttle last-seen writes without extending expiry."""

        now = datetime.now(UTC)
        async with session.begin():
            auth_session = await session.scalar(
                select(AuthSession).where(
                    AuthSession.token_hash == self._crypto.hash_token("session", token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
            )
            if auth_session is None:
                raise InvalidSessionError
            user = await session.get(User, auth_session.user_id)
            if user is None or user.deleted_at is not None:
                raise InvalidSessionError

            last_seen_before = now - timedelta(
                seconds=self._settings.auth_last_seen_interval_seconds
            )
            if auth_session.last_seen_at is None or auth_session.last_seen_at <= last_seen_before:
                auth_session.last_seen_at = now

        return user
