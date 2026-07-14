"""Representative-question, cluster, and answer database models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class AIRepresentativeQuestion(UUIDPrimaryKeyMixin, VersionMixin, Base):
    """An immutable AI-created central question or preserved cluster child."""

    __tablename__ = "ai_representative_questions"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="ai_representative_questions_id_session_uq"),
        CheckConstraint(
            "char_length(btrim(text)) BETWEEN 1 AND 300", name="ai_representative_questions_text_ck"
        ),
        CheckConstraint(
            "status IN ('OPEN', 'SELECTED', 'ANSWERED')",
            name="ai_representative_questions_status_ck",
        ),
        CheckConstraint(
            "lifecycle_status IN ('ACTIVE', 'PRESERVED', 'DISCARDED')",
            name="ai_representative_questions_lifecycle_ck",
        ),
        CheckConstraint("version > 0", name="ai_representative_questions_version_ck"),
        CheckConstraint(
            "created_by_job_attempt > 0", name="ai_representative_questions_job_attempt_ck"
        ),
        CheckConstraint(
            "created_in_generation > 0", name="ai_representative_questions_generation_ck"
        ),
        CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND preserved_at IS NULL AND discarded_at IS NULL) "
            "OR (lifecycle_status = 'PRESERVED' AND preserved_at IS NOT NULL AND discarded_at IS NULL) "
            "OR (lifecycle_status = 'DISCARDED' AND discarded_at IS NOT NULL AND status = 'OPEN')",
            name="ai_representative_questions_lifecycle_timestamps_ck",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("'OPEN'"))
    lifecycle_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sql_text("'ACTIVE'")
    )
    created_by_job_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    created_by_job_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    created_in_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    preserved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    discarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class QuestionCluster(UUIDPrimaryKeyMixin, Base):
    """One physical cluster row in an incremental or final generation."""

    __tablename__ = "question_clusters"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="question_clusters_id_session_uq"),
        UniqueConstraint(
            "session_id",
            "generation",
            "logical_cluster_id",
            name="question_clusters_logical_generation_uq",
        ),
        UniqueConstraint(
            "session_id", "generation", "ordinal", name="question_clusters_ordinal_generation_uq"
        ),
        UniqueConstraint(
            "session_id",
            "generation",
            "representative_question_id",
            name="question_clusters_representative_generation_uq",
        ),
        UniqueConstraint(
            "created_by_job_id",
            "created_by_job_attempt",
            "ordinal",
            name="question_clusters_job_ordinal_uq",
        ),
        CheckConstraint("generation > 0", name="question_clusters_generation_ck"),
        CheckConstraint("ordinal >= 0", name="question_clusters_ordinal_ck"),
        CheckConstraint("created_by_job_attempt > 0", name="question_clusters_job_attempt_ck"),
        CheckConstraint(
            "(is_final AND finalized_at IS NOT NULL) OR (NOT is_final AND finalized_at IS NULL)",
            name="question_clusters_finalized_ck",
        ),
    )

    logical_cluster_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    representative_question_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    is_final: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    finalized_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by_job_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    created_by_job_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class QuestionClusterMember(Base):
    """A single student question or preserved representative-question child."""

    __tablename__ = "question_cluster_members"
    __table_args__ = (
        CheckConstraint("generation > 0", name="question_cluster_members_generation_ck"),
        CheckConstraint("position >= 0", name="question_cluster_members_position_ck"),
        CheckConstraint(
            "num_nonnulls(question_id, representative_question_id) = 1",
            name="question_cluster_members_child_cardinality_ck",
        ),
    )

    cluster_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    representative_question_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class Answer(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """A professor answer targeting exactly one student or representative question."""

    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="answers_id_session_uq"),
        CheckConstraint(
            "num_nonnulls(target_question_id, target_representative_question_id) = 1",
            name="answers_target_cardinality_ck",
        ),
        CheckConstraint("status IN ('CAPTURING', 'COMPLETED')", name="answers_status_ck"),
        CheckConstraint(
            "char_length(btrim(target_text_snapshot)) BETWEEN 1 AND 300",
            name="answers_target_snapshot_ck",
        ),
        CheckConstraint(
            "text_content IS NULL OR char_length(btrim(text_content)) > 0",
            name="answers_text_content_ck",
        ),
        CheckConstraint("version > 0", name="answers_version_ck"),
        CheckConstraint(
            "(start_segment_id IS NULL) = (end_segment_id IS NULL)", name="answers_segment_pair_ck"
        ),
        CheckConstraint(
            "(source_transcript_version_id IS NULL) = (capture_started_after_sequence IS NULL)",
            name="answers_transcript_capture_pair_ck",
        ),
        CheckConstraint(
            "capture_started_after_sequence IS NULL OR capture_started_after_sequence >= 0",
            name="answers_capture_sequence_ck",
        ),
        CheckConstraint(
            "(status = 'CAPTURING' AND source_transcript_version_id IS NOT NULL "
            "AND capture_started_after_sequence IS NOT NULL AND start_segment_id IS NULL "
            "AND text_content IS NULL AND completed_at IS NULL) "
            "OR (status = 'COMPLETED' AND completed_at IS NOT NULL AND "
            "((source_transcript_version_id IS NOT NULL AND capture_started_after_sequence IS NOT NULL "
            "AND start_segment_id IS NOT NULL) OR (source_transcript_version_id IS NULL "
            "AND capture_started_after_sequence IS NULL AND start_segment_id IS NULL "
            "AND text_content IS NOT NULL)))",
            name="answers_state_shape_ck",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="answers_completed_after_started_ck",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    professor_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_question_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    target_representative_question_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    target_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sql_text("'CAPTURING'")
    )
    source_transcript_version_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    capture_started_after_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    start_segment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    end_segment_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AnswerTranscriptMapping(TimestampMixin, Base):
    """A non-destructive mapping from an Answer's live range to an HQ revision."""

    __tablename__ = "answer_transcript_mappings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'SUCCEEDED', 'FAILED')",
            name="answer_transcript_mappings_status_ck",
        ),
        CheckConstraint(
            "(mapped_start_segment_id IS NULL) = (mapped_end_segment_id IS NULL)",
            name="answer_transcript_mappings_segment_pair_ck",
        ),
        CheckConstraint(
            "(processed_by_job_id IS NULL) = (processed_by_job_attempt IS NULL)",
            name="answer_transcript_mappings_job_pair_ck",
        ),
        CheckConstraint(
            "processed_by_job_attempt IS NULL OR processed_by_job_attempt > 0",
            name="answer_transcript_mappings_job_attempt_ck",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND mapped_start_segment_id IS NULL AND processed_by_job_id IS NULL "
            "AND mapped_at IS NULL AND failed_at IS NULL) "
            "OR (status = 'SUCCEEDED' AND mapped_start_segment_id IS NOT NULL "
            "AND processed_by_job_id IS NOT NULL AND mapped_at IS NOT NULL AND failed_at IS NULL) "
            "OR (status = 'FAILED' AND mapped_start_segment_id IS NULL "
            "AND processed_by_job_id IS NOT NULL AND mapped_at IS NULL AND failed_at IS NOT NULL)",
            name="answer_transcript_mappings_state_shape_ck",
        ),
    )

    answer_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    target_transcript_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True
    )
    session_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("'PENDING'"))
    mapped_start_segment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    mapped_end_segment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    processed_by_job_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    processed_by_job_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mapped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AnswerOrganization(UUIDPrimaryKeyMixin, Base):
    """An immutable AI organization of a completed voice-backed Answer."""

    __tablename__ = "answer_organizations"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="answer_organizations_id_session_uq"),
        UniqueConstraint("answer_id", name="answer_organizations_answer_uq"),
        UniqueConstraint("created_by_job_id", name="answer_organizations_job_uq"),
        CheckConstraint("char_length(btrim(content)) > 0", name="answer_organizations_content_ck"),
        CheckConstraint("created_by_job_attempt > 0", name="answer_organizations_job_attempt_ck"),
    )

    answer_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_transcript_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    source_start_segment_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    source_end_segment_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    created_by_job_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    created_by_job_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
