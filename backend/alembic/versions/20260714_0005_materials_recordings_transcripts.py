"""Create material, recording, upload, and transcript ledger tables.

Revision ID: 20260714_0005
Revises: 20260714_0004
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0005"
down_revision: str | None = "20260714_0004"
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
    """Create durable material, recording, and transcript state without Job cycles."""

    op.create_table(
        "lecture_materials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False, server_default=sa.text("'application/pdf'")),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("processing_status", sa.Text(), nullable=False, server_default=sa.text("'UPLOADED'")),
        sa.Column("processed_by_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("processed_by_job_attempt", sa.Integer(), nullable=True),
        sa.Column("detached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.CheckConstraint("mime_type = 'application/pdf'", name="lecture_materials_mime_type_ck"),
        sa.CheckConstraint("length(btrim(original_filename)) > 0", name="lecture_materials_original_filename_ck"),
        sa.CheckConstraint("length(btrim(display_name)) > 0", name="lecture_materials_display_name_ck"),
        sa.CheckConstraint("byte_size BETWEEN 1 AND 100000000", name="lecture_materials_byte_size_ck"),
        sa.CheckConstraint("page_count IS NULL OR page_count > 0", name="lecture_materials_page_count_ck"),
        sa.CheckConstraint(
            "processing_status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED')",
            name="lecture_materials_processing_status_ck",
        ),
        sa.CheckConstraint(
            "(processed_by_job_id IS NULL) = (processed_by_job_attempt IS NULL)",
            name="lecture_materials_processed_job_pair_ck",
        ),
        sa.CheckConstraint("processing_status <> 'READY' OR processed_by_job_id IS NOT NULL", name="lecture_materials_ready_job_ck"),
        sa.CheckConstraint("processing_status <> 'READY' OR page_count IS NOT NULL", name="lecture_materials_ready_page_count_ck"),
        sa.CheckConstraint("version > 0", name="lecture_materials_version_ck"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("id", "session_id", name="lecture_materials_id_session_uq"),
        sa.UniqueConstraint("storage_key", name="lecture_materials_storage_key_uq"),
    )
    _install_updated_at_trigger("lecture_materials")

    op.create_table(
        "session_recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publisher_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("publisher_client_stream_id_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'CAPTURING'")),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("capture_started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("capture_ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.CheckConstraint("octet_length(publisher_client_stream_id_hash) = 32", name="session_recordings_publisher_hash_length_ck"),
        sa.CheckConstraint(
            "status IN ('CAPTURING', 'UPLOAD_PENDING', 'UPLOADING', 'UPLOADED', 'FAILED')",
            name="session_recordings_status_ck",
        ),
        sa.CheckConstraint("byte_size IS NULL OR byte_size > 0", name="session_recordings_byte_size_ck"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="session_recordings_duration_ck"),
        sa.CheckConstraint("content_type IS NULL OR length(btrim(content_type)) > 0", name="session_recordings_content_type_ck"),
        sa.CheckConstraint(
            "num_nonnulls(content_type, byte_size, duration_ms, storage_key, uploaded_at) IN (0, 5)",
            name="session_recordings_final_metadata_ck",
        ),
        sa.CheckConstraint("(status = 'UPLOADED') = (storage_key IS NOT NULL)", name="session_recordings_uploaded_key_ck"),
        sa.CheckConstraint("(status = 'FAILED') = (failed_at IS NOT NULL)", name="session_recordings_failed_at_ck"),
        sa.CheckConstraint(
            "status NOT IN ('UPLOAD_PENDING', 'UPLOADING', 'UPLOADED') OR capture_ended_at IS NOT NULL",
            name="session_recordings_upload_after_capture_ck",
        ),
        sa.CheckConstraint("capture_ended_at IS NULL OR capture_ended_at >= capture_started_at", name="session_recordings_capture_time_ck"),
        sa.CheckConstraint("uploaded_at IS NULL OR uploaded_at >= capture_ended_at", name="session_recordings_uploaded_time_ck"),
        sa.CheckConstraint("version > 0", name="session_recordings_version_ck"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publisher_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("session_id", name="session_recordings_session_uq"),
        sa.UniqueConstraint("id", "session_id", name="session_recordings_id_session_uq"),
        sa.UniqueConstraint("storage_key", name="session_recordings_storage_key_uq"),
    )
    _install_updated_at_trigger("session_recordings")

    op.create_table(
        "recording_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("recording_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("offset_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("declared_content_type", sa.Text(), nullable=False),
        sa.Column("declared_duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("temporary_storage_key", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.CheckConstraint("status IN ('ACTIVE', 'COMPLETED', 'EXPIRED', 'FAILED')", name="recording_uploads_status_ck"),
        sa.CheckConstraint("offset_bytes BETWEEN 0 AND total_bytes", name="recording_uploads_offset_ck"),
        sa.CheckConstraint("total_bytes > 0", name="recording_uploads_total_bytes_ck"),
        sa.CheckConstraint("length(btrim(declared_content_type)) > 0", name="recording_uploads_content_type_ck"),
        sa.CheckConstraint("declared_duration_ms >= 0", name="recording_uploads_duration_ck"),
        sa.CheckConstraint("expires_at > created_at", name="recording_uploads_expiry_ck"),
        sa.CheckConstraint("(status = 'ACTIVE') = (terminal_at IS NULL)", name="recording_uploads_terminal_at_ck"),
        sa.CheckConstraint("status <> 'COMPLETED' OR offset_bytes = total_bytes", name="recording_uploads_completed_offset_ck"),
        sa.CheckConstraint("version > 0", name="recording_uploads_version_ck"),
        sa.ForeignKeyConstraint(["recording_id"], ["session_recordings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("temporary_storage_key", name="recording_uploads_temporary_storage_key_uq"),
    )
    _install_updated_at_trigger("recording_uploads")

    op.create_table(
        "transcript_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'FINALIZING'")),
        sa.Column("recording_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_job_attempt", sa.Integer(), nullable=True),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("version > 0", name="transcript_versions_version_ck"),
        sa.CheckConstraint("source IN ('LIVE', 'RECORDING')", name="transcript_versions_source_ck"),
        sa.CheckConstraint("status IN ('FINALIZING', 'FINALIZED', 'FAILED', 'EMPTY')", name="transcript_versions_status_ck"),
        sa.CheckConstraint(
            "(created_by_job_id IS NULL) = (created_by_job_attempt IS NULL)",
            name="transcript_versions_created_job_pair_ck",
        ),
        sa.CheckConstraint(
            "(source = 'LIVE' AND recording_id IS NULL AND created_by_job_id IS NULL) "
            "OR (source = 'RECORDING' AND recording_id IS NOT NULL AND created_by_job_id IS NOT NULL)",
            name="transcript_versions_source_target_ck",
        ),
        sa.CheckConstraint(
            "(status = 'FINALIZING' AND finalized_at IS NULL AND failed_at IS NULL) "
            "OR (status IN ('FINALIZED', 'EMPTY') AND finalized_at IS NOT NULL AND failed_at IS NULL) "
            "OR (status = 'FAILED' AND finalized_at IS NULL AND failed_at IS NOT NULL)",
            name="transcript_versions_terminal_state_ck",
        ),
        sa.CheckConstraint("status NOT IN ('EMPTY', 'FAILED') OR last_sequence = 0", name="transcript_versions_empty_failed_sequence_ck"),
        sa.CheckConstraint("last_sequence >= 0", name="transcript_versions_last_sequence_ck"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "version", name="transcript_versions_session_version_uq"),
        sa.UniqueConstraint("id", "session_id", name="transcript_versions_id_session_uq"),
    )
    _install_updated_at_trigger("transcript_versions")

    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("utterance_id", sa.Text(), nullable=True),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("recording_start_ms", sa.BigInteger(), nullable=True),
        sa.Column("recording_end_ms", sa.BigInteger(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_job_attempt", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("sequence > 0", name="transcript_segments_sequence_ck"),
        sa.CheckConstraint("start_ms >= 0", name="transcript_segments_start_ck"),
        sa.CheckConstraint("end_ms >= start_ms", name="transcript_segments_time_ck"),
        sa.CheckConstraint("utterance_id IS NULL OR length(btrim(utterance_id)) > 0", name="transcript_segments_utterance_ck"),
        sa.CheckConstraint("(recording_start_ms IS NULL) = (recording_end_ms IS NULL)", name="transcript_segments_recording_pair_ck"),
        sa.CheckConstraint("recording_end_ms IS NULL OR recording_end_ms >= recording_start_ms", name="transcript_segments_recording_time_ck"),
        sa.CheckConstraint("length(btrim(text)) > 0", name="transcript_segments_text_ck"),
        sa.CheckConstraint(
            "(created_by_job_id IS NULL) = (created_by_job_attempt IS NULL)",
            name="transcript_segments_created_job_pair_ck",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["transcript_version_id", "session_id"],
            ["transcript_versions.id", "transcript_versions.session_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("transcript_version_id", "sequence", name="transcript_segments_version_sequence_uq"),
        sa.UniqueConstraint("id", "transcript_version_id", "session_id", name="transcript_segments_id_version_session_uq"),
    )

    op.create_table(
        "transcript_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("start_ms >= 0", name="transcript_gaps_start_ck"),
        sa.CheckConstraint("end_ms IS NULL OR end_ms >= start_ms", name="transcript_gaps_time_ck"),
        sa.CheckConstraint("NOT is_final OR end_ms IS NOT NULL", name="transcript_gaps_final_end_ck"),
        sa.CheckConstraint(
            "reason IN ('SERVER_STATE_LOST', 'SEQUENCE_GAP', 'CLIENT_DISCONNECTED', 'BACKPRESSURE_DROP')",
            name="transcript_gaps_reason_ck",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["transcript_version_id", "session_id"],
            ["transcript_versions.id", "transcript_versions.session_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "transcript_version_id", "session_id", name="transcript_gaps_id_version_session_uq"),
    )


def downgrade() -> None:
    """Drop transcript children before their recording and session parents."""

    op.drop_table("transcript_gaps")
    op.drop_table("transcript_segments")
    op.drop_table("transcript_versions")
    op.drop_table("recording_uploads")
    op.drop_table("session_recordings")
    op.drop_table("lecture_materials")
