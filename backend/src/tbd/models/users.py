"""User and external identity database models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user without an account-wide course role."""

    __tablename__ = "users"
    __table_args__ = (
        Index("users_active_idx", "id", postgresql_where="deleted_at IS NULL"),
        Index(
            "users_active_primary_email_uq",
            "primary_email",
            unique=True,
            postgresql_where=text("primary_email IS NOT NULL AND deleted_at IS NULL"),
        ),
    )

    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    primary_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)


class UserAuthIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A stable external authentication subject linked to one user."""

    __tablename__ = "user_auth_identities"
    __table_args__ = (
        CheckConstraint("provider IN ('GOOGLE')", name="user_auth_identities_provider_ck"),
        Index("user_auth_identities_user_idx", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_subject: Mapped[str] = mapped_column(Text, nullable=False)
    email_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserPasswordCredential(TimestampMixin, Base):
    """One non-recoverable password verifier for one local-login user."""

    __tablename__ = "user_password_credentials"

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
