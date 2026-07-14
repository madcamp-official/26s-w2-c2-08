"""Create question, reaction, clustering state, and AI job tables.

Revision ID: 20260714_0006
Revises: 20260714_0005
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0006"
down_revision: str | None = "20260714_0005"
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
    """Create input ordering and asynchronous job state before cyclic results."""

    op.create_table(
        "question_clustering_states",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("requested_sequence", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("applied_sequence", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_generation", sa.BigInteger(), nullable=True),
        sa.Column("final_generation", sa.BigInteger(), nullable=True),
        sa.Column("last_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_job_attempt", sa.Integer(), nullable=True),
        sa.Column("last_job_status", sa.Text(), nullable=True),
        sa.Column("retry_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("requested_sequence >= 0", name="question_clustering_states_requested_sequence_ck"),
        sa.CheckConstraint("applied_sequence >= 0", name="question_clustering_states_applied_sequence_ck"),
        sa.CheckConstraint("applied_sequence <= requested_sequence", name="question_clustering_states_sequence_order_ck"),
        sa.CheckConstraint("current_revision >= 0", name="question_clustering_states_revision_ck"),
        sa.CheckConstraint("current_generation IS NULL OR current_generation > 0", name="question_clustering_states_current_generation_ck"),
        sa.CheckConstraint("final_generation IS NULL OR final_generation > 0", name="question_clustering_states_final_generation_ck"),
        sa.CheckConstraint("final_generation IS NULL OR final_generation = current_generation", name="question_clustering_states_final_current_ck"),
        sa.CheckConstraint("(last_job_id IS NULL) = (last_job_attempt IS NULL)", name="question_clustering_states_last_job_pair_ck"),
        sa.CheckConstraint("(last_job_id IS NULL) = (last_job_status IS NULL)", name="question_clustering_states_last_job_status_pair_ck"),
        sa.CheckConstraint(
            "last_job_status IS NULL OR last_job_status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="question_clustering_states_last_job_status_ck",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("retry_job_id", name="question_clustering_states_retry_job_uq"),
    )
    _install_updated_at_trigger("question_clustering_states")

    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clustering_sequence", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("reaction_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.CheckConstraint("clustering_sequence > 0", name="questions_clustering_sequence_ck"),
        sa.CheckConstraint(
            "content = btrim(content) AND content IS NFC NORMALIZED AND char_length(content) BETWEEN 1 AND 300",
            name="questions_content_normalized_ck",
        ),
        sa.CheckConstraint("status IN ('OPEN', 'SELECTED', 'ANSWERED')", name="questions_status_ck"),
        sa.CheckConstraint("reaction_count >= 0", name="questions_reaction_count_ck"),
        sa.CheckConstraint("version > 0", name="questions_version_ck"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "session_id", name="questions_id_session_uq"),
        sa.UniqueConstraint("session_id", "clustering_sequence", name="questions_session_clustering_sequence_uq"),
    )
    _install_updated_at_trigger("questions")

    op.create_table(
        "question_reactions",
        sa.Column("question_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("question_reactions_user_idx", "question_reactions", ["user_id", sa.text("created_at DESC")])

    op.create_table(
        "ai_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("target_material_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_recording_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_chat_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_user_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_answer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_transcript_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_start_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_end_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("clustering_mode", sa.Text(), nullable=True),
        sa.Column("input_through_sequence", sa.BigInteger(), nullable=True),
        sa.Column("base_revision", sa.BigInteger(), nullable=True),
        sa.Column("final_answered_through_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key_hash", postgresql.BYTEA(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("blocks_session_completion", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("run_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_stage", sa.Text(), nullable=True),
        sa.Column("progress_percent", sa.SmallInteger(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "job_type IN ('MATERIAL_PROCESSING', 'QUESTION_CLUSTERING', 'LIVE_SUMMARY', 'FINAL_SUMMARY', "
            "'CHAT_RESPONSE', 'SESSION_POSTPROCESSING', 'RECORDING_TRANSCRIPTION', 'ANSWER_ORGANIZATION')",
            name="ai_jobs_type_ck",
        ),
        sa.CheckConstraint("visibility IN ('SHARED', 'REQUESTER_ONLY')", name="ai_jobs_visibility_ck"),
        sa.CheckConstraint("status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')", name="ai_jobs_status_ck"),
        sa.CheckConstraint("attempt > 0", name="ai_jobs_attempt_ck"),
        sa.CheckConstraint("version > 0", name="ai_jobs_version_ck"),
        sa.CheckConstraint("num_nonnulls(target_material_id, target_recording_id, target_chat_id, target_answer_id) <= 1", name="ai_jobs_target_cardinality_ck"),
        sa.CheckConstraint("target_material_id IS NULL OR job_type = 'MATERIAL_PROCESSING'", name="ai_jobs_material_target_ck"),
        sa.CheckConstraint("target_recording_id IS NULL OR job_type = 'RECORDING_TRANSCRIPTION'", name="ai_jobs_recording_target_ck"),
        sa.CheckConstraint(
            "(job_type = 'CHAT_RESPONSE' AND target_chat_id IS NOT NULL AND target_user_message_id IS NOT NULL) "
            "OR (job_type <> 'CHAT_RESPONSE' AND target_chat_id IS NULL AND target_user_message_id IS NULL)",
            name="ai_jobs_chat_target_ck",
        ),
        sa.CheckConstraint("target_answer_id IS NULL OR job_type = 'ANSWER_ORGANIZATION'", name="ai_jobs_answer_target_ck"),
        sa.CheckConstraint("job_type <> 'MATERIAL_PROCESSING' OR target_material_id IS NOT NULL", name="ai_jobs_material_type_target_ck"),
        sa.CheckConstraint("job_type <> 'RECORDING_TRANSCRIPTION' OR target_recording_id IS NOT NULL", name="ai_jobs_recording_type_target_ck"),
        sa.CheckConstraint("job_type <> 'ANSWER_ORGANIZATION' OR target_answer_id IS NOT NULL", name="ai_jobs_answer_type_target_ck"),
        sa.CheckConstraint(
            "(job_type = 'ANSWER_ORGANIZATION' AND input_transcript_version_id IS NOT NULL "
            "AND input_start_segment_id IS NOT NULL AND input_end_segment_id IS NOT NULL) "
            "OR (job_type <> 'ANSWER_ORGANIZATION' AND input_transcript_version_id IS NULL "
            "AND input_start_segment_id IS NULL AND input_end_segment_id IS NULL)",
            name="ai_jobs_answer_input_ck",
        ),
        sa.CheckConstraint("(input_start_segment_id IS NULL) = (input_end_segment_id IS NULL)", name="ai_jobs_input_segment_pair_ck"),
        sa.CheckConstraint("(input_transcript_version_id IS NULL) = (input_start_segment_id IS NULL)", name="ai_jobs_input_version_segment_ck"),
        sa.CheckConstraint(
            "(job_type = 'QUESTION_CLUSTERING' AND clustering_mode IS NOT NULL "
            "AND input_through_sequence IS NOT NULL AND base_revision IS NOT NULL) "
            "OR (job_type <> 'QUESTION_CLUSTERING' AND clustering_mode IS NULL "
            "AND input_through_sequence IS NULL AND base_revision IS NULL)",
            name="ai_jobs_clustering_input_ck",
        ),
        sa.CheckConstraint("job_type <> 'QUESTION_CLUSTERING' OR requester_user_id IS NULL", name="ai_jobs_clustering_requester_ck"),
        sa.CheckConstraint("clustering_mode IS NULL OR clustering_mode IN ('LIVE_INCREMENTAL', 'FINAL')", name="ai_jobs_clustering_mode_ck"),
        sa.CheckConstraint(
            "(clustering_mode = 'FINAL' AND final_answered_through_at IS NOT NULL) "
            "OR (clustering_mode IS DISTINCT FROM 'FINAL' AND final_answered_through_at IS NULL)",
            name="ai_jobs_final_answered_through_ck",
        ),
        sa.CheckConstraint("clustering_mode <> 'LIVE_INCREMENTAL' OR (visibility = 'SHARED' AND NOT blocks_session_completion)", name="ai_jobs_live_clustering_visibility_ck"),
        sa.CheckConstraint("clustering_mode <> 'FINAL' OR (visibility = 'SHARED' AND blocks_session_completion)", name="ai_jobs_final_clustering_visibility_ck"),
        sa.CheckConstraint("(visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL) OR visibility = 'SHARED'", name="ai_jobs_visibility_requester_ck"),
        sa.CheckConstraint("NOT blocks_session_completion OR visibility = 'SHARED'", name="ai_jobs_blocking_visibility_ck"),
        sa.CheckConstraint(
            "job_type NOT IN ('LIVE_SUMMARY', 'CHAT_RESPONSE') OR "
            "(visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL AND NOT blocks_session_completion)",
            name="ai_jobs_personal_visibility_ck",
        ),
        sa.CheckConstraint("job_type <> 'FINAL_SUMMARY' OR (visibility = 'SHARED' AND requester_user_id IS NULL AND blocks_session_completion)", name="ai_jobs_final_summary_visibility_ck"),
        sa.CheckConstraint(
            "job_type NOT IN ('SESSION_POSTPROCESSING', 'RECORDING_TRANSCRIPTION', 'ANSWER_ORGANIZATION') "
            "OR (visibility = 'SHARED' AND requester_user_id IS NULL AND blocks_session_completion)",
            name="ai_jobs_processing_visibility_ck",
        ),
        sa.CheckConstraint("progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100", name="ai_jobs_progress_percent_ck"),
        sa.CheckConstraint("(run_token IS NOT NULL) = (status = 'RUNNING')", name="ai_jobs_run_token_ck"),
        sa.CheckConstraint("(lease_expires_at IS NOT NULL) = (status = 'RUNNING')", name="ai_jobs_lease_ck"),
        sa.CheckConstraint(
            "(status = 'PENDING' AND started_at IS NULL AND finished_at IS NULL AND error_code IS NULL AND error_message IS NULL) "
            "OR (status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL AND error_code IS NULL AND error_message IS NULL) "
            "OR (status = 'SUCCEEDED' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND error_code IS NULL AND error_message IS NULL) "
            "OR (status = 'FAILED' AND finished_at IS NOT NULL AND error_code IS NOT NULL)",
            name="ai_jobs_terminal_state_ck",
        ),
        sa.CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="ai_jobs_finished_after_started_ck"),
        sa.CheckConstraint("dedupe_key_hash IS NULL OR octet_length(dedupe_key_hash) = 32", name="ai_jobs_dedupe_hash_length_ck"),
        sa.CheckConstraint("input_through_sequence IS NULL OR input_through_sequence >= 0", name="ai_jobs_input_sequence_ck"),
        sa.CheckConstraint("base_revision IS NULL OR base_revision >= 0", name="ai_jobs_base_revision_ck"),
        sa.ForeignKeyConstraint(["session_id"], ["lecture_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "session_id", name="ai_jobs_id_session_uq"),
    )
    _install_updated_at_trigger("ai_jobs")


def downgrade() -> None:
    """Drop jobs and question inputs before their Session parent."""

    op.drop_table("ai_jobs")
    op.drop_table("question_reactions")
    op.drop_table("questions")
    op.drop_table("question_clustering_states")
