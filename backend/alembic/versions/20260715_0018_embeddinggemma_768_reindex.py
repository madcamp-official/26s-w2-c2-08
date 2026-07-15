"""Adopt EmbeddingGemma's 768-dimensional retrieval profile and reindex.

Revision ID: 20260715_0018
Revises: 20260714_0017
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260715_0018"
down_revision: str | None = "20260714_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HNSW_INDEX = "knowledge_chunks_embedding_hnsw_idx"
_REINDEX_CANCEL_CODE = "EMBEDDING_PROFILE_REINDEX_REQUIRED"
_REINDEX_CANCEL_MESSAGE = "임베딩 profile 변경으로 전체 재색인이 예약되었습니다."


def _cancel_active_indexing_jobs() -> None:
    """Fence old 8D Workers before their result can reach the new vector column."""

    op.execute(
        sa.text(
            """
            UPDATE ai_jobs
            SET status = 'CANCELLED',
                run_token = NULL,
                lease_expires_at = NULL,
                error_code = :error_code,
                error_message = :error_message,
                finished_at = now(),
                updated_at = now()
            WHERE job_type = 'KNOWLEDGE_INDEXING'
              AND status IN ('PENDING', 'RUNNING')
            """
        ).bindparams(error_code=_REINDEX_CANCEL_CODE, error_message=_REINDEX_CANCEL_MESSAGE)
    )


def _delete_derived_knowledge() -> None:
    """Remove vectors and their stale Evidence without deleting source records."""

    op.execute(
        "DELETE FROM chat_message_evidence "
        "WHERE knowledge_chunk_id IN (SELECT id FROM knowledge_chunks)"
    )
    op.execute("DELETE FROM knowledge_chunks")
    # ``chat_message_evidence`` and KnowledgeChunk source FKs are deferred in
    # this schema. PostgreSQL refuses ALTER TABLE while their delete events are
    # pending, so validate the now-empty derived graph before changing vector
    # typmod inside the same migration transaction.
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _enqueue_full_reindex() -> None:
    """Queue exactly one new shared index Job for every currently indexable Session."""

    op.execute(
        """
        INSERT INTO ai_jobs (
            session_id,
            job_type,
            visibility,
            status,
            attempt,
            version,
            blocks_session_completion,
            retryable
        )
        SELECT sessions.id,
               'KNOWLEDGE_INDEXING',
               'SHARED',
               'PENDING',
               1,
               1,
               false,
               false
        FROM lecture_sessions AS sessions
        WHERE EXISTS (
            SELECT 1
            FROM lecture_materials AS materials
            WHERE materials.session_id = sessions.id
              AND materials.processing_status = 'READY'
              AND materials.detached_at IS NULL
        )
        OR EXISTS (
            SELECT 1
            FROM transcript_segments AS segments
            WHERE segments.session_id = sessions.id
              AND segments.transcript_version_id = sessions.canonical_transcript_version_id
        )
        OR EXISTS (
            SELECT 1
            FROM answers
            WHERE answers.session_id = sessions.id
              AND answers.status = 'COMPLETED'
              AND answers.text_content IS NOT NULL
        )
        ON CONFLICT (session_id)
        WHERE job_type = 'KNOWLEDGE_INDEXING' AND status IN ('PENDING', 'RUNNING')
        DO NOTHING
        """
    )


def _create_hnsw_index() -> None:
    op.execute(
        "CREATE INDEX knowledge_chunks_embedding_hnsw_idx ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def upgrade() -> None:
    """Discard incompatible 8D vectors, then queue a complete 768D rebuild."""

    _cancel_active_indexing_jobs()
    op.execute(f"DROP INDEX {_HNSW_INDEX}")
    _delete_derived_knowledge()
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        existing_type=Vector(8),
        type_=Vector(768),
        postgresql_using="embedding::text::vector(768)",
    )
    _create_hnsw_index()
    _enqueue_full_reindex()


def downgrade() -> None:
    """Restore the old empty 8D schema; the 768D index remains non-portable."""

    _cancel_active_indexing_jobs()
    op.execute(f"DROP INDEX {_HNSW_INDEX}")
    _delete_derived_knowledge()
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        existing_type=Vector(768),
        type_=Vector(8),
        postgresql_using="embedding::text::vector(8)",
    )
    _create_hnsw_index()
