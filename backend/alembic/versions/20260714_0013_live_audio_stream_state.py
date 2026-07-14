"""Persist live audio publisher and ACK watermarks.

Revision ID: 20260714_0013
Revises: 20260714_0012
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0013"
down_revision: str | None = "20260714_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add only opaque publisher progress, never PCM or a stream ID plaintext."""

    op.add_column(
        "session_recordings",
        sa.Column(
            "last_received_sequence", sa.BigInteger(), nullable=False, server_default=sa.text("-1")
        ),
    )
    op.add_column(
        "session_recordings",
        sa.Column(
            "last_processed_sequence", sa.BigInteger(), nullable=False, server_default=sa.text("-1")
        ),
    )
    op.add_column(
        "session_recordings",
        sa.Column(
            "last_captured_offset_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "session_recordings",
        sa.Column("live_audio_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "session_recordings_last_received_sequence_ck",
        "session_recordings",
        "last_received_sequence >= -1",
    )
    op.create_check_constraint(
        "session_recordings_last_processed_sequence_ck",
        "session_recordings",
        "last_processed_sequence BETWEEN -1 AND last_received_sequence",
    )
    op.create_check_constraint(
        "session_recordings_last_capture_offset_ck",
        "session_recordings",
        "last_captured_offset_ms >= 0",
    )
    op.alter_column("session_recordings", "last_received_sequence", server_default=None)
    op.alter_column("session_recordings", "last_processed_sequence", server_default=None)
    op.alter_column("session_recordings", "last_captured_offset_ms", server_default=None)


def downgrade() -> None:
    """Remove runtime-only audio progress before the original recording ledger."""

    op.drop_constraint(
        "session_recordings_last_capture_offset_ck", "session_recordings", type_="check"
    )
    op.drop_constraint(
        "session_recordings_last_processed_sequence_ck", "session_recordings", type_="check"
    )
    op.drop_constraint(
        "session_recordings_last_received_sequence_ck", "session_recordings", type_="check"
    )
    op.drop_column("session_recordings", "live_audio_lease_expires_at")
    op.drop_column("session_recordings", "last_captured_offset_ms")
    op.drop_column("session_recordings", "last_processed_sequence")
    op.drop_column("session_recordings", "last_received_sequence")
