"""Create idempotency and transactional-outbox tables.

Revision ID: 20260714_0009
Revises: 20260714_0008
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0009"
down_revision: str | None = "20260714_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _install_updated_at_trigger(table_name: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table_name}_set_updated_at "
        f"BEFORE UPDATE ON {table_name} "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def upgrade() -> None:
    """Create durable request de-duplication and at-least-once event storage."""

    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purge_on_session_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("http_method", sa.Text(), nullable=False),
        sa.Column("route_key", sa.Text(), nullable=False),
        sa.Column("idempotency_key_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("request_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'PROCESSING'")),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_body_ciphertext", postgresql.BYTEA(), nullable=True),
        sa.Column("response_body_nonce", postgresql.BYTEA(), nullable=True),
        sa.Column("response_key_version", sa.SmallInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("NOT purge_on_session_end OR session_id IS NOT NULL", name="idempotency_records_purge_scope_ck"),
        sa.CheckConstraint("http_method IN ('POST', 'PUT', 'PATCH', 'DELETE')", name="idempotency_records_method_ck"),
        sa.CheckConstraint("char_length(btrim(route_key)) > 0", name="idempotency_records_route_key_ck"),
        sa.CheckConstraint("state IN ('PROCESSING', 'COMPLETED', 'FAILED')", name="idempotency_records_state_ck"),
        sa.CheckConstraint("response_status IS NULL OR response_status BETWEEN 100 AND 599", name="idempotency_records_status_ck"),
        sa.CheckConstraint("octet_length(idempotency_key_hash) = 32 AND octet_length(request_hash) = 32", name="idempotency_records_hash_length_ck"),
        sa.CheckConstraint("response_body_nonce IS NULL OR octet_length(response_body_nonce) = 12", name="idempotency_records_nonce_length_ck"),
        sa.CheckConstraint(
            "(response_body_ciphertext IS NULL AND response_body_nonce IS NULL AND response_key_version IS NULL) "
            "OR (response_body_ciphertext IS NOT NULL AND response_body_nonce IS NOT NULL "
            "AND response_key_version IS NOT NULL)",
            name="idempotency_records_response_encryption_ck",
        ),
        sa.CheckConstraint("response_key_version IS NULL OR response_key_version > 0", name="idempotency_records_key_version_ck"),
        sa.CheckConstraint(
            "(state = 'PROCESSING' AND completed_at IS NULL AND expires_at IS NULL) "
            "OR (state IN ('COMPLETED', 'FAILED') AND completed_at IS NOT NULL "
            "AND expires_at = completed_at + interval '24 hours')",
            name="idempotency_records_terminal_expiry_ck",
        ),
        sa.CheckConstraint("completed_at IS NULL OR completed_at >= created_at", name="idempotency_records_completed_after_created_ck"),
        sa.CheckConstraint("state = 'PROCESSING' OR response_status IS NOT NULL", name="idempotency_records_terminal_response_ck"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "http_method", "route_key", "idempotency_key_hash", name="idempotency_records_request_uq"),
    )
    _install_updated_at_trigger("idempotency_records")

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("partition_key", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("resource_version", sa.BigInteger(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(btrim(partition_key)) > 0", name="outbox_events_partition_key_ck"),
        sa.CheckConstraint("char_length(btrim(event_type)) > 0", name="outbox_events_type_ck"),
        sa.CheckConstraint("resource_version IS NULL OR resource_version > 0", name="outbox_events_resource_version_ck"),
        sa.CheckConstraint("publish_attempt >= 0", name="outbox_events_publish_attempt_ck"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    """Drop consistency records after all domain records are gone."""

    op.drop_table("outbox_events")
    op.drop_table("idempotency_records")
