"""Allow a completed FINAL_SUMMARY to be regenerated with a newer prompt."""

import sqlalchemy as sa
from alembic import op

revision = "20260715_0020"
down_revision = "20260715_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ai_jobs_one_final_summary_uq", table_name="ai_jobs")
    op.create_index(
        "ai_jobs_one_active_final_summary_uq",
        "ai_jobs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'FINAL_SUMMARY' AND status IN ('PENDING', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("ai_jobs_one_active_final_summary_uq", table_name="ai_jobs")
    op.execute(
        "DELETE FROM lecture_summaries WHERE created_by_job_id IN ("
        "SELECT id FROM ai_jobs WHERE job_type = 'FINAL_SUMMARY' "
        "AND dedupe_key_hash IS NOT NULL)"
    )
    op.execute(
        "DELETE FROM ai_jobs WHERE job_type = 'FINAL_SUMMARY' AND dedupe_key_hash IS NOT NULL"
    )
    op.create_index(
        "ai_jobs_one_final_summary_uq",
        "ai_jobs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'FINAL_SUMMARY'"),
    )
