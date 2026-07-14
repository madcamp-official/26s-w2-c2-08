"""Authentication session, OAuth transaction, and realtime ticket models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import UUIDPrimaryKeyMixin


class AuthSession(UUIDPrimaryKeyMixin, Base):
    """A hashed server-side browser session token."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="auth_sessions_expiry_after_created_ck"),
        CheckConstraint("octet_length(token_hash) = 32", name="auth_sessions_token_hash_length_ck"),
        Index(
            "auth_sessions_user_active_idx",
            "user_id",
            "expires_at",
            postgresql_where="revoked_at IS NULL",
        ),
        Index("auth_sessions_expiry_idx", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class OAuthTransaction(UUIDPrimaryKeyMixin, Base):
    """A short-lived browser-bound OAuth state, nonce, and PKCE record."""

    __tablename__ = "oauth_transactions"
    __table_args__ = (
        CheckConstraint(
            "return_to LIKE '/%' AND return_to NOT LIKE '//%'",
            name="oauth_transactions_return_to_path_ck",
        ),
        CheckConstraint(
            "expires_at > created_at", name="oauth_transactions_expiry_after_created_ck"
        ),
        CheckConstraint(
            "expires_at <= created_at + interval '10 minutes'",
            name="oauth_transactions_expiry_window_ck",
        ),
        CheckConstraint(
            "octet_length(state_hash) = 32 AND octet_length(nonce_hash) = 32",
            name="oauth_transactions_state_nonce_length_ck",
        ),
        CheckConstraint(
            "octet_length(pkce_verifier_nonce) = 12",
            name="oauth_transactions_pkce_nonce_length_ck",
        ),
        CheckConstraint("encryption_key_version > 0", name="oauth_transactions_key_version_ck"),
        Index("oauth_transactions_expiry_idx", "expires_at"),
    )

    browser_binding_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False, unique=True)
    state_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False, unique=True)
    nonce_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    pkce_verifier_ciphertext: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    pkce_verifier_nonce: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    return_to: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'/'"))
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class RealtimeTicket(UUIDPrimaryKeyMixin, Base):
    """A one-time short-lived ticket used to upgrade a realtime connection."""

    __tablename__ = "realtime_tickets"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('SESSION_EVENTS_READ', 'SESSION_AUDIO_WRITE')",
            name="realtime_tickets_scope_ck",
        ),
        CheckConstraint("expires_at > created_at", name="realtime_tickets_expiry_after_created_ck"),
        CheckConstraint(
            "expires_at <= created_at + interval '60 seconds'",
            name="realtime_tickets_expiry_window_ck",
        ),
        CheckConstraint("octet_length(ticket_hash) = 32", name="realtime_tickets_hash_length_ck"),
        CheckConstraint(
            "scope = 'SESSION_EVENTS_READ' OR resume_cursor IS NULL",
            name="realtime_tickets_resume_scope_ck",
        ),
        Index("realtime_tickets_expiry_idx", "expires_at"),
        Index("realtime_tickets_user_idx", "user_id", text("created_at DESC")),
    )

    ticket_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    resume_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
