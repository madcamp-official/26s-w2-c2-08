"""Material, recording, upload, and durable transcript models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class LectureMaterial(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """A PDF attached to a lecture session until it is detached."""

    __tablename__ = "lecture_materials"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="lecture_materials_id_session_uq"),
        CheckConstraint("mime_type = 'application/pdf'", name="lecture_materials_mime_type_ck"),
        CheckConstraint(
            "length(btrim(original_filename)) > 0", name="lecture_materials_original_filename_ck"
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0", name="lecture_materials_display_name_ck"
        ),
        CheckConstraint("byte_size BETWEEN 1 AND 100000000", name="lecture_materials_byte_size_ck"),
        CheckConstraint(
            "page_count IS NULL OR page_count > 0", name="lecture_materials_page_count_ck"
        ),
        CheckConstraint(
            "processing_status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED')",
            name="lecture_materials_processing_status_ck",
        ),
        CheckConstraint(
            "(processed_by_job_id IS NULL) = (processed_by_job_attempt IS NULL)",
            name="lecture_materials_processed_job_pair_ck",
        ),
        CheckConstraint(
            "processing_status <> 'READY' OR processed_by_job_id IS NOT NULL",
            name="lecture_materials_ready_job_ck",
        ),
        CheckConstraint(
            "processing_status <> 'READY' OR page_count IS NOT NULL",
            name="lecture_materials_ready_page_count_ck",
        ),
        CheckConstraint("version > 0", name="lecture_materials_version_ck"),
        ForeignKeyConstraint(
            ["processed_by_job_id", "session_id"],
            ["ai_jobs.id", "ai_jobs.session_id"],
            name="lecture_materials_processed_job_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'application/pdf'")
    )
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'UPLOADED'")
    )
    processed_by_job_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    processed_by_job_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detached_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SessionRecording(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """The one logical recording aggregate of a lecture session."""

    __tablename__ = "session_recordings"
    __table_args__ = (
        UniqueConstraint("session_id", name="session_recordings_session_uq"),
        UniqueConstraint("id", "session_id", name="session_recordings_id_session_uq"),
        CheckConstraint(
            "octet_length(publisher_client_stream_id_hash) = 32",
            name="session_recordings_publisher_hash_length_ck",
        ),
        CheckConstraint(
            "last_received_sequence >= -1",
            name="session_recordings_last_received_sequence_ck",
        ),
        CheckConstraint(
            "last_processed_sequence BETWEEN -1 AND last_received_sequence",
            name="session_recordings_last_processed_sequence_ck",
        ),
        CheckConstraint(
            "last_captured_offset_ms >= 0",
            name="session_recordings_last_capture_offset_ck",
        ),
        CheckConstraint(
            "status IN ('CAPTURING', 'UPLOAD_PENDING', 'UPLOADING', 'UPLOADED', 'FAILED')",
            name="session_recordings_status_ck",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size > 0", name="session_recordings_byte_size_ck"
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="session_recordings_duration_ck"
        ),
        CheckConstraint(
            "content_type IS NULL OR length(btrim(content_type)) > 0",
            name="session_recordings_content_type_ck",
        ),
        CheckConstraint(
            "num_nonnulls(content_type, byte_size, duration_ms, storage_key, uploaded_at) IN (0, 5)",
            name="session_recordings_final_metadata_ck",
        ),
        CheckConstraint(
            "(status = 'UPLOADED') = (storage_key IS NOT NULL)",
            name="session_recordings_uploaded_key_ck",
        ),
        CheckConstraint(
            "(status = 'FAILED') = (failed_at IS NOT NULL)", name="session_recordings_failed_at_ck"
        ),
        CheckConstraint(
            "status NOT IN ('UPLOAD_PENDING', 'UPLOADING', 'UPLOADED') OR capture_ended_at IS NOT NULL",
            name="session_recordings_upload_after_capture_ck",
        ),
        CheckConstraint(
            "capture_ended_at IS NULL OR capture_ended_at >= capture_started_at",
            name="session_recordings_capture_time_ck",
        ),
        CheckConstraint(
            "uploaded_at IS NULL OR uploaded_at >= capture_ended_at",
            name="session_recordings_uploaded_time_ck",
        ),
        CheckConstraint("version > 0", name="session_recordings_version_ck"),
        Index(
            "session_recordings_retention_due_idx",
            "retention_expires_at",
            "id",
            postgresql_where=sql_text(
                "deleted_at IS NULL AND retention_expires_at IS NOT NULL AND storage_key IS NOT NULL"
            ),
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    publisher_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    publisher_client_stream_id_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    last_received_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("-1")
    )
    last_processed_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("-1")
    )
    last_captured_offset_ms: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    live_audio_lease_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'CAPTURING'"))
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    capture_started_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
    capture_ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    retention_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)


class RecordingUpload(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """A resumable logical upload with a server-confirmed byte offset."""

    __tablename__ = "recording_uploads"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'EXPIRED', 'FAILED')",
            name="recording_uploads_status_ck",
        ),
        CheckConstraint(
            "offset_bytes BETWEEN 0 AND total_bytes", name="recording_uploads_offset_ck"
        ),
        CheckConstraint("total_bytes > 0", name="recording_uploads_total_bytes_ck"),
        CheckConstraint(
            "length(btrim(declared_content_type)) > 0",
            name="recording_uploads_content_type_ck",
        ),
        CheckConstraint("declared_duration_ms >= 0", name="recording_uploads_duration_ck"),
        CheckConstraint("expires_at > created_at", name="recording_uploads_expiry_ck"),
        CheckConstraint(
            "(status = 'ACTIVE') = (terminal_at IS NULL)", name="recording_uploads_terminal_at_ck"
        ),
        CheckConstraint(
            "status <> 'COMPLETED' OR offset_bytes = total_bytes",
            name="recording_uploads_completed_offset_ck",
        ),
        CheckConstraint("version > 0", name="recording_uploads_version_ck"),
    )

    recording_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("session_recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    initiated_by_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    offset_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    declared_content_type: Mapped[str] = mapped_column(Text, nullable=False)
    declared_duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    temporary_storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    terminal_at: Mapped[datetime | None] = mapped_column(nullable=True)


class TranscriptVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A durable LIVE or recording-based transcript revision."""

    __tablename__ = "transcript_versions"
    __table_args__ = (
        UniqueConstraint("session_id", "version", name="transcript_versions_session_version_uq"),
        UniqueConstraint("id", "session_id", name="transcript_versions_id_session_uq"),
        CheckConstraint("version > 0", name="transcript_versions_version_ck"),
        CheckConstraint("source IN ('LIVE', 'RECORDING')", name="transcript_versions_source_ck"),
        CheckConstraint(
            "status IN ('FINALIZING', 'FINALIZED', 'FAILED', 'EMPTY')",
            name="transcript_versions_status_ck",
        ),
        CheckConstraint(
            "(created_by_job_id IS NULL) = (created_by_job_attempt IS NULL)",
            name="transcript_versions_created_job_pair_ck",
        ),
        CheckConstraint(
            "(source = 'LIVE' AND recording_id IS NULL AND created_by_job_id IS NULL) "
            "OR (source = 'RECORDING' AND recording_id IS NOT NULL AND created_by_job_id IS NOT NULL)",
            name="transcript_versions_source_target_ck",
        ),
        CheckConstraint(
            "(status = 'FINALIZING' AND finalized_at IS NULL AND failed_at IS NULL) "
            "OR (status IN ('FINALIZED', 'EMPTY') AND finalized_at IS NOT NULL AND failed_at IS NULL) "
            "OR (status = 'FAILED' AND finalized_at IS NULL AND failed_at IS NOT NULL)",
            name="transcript_versions_terminal_state_ck",
        ),
        CheckConstraint(
            "status NOT IN ('EMPTY', 'FAILED') OR last_sequence = 0",
            name="transcript_versions_empty_failed_sequence_ck",
        ),
        CheckConstraint("last_sequence >= 0", name="transcript_versions_last_sequence_ck"),
        ForeignKeyConstraint(
            ["recording_id", "session_id"],
            ["session_recordings.id", "session_recordings.session_id"],
            name="transcript_versions_recording_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["created_by_job_id", "session_id"],
            ["ai_jobs.id", "ai_jobs.session_id"],
            name="transcript_versions_created_job_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'FINALIZING'"))
    recording_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    created_by_job_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    created_by_job_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    finalized_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class TranscriptSegment(UUIDPrimaryKeyMixin, Base):
    """A final transcript sentence; partial STT results have no row."""

    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint(
            "transcript_version_id", "sequence", name="transcript_segments_version_sequence_uq"
        ),
        UniqueConstraint(
            "id",
            "transcript_version_id",
            "session_id",
            name="transcript_segments_id_version_session_uq",
        ),
        CheckConstraint("sequence > 0", name="transcript_segments_sequence_ck"),
        CheckConstraint("end_ms >= start_ms", name="transcript_segments_time_ck"),
        CheckConstraint("start_ms >= 0", name="transcript_segments_start_ck"),
        CheckConstraint(
            "utterance_id IS NULL OR length(btrim(utterance_id)) > 0",
            name="transcript_segments_utterance_ck",
        ),
        CheckConstraint(
            "(recording_start_ms IS NULL) = (recording_end_ms IS NULL)",
            name="transcript_segments_recording_pair_ck",
        ),
        CheckConstraint(
            "recording_end_ms IS NULL OR recording_end_ms >= recording_start_ms",
            name="transcript_segments_recording_time_ck",
        ),
        CheckConstraint("length(btrim(text)) > 0", name="transcript_segments_text_ck"),
        CheckConstraint(
            "(created_by_job_id IS NULL) = (created_by_job_attempt IS NULL)",
            name="transcript_segments_created_job_pair_ck",
        ),
        ForeignKeyConstraint(
            ["transcript_version_id", "session_id"],
            ["transcript_versions.id", "transcript_versions.session_id"],
            name="transcript_segments_version_session_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["created_by_job_id", "session_id"],
            ["ai_jobs.id", "ai_jobs.session_id"],
            name="transcript_segments_created_job_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    transcript_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    utterance_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recording_start_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recording_end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_job_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    created_by_job_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class TranscriptGap(UUIDPrimaryKeyMixin, Base):
    """A version-specific interval whose transcript could not be recovered."""

    __tablename__ = "transcript_gaps"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "transcript_version_id",
            "session_id",
            name="transcript_gaps_id_version_session_uq",
        ),
        CheckConstraint("start_ms >= 0", name="transcript_gaps_start_ck"),
        CheckConstraint("end_ms IS NULL OR end_ms >= start_ms", name="transcript_gaps_time_ck"),
        CheckConstraint("NOT is_final OR end_ms IS NOT NULL", name="transcript_gaps_final_end_ck"),
        CheckConstraint(
            "reason IN ('SERVER_STATE_LOST', 'SEQUENCE_GAP', 'CLIENT_DISCONNECTED', 'BACKPRESSURE_DROP')",
            name="transcript_gaps_reason_ck",
        ),
        ForeignKeyConstraint(
            ["transcript_version_id", "session_id"],
            ["transcript_versions.id", "transcript_versions.session_id"],
            name="transcript_gaps_version_session_fk",
            ondelete="CASCADE",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    transcript_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
