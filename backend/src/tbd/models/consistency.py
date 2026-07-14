"""Idempotency and transactional-outbox database models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class IdempotencyRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Encrypted terminal responses and active leases for idempotent writes."""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "http_method",
            "route_key",
            "idempotency_key_hash",
            name="idempotency_records_request_uq",
        ),
        CheckConstraint(
            "NOT purge_on_session_end OR session_id IS NOT NULL",
            name="idempotency_records_purge_scope_ck",
        ),
        CheckConstraint(
            "http_method IN ('POST', 'PUT', 'PATCH', 'DELETE')",
            name="idempotency_records_method_ck",
        ),
        CheckConstraint(
            "char_length(btrim(route_key)) > 0", name="idempotency_records_route_key_ck"
        ),
        CheckConstraint(
            "state IN ('PROCESSING', 'COMPLETED', 'FAILED')", name="idempotency_records_state_ck"
        ),
        CheckConstraint(
            "response_status IS NULL OR response_status BETWEEN 100 AND 599",
            name="idempotency_records_status_ck",
        ),
        CheckConstraint(
            "octet_length(idempotency_key_hash) = 32 AND octet_length(request_hash) = 32",
            name="idempotency_records_hash_length_ck",
        ),
        CheckConstraint(
            "response_body_nonce IS NULL OR octet_length(response_body_nonce) = 12",
            name="idempotency_records_nonce_length_ck",
        ),
        CheckConstraint(
            "(response_body_ciphertext IS NULL AND response_body_nonce IS NULL AND response_key_version IS NULL) "
            "OR (response_body_ciphertext IS NOT NULL AND response_body_nonce IS NOT NULL "
            "AND response_key_version IS NOT NULL)",
            name="idempotency_records_response_encryption_ck",
        ),
        CheckConstraint(
            "response_key_version IS NULL OR response_key_version > 0",
            name="idempotency_records_key_version_ck",
        ),
        CheckConstraint(
            "(state = 'PROCESSING' AND completed_at IS NULL AND expires_at IS NULL) "
            "OR (state IN ('COMPLETED', 'FAILED') AND completed_at IS NOT NULL "
            "AND expires_at = completed_at + interval '24 hours')",
            name="idempotency_records_terminal_expiry_ck",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="idempotency_records_completed_after_created_ck",
        ),
        CheckConstraint(
            "state = 'PROCESSING' OR response_status IS NOT NULL",
            name="idempotency_records_terminal_response_ck",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    purge_on_session_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    http_method: Mapped[str] = mapped_column(Text, nullable=False)
    route_key: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    request_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PROCESSING'"))
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    response_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    response_body_ciphertext: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    response_body_nonce: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    response_key_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)


class OutboxEvent(UUIDPrimaryKeyMixin, Base):
    """At-least-once events created in the same transaction as domain changes."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(partition_key)) > 0", name="outbox_events_partition_key_ck"
        ),
        CheckConstraint("char_length(btrim(event_type)) > 0", name="outbox_events_type_ck"),
        CheckConstraint(
            "resource_version IS NULL OR resource_version > 0",
            name="outbox_events_resource_version_ck",
        ),
        CheckConstraint("publish_attempt >= 0", name="outbox_events_publish_attempt_ck"),
    )

    session_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    partition_key: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    available_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    publish_attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
