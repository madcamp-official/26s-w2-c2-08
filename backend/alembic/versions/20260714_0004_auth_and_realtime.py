"""Create authentication session, OAuth transaction, and realtime ticket tables.

Revision ID: 20260714_0004
Revises: 20260714_0003
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0004"
down_revision: str | None = "20260714_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create short-lived authentication and realtime credentials."""

    op.create_table(
        "auth_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("expires_at > created_at", name="auth_sessions_expiry_after_created_ck"),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name="auth_sessions_token_hash_length_ck"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="auth_sessions_token_hash_uq"),
    )
    op.create_index(
        "auth_sessions_user_active_idx",
        "auth_sessions",
        ["user_id", "expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("auth_sessions_expiry_idx", "auth_sessions", ["expires_at"])

    op.create_table(
        "oauth_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("browser_binding_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("state_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("nonce_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("pkce_verifier_ciphertext", postgresql.BYTEA(), nullable=False),
        sa.Column("pkce_verifier_nonce", postgresql.BYTEA(), nullable=False),
        sa.Column("encryption_key_version", sa.SmallInteger(), nullable=False),
        sa.Column("return_to", sa.Text(), nullable=False, server_default=sa.text("'/'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "return_to LIKE '/%' AND return_to NOT LIKE '//%'",
            name="oauth_transactions_return_to_path_ck",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="oauth_transactions_expiry_after_created_ck"
        ),
        sa.CheckConstraint(
            "expires_at <= created_at + interval '10 minutes'",
            name="oauth_transactions_expiry_window_ck",
        ),
        sa.CheckConstraint(
            "octet_length(state_hash) = 32 AND octet_length(nonce_hash) = 32",
            name="oauth_transactions_state_nonce_length_ck",
        ),
        sa.CheckConstraint(
            "octet_length(pkce_verifier_nonce) = 12", name="oauth_transactions_pkce_nonce_length_ck"
        ),
        sa.CheckConstraint("encryption_key_version > 0", name="oauth_transactions_key_version_ck"),
        sa.UniqueConstraint(
            "browser_binding_hash", name="oauth_transactions_browser_binding_hash_uq"
        ),
        sa.UniqueConstraint("state_hash", name="oauth_transactions_state_hash_uq"),
    )
    op.create_index("oauth_transactions_expiry_idx", "oauth_transactions", ["expires_at"])

    op.create_table(
        "realtime_tickets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("ticket_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("resume_cursor", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "scope IN ('SESSION_EVENTS_READ', 'SESSION_AUDIO_WRITE')",
            name="realtime_tickets_scope_ck",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="realtime_tickets_expiry_after_created_ck"
        ),
        sa.CheckConstraint(
            "expires_at <= created_at + interval '60 seconds'",
            name="realtime_tickets_expiry_window_ck",
        ),
        sa.CheckConstraint(
            "octet_length(ticket_hash) = 32", name="realtime_tickets_hash_length_ck"
        ),
        sa.CheckConstraint(
            "scope = 'SESSION_EVENTS_READ' OR resume_cursor IS NULL",
            name="realtime_tickets_resume_scope_ck",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("ticket_hash", name="realtime_tickets_ticket_hash_uq"),
    )
    op.create_index("realtime_tickets_expiry_idx", "realtime_tickets", ["expires_at"])
    op.create_index(
        "realtime_tickets_user_idx", "realtime_tickets", ["user_id", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    """Drop transient credential tables before their owners."""

    op.drop_table("realtime_tickets")
    op.drop_table("oauth_transactions")
    op.drop_table("auth_sessions")
