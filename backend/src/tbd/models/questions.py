"""Question, clustering state, reaction, and AI job database models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class QuestionClusteringState(TimestampMixin, Base):
    """The per-session ordering and late-result fence for clustering."""

    __tablename__ = "question_clustering_states"
    __table_args__ = (
        CheckConstraint(
            "requested_sequence >= 0", name="question_clustering_states_requested_sequence_ck"
        ),
        CheckConstraint(
            "applied_sequence >= 0", name="question_clustering_states_applied_sequence_ck"
        ),
        CheckConstraint(
            "applied_sequence <= requested_sequence",
            name="question_clustering_states_sequence_order_ck",
        ),
        CheckConstraint("current_revision >= 0", name="question_clustering_states_revision_ck"),
        CheckConstraint(
            "current_generation IS NULL OR current_generation > 0",
            name="question_clustering_states_current_generation_ck",
        ),
        CheckConstraint(
            "final_generation IS NULL OR final_generation > 0",
            name="question_clustering_states_final_generation_ck",
        ),
        CheckConstraint(
            "final_generation IS NULL OR final_generation = current_generation",
            name="question_clustering_states_final_current_ck",
        ),
        CheckConstraint(
            "(last_job_id IS NULL) = (last_job_attempt IS NULL)",
            name="question_clustering_states_last_job_pair_ck",
        ),
        CheckConstraint(
            "(last_job_id IS NULL) = (last_job_status IS NULL)",
            name="question_clustering_states_last_job_status_pair_ck",
        ),
        CheckConstraint(
            "last_job_status IS NULL OR last_job_status IN "
            "('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'SUPERSEDED')",
            name="question_clustering_states_last_job_status_ck",
        ),
        ForeignKeyConstraint(
            ["last_job_id", "session_id"],
            ["ai_jobs.id", "ai_jobs.session_id"],
            name="clustering_state_last_job_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["retry_job_id", "session_id"],
            ["ai_jobs.id", "ai_jobs.session_id"],
            name="clustering_state_retry_job_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    requested_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    applied_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    current_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    current_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    final_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_job_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    last_job_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_job_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_job_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True, unique=True
    )


class Question(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """A student-authored question with its clustering input sequence."""

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="questions_id_session_uq"),
        UniqueConstraint(
            "session_id", "clustering_sequence", name="questions_session_clustering_sequence_uq"
        ),
        CheckConstraint("clustering_sequence > 0", name="questions_clustering_sequence_ck"),
        CheckConstraint(
            "content = btrim(content) AND content IS NFC NORMALIZED AND char_length(content) BETWEEN 1 AND 300",
            name="questions_content_normalized_ck",
        ),
        CheckConstraint("status IN ('OPEN', 'SELECTED', 'ANSWERED')", name="questions_status_ck"),
        CheckConstraint("reaction_count >= 0", name="questions_reaction_count_ck"),
        CheckConstraint("version > 0", name="questions_version_ck"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    clustering_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'OPEN'"))
    reaction_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class QuestionReaction(Base):
    """A user's single reaction to one question."""

    __tablename__ = "question_reactions"

    question_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class AIJob(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """A durable asynchronous work row retried by incrementing ``attempt``."""

    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="ai_jobs_id_session_uq"),
        CheckConstraint(
            "job_type IN ('MATERIAL_PROCESSING', 'QUESTION_CLUSTERING', 'LIVE_SUMMARY', "
            "'FINAL_SUMMARY', 'CHAT_RESPONSE', 'SESSION_POSTPROCESSING', "
            "'RECORDING_TRANSCRIPTION', 'ANSWER_ORGANIZATION', 'KNOWLEDGE_INDEXING')",
            name="ai_jobs_type_ck",
        ),
        CheckConstraint("visibility IN ('SHARED', 'REQUESTER_ONLY')", name="ai_jobs_visibility_ck"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'SUPERSEDED')",
            name="ai_jobs_status_ck",
        ),
        CheckConstraint("attempt > 0", name="ai_jobs_attempt_ck"),
        CheckConstraint("version > 0", name="ai_jobs_version_ck"),
        CheckConstraint(
            "num_nonnulls(target_material_id, target_recording_id, target_chat_id, target_answer_id) <= 1",
            name="ai_jobs_target_cardinality_ck",
        ),
        CheckConstraint(
            "target_material_id IS NULL OR job_type = 'MATERIAL_PROCESSING'",
            name="ai_jobs_material_target_ck",
        ),
        CheckConstraint(
            "target_recording_id IS NULL OR job_type = 'RECORDING_TRANSCRIPTION'",
            name="ai_jobs_recording_target_ck",
        ),
        CheckConstraint(
            "(job_type = 'CHAT_RESPONSE' AND target_chat_id IS NOT NULL AND target_user_message_id IS NOT NULL) "
            "OR (job_type <> 'CHAT_RESPONSE' AND target_chat_id IS NULL AND target_user_message_id IS NULL)",
            name="ai_jobs_chat_target_ck",
        ),
        CheckConstraint(
            "target_answer_id IS NULL OR job_type = 'ANSWER_ORGANIZATION'",
            name="ai_jobs_answer_target_ck",
        ),
        CheckConstraint(
            "job_type <> 'MATERIAL_PROCESSING' OR target_material_id IS NOT NULL",
            name="ai_jobs_material_type_target_ck",
        ),
        CheckConstraint(
            "job_type <> 'RECORDING_TRANSCRIPTION' OR target_recording_id IS NOT NULL",
            name="ai_jobs_recording_type_target_ck",
        ),
        CheckConstraint(
            "job_type <> 'ANSWER_ORGANIZATION' OR target_answer_id IS NOT NULL",
            name="ai_jobs_answer_type_target_ck",
        ),
        CheckConstraint(
            "(job_type IN ('ANSWER_ORGANIZATION', 'LIVE_SUMMARY') "
            "AND input_transcript_version_id IS NOT NULL AND input_start_segment_id IS NOT NULL "
            "AND input_end_segment_id IS NOT NULL) OR (job_type = 'FINAL_SUMMARY' "
            "AND input_start_segment_id IS NULL AND input_end_segment_id IS NULL) "
            "OR (job_type NOT IN "
            "('ANSWER_ORGANIZATION', 'LIVE_SUMMARY', 'FINAL_SUMMARY') "
            "AND input_transcript_version_id IS NULL "
            "AND input_start_segment_id IS NULL AND input_end_segment_id IS NULL)",
            name="ai_jobs_answer_input_ck",
        ),
        CheckConstraint(
            "(input_start_segment_id IS NULL) = (input_end_segment_id IS NULL)",
            name="ai_jobs_input_segment_pair_ck",
        ),
        CheckConstraint(
            "input_start_segment_id IS NULL OR input_transcript_version_id IS NOT NULL",
            name="ai_jobs_input_version_segment_ck",
        ),
        CheckConstraint(
            "(job_type = 'QUESTION_CLUSTERING' AND clustering_mode IS NOT NULL "
            "AND input_through_sequence IS NOT NULL AND base_revision IS NOT NULL) "
            "OR (job_type <> 'QUESTION_CLUSTERING' AND clustering_mode IS NULL "
            "AND input_through_sequence IS NULL AND base_revision IS NULL)",
            name="ai_jobs_clustering_input_ck",
        ),
        CheckConstraint(
            "job_type <> 'QUESTION_CLUSTERING' OR requester_user_id IS NULL",
            name="ai_jobs_clustering_requester_ck",
        ),
        CheckConstraint(
            "clustering_mode IS NULL OR clustering_mode IN ('LIVE_INCREMENTAL', 'FINAL')",
            name="ai_jobs_clustering_mode_ck",
        ),
        CheckConstraint(
            "(clustering_mode = 'FINAL' AND final_answered_through_at IS NOT NULL) "
            "OR (clustering_mode IS DISTINCT FROM 'FINAL' AND final_answered_through_at IS NULL)",
            name="ai_jobs_final_answered_through_ck",
        ),
        CheckConstraint(
            "clustering_mode <> 'LIVE_INCREMENTAL' OR (visibility = 'SHARED' AND NOT blocks_session_completion)",
            name="ai_jobs_live_clustering_visibility_ck",
        ),
        CheckConstraint(
            "clustering_mode <> 'FINAL' OR (visibility = 'SHARED' AND blocks_session_completion)",
            name="ai_jobs_final_clustering_visibility_ck",
        ),
        CheckConstraint(
            "(visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL) OR visibility = 'SHARED'",
            name="ai_jobs_visibility_requester_ck",
        ),
        CheckConstraint(
            "NOT blocks_session_completion OR visibility = 'SHARED'",
            name="ai_jobs_blocking_visibility_ck",
        ),
        CheckConstraint(
            "job_type NOT IN ('LIVE_SUMMARY', 'CHAT_RESPONSE') OR "
            "(visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL AND NOT blocks_session_completion)",
            name="ai_jobs_personal_visibility_ck",
        ),
        CheckConstraint(
            "job_type <> 'FINAL_SUMMARY' OR "
            "(visibility = 'SHARED' AND requester_user_id IS NULL AND blocks_session_completion)",
            name="ai_jobs_final_summary_visibility_ck",
        ),
        CheckConstraint(
            "job_type NOT IN ('SESSION_POSTPROCESSING', 'RECORDING_TRANSCRIPTION', 'ANSWER_ORGANIZATION') "
            "OR (visibility = 'SHARED' AND requester_user_id IS NULL AND blocks_session_completion)",
            name="ai_jobs_processing_visibility_ck",
        ),
        CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
            name="ai_jobs_progress_percent_ck",
        ),
        CheckConstraint(
            "(run_token IS NOT NULL) = (status = 'RUNNING')", name="ai_jobs_run_token_ck"
        ),
        CheckConstraint(
            "(lease_expires_at IS NOT NULL) = (status = 'RUNNING')", name="ai_jobs_lease_ck"
        ),
        CheckConstraint(
            "(status = 'PENDING' AND started_at IS NULL AND finished_at IS NULL AND error_code IS NULL AND error_message IS NULL) "
            "OR (status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL AND error_code IS NULL AND error_message IS NULL) "
            "OR (status = 'SUCCEEDED' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND error_code IS NULL AND error_message IS NULL) "
            "OR (status IN ('FAILED', 'CANCELLED', 'SUPERSEDED') "
            "AND finished_at IS NOT NULL AND error_code IS NOT NULL)",
            name="ai_jobs_terminal_state_ck",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ai_jobs_finished_after_started_ck",
        ),
        CheckConstraint(
            "dedupe_key_hash IS NULL OR octet_length(dedupe_key_hash) = 32",
            name="ai_jobs_dedupe_hash_length_ck",
        ),
        CheckConstraint(
            "input_through_sequence IS NULL OR input_through_sequence >= 0",
            name="ai_jobs_input_sequence_ck",
        ),
        CheckConstraint(
            "base_revision IS NULL OR base_revision >= 0", name="ai_jobs_base_revision_ck"
        ),
        ForeignKeyConstraint(
            ["target_material_id", "session_id"],
            ["lecture_materials.id", "lecture_materials.session_id"],
            name="ai_jobs_material_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["target_recording_id", "session_id"],
            ["session_recordings.id", "session_recordings.session_id"],
            name="ai_jobs_recording_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["target_chat_id", "session_id"],
            ["chat_sessions.id", "chat_sessions.session_id"],
            name="ai_jobs_chat_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["target_user_message_id", "target_chat_id", "session_id"],
            ["chat_messages.id", "chat_messages.chat_id", "chat_messages.session_id"],
            name="ai_jobs_message_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["target_answer_id", "session_id"],
            ["answers.id", "answers.session_id"],
            name="ai_jobs_answer_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["input_transcript_version_id", "session_id"],
            ["transcript_versions.id", "transcript_versions.session_id"],
            name="ai_jobs_input_version_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["input_start_segment_id", "input_transcript_version_id", "session_id"],
            [
                "transcript_segments.id",
                "transcript_segments.transcript_version_id",
                "transcript_segments.session_id",
            ],
            name="ai_jobs_input_start_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["input_end_segment_id", "input_transcript_version_id", "session_id"],
            [
                "transcript_segments.id",
                "transcript_segments.transcript_version_id",
                "transcript_segments.session_id",
            ],
            name="ai_jobs_input_end_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    requester_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    target_material_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    target_recording_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    target_chat_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    target_user_message_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    target_answer_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    input_transcript_version_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    input_start_segment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    input_end_segment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    clustering_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_through_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    base_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    final_answered_through_at: Mapped[datetime | None] = mapped_column(nullable=True)
    dedupe_key_hash: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    available_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    blocks_session_completion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    run_token: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    progress_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
