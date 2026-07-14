"""Extend AIJob terminal states for cancellation and supersession.

Revision ID: 20260714_0011
Revises: 20260714_0010
Create Date: 2026-07-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260714_0011"
down_revision: str | None = "20260714_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AI_JOB_STATUSES = "'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'SUPERSEDED'"
_PREVIOUS_AI_JOB_STATUSES = "'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'"


def _create_extended_constraints() -> None:
    op.create_check_constraint(
        "question_clustering_states_last_job_status_ck",
        "question_clustering_states",
        f"last_job_status IS NULL OR last_job_status IN ({_AI_JOB_STATUSES})",
    )
    op.create_check_constraint(
        "ai_jobs_status_ck",
        "ai_jobs",
        f"status IN ({_AI_JOB_STATUSES})",
    )
    op.create_check_constraint(
        "ai_jobs_terminal_state_ck",
        "ai_jobs",
        "(status = 'PENDING' AND started_at IS NULL AND finished_at IS NULL "
        "AND error_code IS NULL AND error_message IS NULL) "
        "OR (status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL "
        "AND error_code IS NULL AND error_message IS NULL) "
        "OR (status = 'SUCCEEDED' AND started_at IS NOT NULL AND finished_at IS NOT NULL "
        "AND error_code IS NULL AND error_message IS NULL) "
        "OR (status IN ('FAILED', 'CANCELLED', 'SUPERSEDED') "
        "AND finished_at IS NOT NULL AND error_code IS NOT NULL)",
    )


def _drop_constraints() -> None:
    op.drop_constraint(
        "question_clustering_states_last_job_status_ck",
        "question_clustering_states",
        type_="check",
    )
    op.drop_constraint("ai_jobs_terminal_state_ck", "ai_jobs", type_="check")
    op.drop_constraint("ai_jobs_status_ck", "ai_jobs", type_="check")


def upgrade() -> None:
    """Permit terminal cancellation and supersession without creating a second Job row."""

    _drop_constraints()
    _create_extended_constraints()


def downgrade() -> None:
    """Restore the original four-state Job contract after removing new terminal rows."""

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM ai_jobs WHERE status IN ('CANCELLED', 'SUPERSEDED')
          ) OR EXISTS (
            SELECT 1 FROM question_clustering_states
            WHERE last_job_status IN ('CANCELLED', 'SUPERSEDED')
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade while CANCELLED or SUPERSEDED AIJob history exists';
          END IF;
        END $$;
        """
    )
    _drop_constraints()
    op.create_check_constraint(
        "question_clustering_states_last_job_status_ck",
        "question_clustering_states",
        f"last_job_status IS NULL OR last_job_status IN ({_PREVIOUS_AI_JOB_STATUSES})",
    )
    op.create_check_constraint(
        "ai_jobs_status_ck",
        "ai_jobs",
        f"status IN ({_PREVIOUS_AI_JOB_STATUSES})",
    )
    op.create_check_constraint(
        "ai_jobs_terminal_state_ck",
        "ai_jobs",
        "(status = 'PENDING' AND started_at IS NULL AND finished_at IS NULL "
        "AND error_code IS NULL AND error_message IS NULL) "
        "OR (status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL "
        "AND error_code IS NULL AND error_message IS NULL) "
        "OR (status = 'SUCCEEDED' AND started_at IS NOT NULL AND finished_at IS NOT NULL "
        "AND error_code IS NULL AND error_message IS NULL) "
        "OR (status = 'FAILED' AND finished_at IS NOT NULL AND error_code IS NOT NULL)",
    )
