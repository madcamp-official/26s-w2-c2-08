"""Create representative-question, cluster, and answer tables.

Revision ID: 20260714_0007
Revises: 20260714_0006
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0007"
down_revision: str | None = "20260714_0006"
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
    """Create tables before final deferred cross-table constraints."""

    op.create_table(
        "ai_representative_questions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column(
            "lifecycle_status", sa.Text(), nullable=False, server_default=sa.text("'ACTIVE'")
        ),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_job_attempt", sa.Integer(), nullable=False),
        sa.Column("created_in_generation", sa.BigInteger(), nullable=False),
        sa.Column("preserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(text)) BETWEEN 1 AND 300", name="ai_representative_questions_text_ck"
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'SELECTED', 'ANSWERED')",
            name="ai_representative_questions_status_ck",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('ACTIVE', 'PRESERVED', 'DISCARDED')",
            name="ai_representative_questions_lifecycle_ck",
        ),
        sa.CheckConstraint("version > 0", name="ai_representative_questions_version_ck"),
        sa.CheckConstraint(
            "created_by_job_attempt > 0", name="ai_representative_questions_job_attempt_ck"
        ),
        sa.CheckConstraint(
            "created_in_generation > 0", name="ai_representative_questions_generation_ck"
        ),
        sa.CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND preserved_at IS NULL AND discarded_at IS NULL) "
            "OR (lifecycle_status = 'PRESERVED' AND preserved_at IS NOT NULL AND discarded_at IS NULL) "
            "OR (lifecycle_status = 'DISCARDED' AND discarded_at IS NOT NULL AND status = 'OPEN')",
            name="ai_representative_questions_lifecycle_timestamps_ck",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "session_id", name="ai_representative_questions_id_session_uq"),
    )

    op.create_table(
        "question_clusters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("logical_cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("representative_question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_job_attempt", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("generation > 0", name="question_clusters_generation_ck"),
        sa.CheckConstraint("ordinal >= 0", name="question_clusters_ordinal_ck"),
        sa.CheckConstraint("created_by_job_attempt > 0", name="question_clusters_job_attempt_ck"),
        sa.CheckConstraint(
            "(is_final AND finalized_at IS NOT NULL) OR (NOT is_final AND finalized_at IS NULL)",
            name="question_clusters_finalized_ck",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "session_id", name="question_clusters_id_session_uq"),
        sa.UniqueConstraint(
            "session_id",
            "generation",
            "logical_cluster_id",
            name="question_clusters_logical_generation_uq",
        ),
        sa.UniqueConstraint(
            "session_id", "generation", "ordinal", name="question_clusters_ordinal_generation_uq"
        ),
        sa.UniqueConstraint(
            "session_id",
            "generation",
            "representative_question_id",
            name="question_clusters_representative_generation_uq",
        ),
        sa.UniqueConstraint(
            "created_by_job_id",
            "created_by_job_attempt",
            "ordinal",
            name="question_clusters_job_ordinal_uq",
        ),
    )

    op.create_table(
        "question_cluster_members",
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("representative_question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("generation > 0", name="question_cluster_members_generation_ck"),
        sa.CheckConstraint("position >= 0", name="question_cluster_members_position_ck"),
        sa.CheckConstraint(
            "num_nonnulls(question_id, representative_question_id) = 1",
            name="question_cluster_members_child_cardinality_ck",
        ),
    )

    op.create_table(
        "answers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "target_representative_question_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("target_text_snapshot", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'CAPTURING'")),
        sa.Column("source_transcript_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capture_started_after_sequence", sa.BigInteger(), nullable=True),
        sa.Column("start_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("end_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "num_nonnulls(target_question_id, target_representative_question_id) = 1",
            name="answers_target_cardinality_ck",
        ),
        sa.CheckConstraint("status IN ('CAPTURING', 'COMPLETED')", name="answers_status_ck"),
        sa.CheckConstraint(
            "char_length(btrim(target_text_snapshot)) BETWEEN 1 AND 300",
            name="answers_target_snapshot_ck",
        ),
        sa.CheckConstraint(
            "text_content IS NULL OR char_length(btrim(text_content)) > 0",
            name="answers_text_content_ck",
        ),
        sa.CheckConstraint("version > 0", name="answers_version_ck"),
        sa.CheckConstraint(
            "(start_segment_id IS NULL) = (end_segment_id IS NULL)", name="answers_segment_pair_ck"
        ),
        sa.CheckConstraint(
            "(source_transcript_version_id IS NULL) = (capture_started_after_sequence IS NULL)",
            name="answers_transcript_capture_pair_ck",
        ),
        sa.CheckConstraint(
            "capture_started_after_sequence IS NULL OR capture_started_after_sequence >= 0",
            name="answers_capture_sequence_ck",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="answers_completed_after_started_ck",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["professor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("id", "session_id", name="answers_id_session_uq"),
    )
    _install_updated_at_trigger("answers")

    op.create_table(
        "answer_transcript_mappings",
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_transcript_version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("mapped_start_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mapped_end_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("processed_by_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("processed_by_job_attempt", sa.Integer(), nullable=True),
        sa.Column("mapped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SUCCEEDED', 'FAILED')",
            name="answer_transcript_mappings_status_ck",
        ),
        sa.CheckConstraint(
            "(mapped_start_segment_id IS NULL) = (mapped_end_segment_id IS NULL)",
            name="answer_transcript_mappings_segment_pair_ck",
        ),
        sa.CheckConstraint(
            "(processed_by_job_id IS NULL) = (processed_by_job_attempt IS NULL)",
            name="answer_transcript_mappings_job_pair_ck",
        ),
        sa.CheckConstraint(
            "processed_by_job_attempt IS NULL OR processed_by_job_attempt > 0",
            name="answer_transcript_mappings_job_attempt_ck",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND mapped_start_segment_id IS NULL AND processed_by_job_id IS NULL "
            "AND mapped_at IS NULL AND failed_at IS NULL) "
            "OR (status = 'SUCCEEDED' AND mapped_start_segment_id IS NOT NULL "
            "AND processed_by_job_id IS NOT NULL AND mapped_at IS NOT NULL AND failed_at IS NULL) "
            "OR (status = 'FAILED' AND mapped_start_segment_id IS NULL "
            "AND processed_by_job_id IS NOT NULL AND mapped_at IS NULL AND failed_at IS NOT NULL)",
            name="answer_transcript_mappings_state_shape_ck",
        ),
    )
    _install_updated_at_trigger("answer_transcript_mappings")

    op.create_table(
        "answer_organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_transcript_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_start_segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_end_segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_job_attempt", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(content)) > 0", name="answer_organizations_content_ck"
        ),
        sa.CheckConstraint(
            "created_by_job_attempt > 0", name="answer_organizations_job_attempt_ck"
        ),
        sa.UniqueConstraint("id", "session_id", name="answer_organizations_id_session_uq"),
        sa.UniqueConstraint("answer_id", name="answer_organizations_answer_uq"),
        sa.UniqueConstraint("created_by_job_id", name="answer_organizations_job_uq"),
    )


def downgrade() -> None:
    """Drop answer and cluster tables before question and transcript parents."""

    op.drop_table("answer_organizations")
    op.drop_table("answer_transcript_mappings")
    op.drop_table("answers")
    op.drop_table("question_cluster_members")
    op.drop_table("question_clusters")
    op.drop_table("ai_representative_questions")
