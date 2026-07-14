"""Create knowledge, summary, chat, and evidence tables.

Revision ID: 20260714_0008
Revises: 20260714_0007
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0008"
down_revision: str | None = "20260714_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def _install_updated_at_trigger(table_name: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table_name}_set_updated_at "
        f"BEFORE UPDATE ON {table_name} "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def upgrade() -> None:
    """Create relational AI result storage without an unresolved vector dimension."""

    op.create_table(
        "knowledge_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_transcript_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transcript_start_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transcript_end_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("representative_question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_job_attempt", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("chunk_index >= 0", name="knowledge_chunks_chunk_index_ck"),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0", name="knowledge_chunks_page_number_ck"
        ),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0", name="knowledge_chunks_token_count_ck"
        ),
        sa.CheckConstraint("char_length(btrim(content)) > 0", name="knowledge_chunks_content_ck"),
        sa.CheckConstraint("created_by_job_attempt > 0", name="knowledge_chunks_job_attempt_ck"),
        sa.CheckConstraint(
            "(transcript_start_segment_id IS NULL) = (transcript_end_segment_id IS NULL)",
            name="knowledge_chunks_transcript_segment_pair_ck",
        ),
        sa.CheckConstraint(
            "(source_transcript_version_id IS NULL) = (transcript_start_segment_id IS NULL)",
            name="knowledge_chunks_transcript_source_pair_ck",
        ),
        sa.CheckConstraint(
            "num_nonnulls(material_id, source_transcript_version_id, question_id, "
            "representative_question_id, answer_id) = 1",
            name="knowledge_chunks_source_cardinality_ck",
        ),
        sa.CheckConstraint(
            "page_number IS NULL OR material_id IS NOT NULL",
            name="knowledge_chunks_page_material_ck",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "session_id", name="knowledge_chunks_id_session_uq"),
    )

    op.create_table(
        "lecture_summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_job_attempt", sa.Integer(), nullable=False),
        sa.Column("summary_type", sa.Text(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_transcript_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_start_segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_end_segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("created_by_job_attempt > 0", name="lecture_summaries_job_attempt_ck"),
        sa.CheckConstraint("summary_type IN ('LIVE', 'FINAL')", name="lecture_summaries_type_ck"),
        sa.CheckConstraint(
            "visibility IN ('REQUESTER_ONLY', 'COURSE_MEMBERS')",
            name="lecture_summaries_visibility_ck",
        ),
        sa.CheckConstraint("char_length(btrim(content)) > 0", name="lecture_summaries_content_ck"),
        sa.CheckConstraint(
            "(summary_type = 'LIVE' AND visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL) "
            "OR (summary_type = 'FINAL' AND visibility = 'COURSE_MEMBERS' AND requester_user_id IS NULL)",
            name="lecture_summaries_type_visibility_ck",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("created_by_job_id", name="lecture_summaries_job_uq"),
    )

    op.create_table(
        "chat_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.CheckConstraint("mode IN ('LIVE', 'REVIEW')", name="chat_sessions_mode_ck"),
        sa.CheckConstraint("version > 0", name="chat_sessions_version_ck"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "session_id", name="chat_sessions_id_session_uq"),
    )
    _install_updated_at_trigger("chat_sessions")

    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_job_attempt", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("sequence > 0", name="chat_messages_sequence_ck"),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name="chat_messages_role_ck"),
        sa.CheckConstraint(
            "(role = 'USER' AND content = btrim(content) AND content IS NFC NORMALIZED "
            "AND char_length(content) BETWEEN 1 AND 2000) OR "
            "(role = 'ASSISTANT' AND char_length(btrim(content)) > 0)",
            name="chat_messages_content_ck",
        ),
        sa.CheckConstraint(
            "created_by_job_attempt IS NULL OR created_by_job_attempt > 0",
            name="chat_messages_job_attempt_ck",
        ),
        sa.CheckConstraint(
            "(role = 'USER' AND created_by_job_id IS NULL AND created_by_job_attempt IS NULL "
            "AND model_name IS NULL AND prompt_version IS NULL) "
            "OR (role = 'ASSISTANT' AND created_by_job_id IS NOT NULL AND created_by_job_attempt IS NOT NULL)",
            name="chat_messages_provenance_ck",
        ),
        sa.UniqueConstraint("chat_id", "sequence", name="chat_messages_sequence_uq"),
        sa.UniqueConstraint("id", "session_id", name="chat_messages_id_session_uq"),
        sa.UniqueConstraint("id", "chat_id", "session_id", name="chat_messages_id_chat_session_uq"),
    )

    op.create_table(
        "chat_message_evidence",
        sa.Column("chat_message_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), primary_key=True),
        sa.Column("relevance_score", sa.Double(), nullable=True),
        sa.Column("label_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("rank > 0", name="chat_message_evidence_rank_ck"),
        sa.CheckConstraint(
            "char_length(btrim(label_snapshot)) > 0", name="chat_message_evidence_label_ck"
        ),
        sa.UniqueConstraint(
            "chat_message_id", "knowledge_chunk_id", name="chat_message_evidence_message_chunk_uq"
        ),
    )


def downgrade() -> None:
    """Drop AI result tables before their source tables."""

    op.drop_table("chat_message_evidence")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("lecture_summaries")
    op.drop_table("knowledge_chunks")
