"""Knowledge, summary, chat, and evidence database models."""

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin

KNOWLEDGE_EMBEDDING_DIMENSION = 768


class KnowledgeChunk(UUIDPrimaryKeyMixin, Base):
    """A scoped RAG source with one typed source reference.

    All environments use one fixed 768-dimensional retrieval profile.  Changing
    that dimension requires a dedicated migration and complete reindex, rather
    than mixing vectors in this table.
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="knowledge_chunks_id_session_uq"),
        CheckConstraint("chunk_index >= 0", name="knowledge_chunks_chunk_index_ck"),
        CheckConstraint(
            "page_number IS NULL OR page_number > 0", name="knowledge_chunks_page_number_ck"
        ),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0", name="knowledge_chunks_token_count_ck"
        ),
        CheckConstraint("char_length(btrim(content)) > 0", name="knowledge_chunks_content_ck"),
        CheckConstraint("created_by_job_attempt > 0", name="knowledge_chunks_job_attempt_ck"),
        CheckConstraint(
            "(transcript_start_segment_id IS NULL) = (transcript_end_segment_id IS NULL)",
            name="knowledge_chunks_transcript_segment_pair_ck",
        ),
        CheckConstraint(
            "(source_transcript_version_id IS NULL) = (transcript_start_segment_id IS NULL)",
            name="knowledge_chunks_transcript_source_pair_ck",
        ),
        CheckConstraint(
            "num_nonnulls(material_id, source_transcript_version_id, question_id, "
            "representative_question_id, answer_id) = 1",
            name="knowledge_chunks_source_cardinality_ck",
        ),
        CheckConstraint(
            "page_number IS NULL OR material_id IS NOT NULL",
            name="knowledge_chunks_page_material_ck",
        ),
        Index(
            "knowledge_chunks_embedding_hnsw_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    source_transcript_version_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    transcript_start_segment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    transcript_end_segment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    question_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    representative_question_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    answer_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(KNOWLEDGE_EMBEDDING_DIMENSION), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_job_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    created_by_job_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class LectureSummary(UUIDPrimaryKeyMixin, Base):
    """A successful requester-only LIVE or shared FINAL summary."""

    __tablename__ = "lecture_summaries"
    __table_args__ = (
        UniqueConstraint("created_by_job_id", name="lecture_summaries_job_uq"),
        CheckConstraint("created_by_job_attempt > 0", name="lecture_summaries_job_attempt_ck"),
        CheckConstraint("summary_type IN ('LIVE', 'FINAL')", name="lecture_summaries_type_ck"),
        CheckConstraint(
            "visibility IN ('REQUESTER_ONLY', 'COURSE_MEMBERS')",
            name="lecture_summaries_visibility_ck",
        ),
        CheckConstraint("char_length(btrim(content)) > 0", name="lecture_summaries_content_ck"),
        CheckConstraint(
            "(summary_type = 'LIVE' AND visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL) "
            "OR (summary_type = 'FINAL' AND visibility = 'COURSE_MEMBERS' AND requester_user_id IS NULL)",
            name="lecture_summaries_type_visibility_ck",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    requester_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_by_job_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    created_by_job_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_type: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
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
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class ChatSession(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """A private AI conversation scoped to one course session."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint("id", "session_id", name="chat_sessions_id_session_uq"),
        CheckConstraint("mode IN ('LIVE', 'REVIEW')", name="chat_sessions_mode_ck"),
        CheckConstraint("version > 0", name="chat_sessions_version_ck"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False)


class ChatMessage(UUIDPrimaryKeyMixin, Base):
    """An ordered user or completed assistant message in a private chat."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("chat_id", "sequence", name="chat_messages_sequence_uq"),
        UniqueConstraint("id", "session_id", name="chat_messages_id_session_uq"),
        UniqueConstraint("id", "chat_id", "session_id", name="chat_messages_id_chat_session_uq"),
        CheckConstraint("sequence > 0", name="chat_messages_sequence_ck"),
        CheckConstraint("role IN ('USER', 'ASSISTANT')", name="chat_messages_role_ck"),
        CheckConstraint(
            "(role = 'USER' AND content = btrim(content) AND content IS NFC NORMALIZED "
            "AND char_length(content) BETWEEN 1 AND 2000) OR "
            "(role = 'ASSISTANT' AND char_length(btrim(content)) > 0)",
            name="chat_messages_content_ck",
        ),
        CheckConstraint(
            "created_by_job_attempt IS NULL OR created_by_job_attempt > 0",
            name="chat_messages_job_attempt_ck",
        ),
        CheckConstraint(
            "(role = 'USER' AND created_by_job_id IS NULL AND created_by_job_attempt IS NULL "
            "AND model_name IS NULL AND prompt_version IS NULL) "
            "OR (role = 'ASSISTANT' AND created_by_job_id IS NOT NULL AND created_by_job_attempt IS NOT NULL)",
            name="chat_messages_provenance_ck",
        ),
    )

    chat_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_job_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    created_by_job_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class ChatMessageEvidence(Base):
    """A ranked, safe-label snapshot of a chunk used in an assistant response."""

    __tablename__ = "chat_message_evidence"
    __table_args__ = (
        UniqueConstraint(
            "chat_message_id", "knowledge_chunk_id", name="chat_message_evidence_message_chunk_uq"
        ),
        CheckConstraint("rank > 0", name="chat_message_evidence_rank_ck"),
        CheckConstraint(
            "char_length(btrim(label_snapshot)) > 0", name="chat_message_evidence_label_ck"
        ),
    )

    chat_message_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    knowledge_chunk_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)
    relevance_score: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    label_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
