"""Add the fixed development RAG vector profile and indexing Job type.

Revision ID: 20260714_0014
Revises: 20260714_0013
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260714_0014"
down_revision: str | None = "20260714_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AI_JOB_TYPES = (
    "'MATERIAL_PROCESSING', 'QUESTION_CLUSTERING', 'LIVE_SUMMARY', "
    "'FINAL_SUMMARY', 'CHAT_RESPONSE', 'SESSION_POSTPROCESSING', "
    "'RECORDING_TRANSCRIPTION', 'ANSWER_ORGANIZATION', 'KNOWLEDGE_INDEXING'"
)
_PREVIOUS_AI_JOB_TYPES = (
    "'MATERIAL_PROCESSING', 'QUESTION_CLUSTERING', 'LIVE_SUMMARY', "
    "'FINAL_SUMMARY', 'CHAT_RESPONSE', 'SESSION_POSTPROCESSING', "
    "'RECORDING_TRANSCRIPTION', 'ANSWER_ORGANIZATION'"
)


def _create_job_type_constraint(types: str) -> None:
    op.create_check_constraint("ai_jobs_type_ck", "ai_jobs", f"job_type IN ({types})")


def upgrade() -> None:
    """Persist eight-dimensional deterministic vectors and one active session index Job."""

    op.drop_constraint("ai_jobs_type_ck", "ai_jobs", type_="check")
    _create_job_type_constraint(_AI_JOB_TYPES)
    op.create_index(
        "ai_jobs_one_active_knowledge_indexing_uq",
        "ai_jobs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text(
            "job_type = 'KNOWLEDGE_INDEXING' AND status IN ('PENDING', 'RUNNING')"
        ),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding", Vector(8), nullable=False),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_model", sa.Text(), nullable=False),
    )
    op.execute(
        "CREATE INDEX knowledge_chunks_embedding_hnsw_idx ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    """Remove the vector profile before restoring the prior Job type contract."""

    op.execute("DROP INDEX knowledge_chunks_embedding_hnsw_idx")
    op.drop_column("knowledge_chunks", "embedding_model")
    op.drop_column("knowledge_chunks", "embedding")
    op.drop_index("ai_jobs_one_active_knowledge_indexing_uq", table_name="ai_jobs")
    op.drop_constraint("ai_jobs_type_ck", "ai_jobs", type_="check")
    _create_job_type_constraint(_PREVIOUS_AI_JOB_TYPES)
