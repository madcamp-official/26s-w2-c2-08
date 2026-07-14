"""Allow requester-only LIVE Summary Jobs to snapshot transcript input.

Revision ID: 20260714_0016
Revises: 20260714_0015
Create Date: 2026-07-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260714_0016"
down_revision: str | None = "20260714_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LIVE_SUMMARY_INPUT = (
    "(job_type IN ('ANSWER_ORGANIZATION', 'LIVE_SUMMARY') "
    "AND input_transcript_version_id IS NOT NULL AND input_start_segment_id IS NOT NULL "
    "AND input_end_segment_id IS NOT NULL) OR (job_type NOT IN "
    "('ANSWER_ORGANIZATION', 'LIVE_SUMMARY') AND input_transcript_version_id IS NULL "
    "AND input_start_segment_id IS NULL AND input_end_segment_id IS NULL)"
)
_ANSWER_ONLY_INPUT = (
    "(job_type = 'ANSWER_ORGANIZATION' "
    "AND input_transcript_version_id IS NOT NULL AND input_start_segment_id IS NOT NULL "
    "AND input_end_segment_id IS NOT NULL) OR (job_type <> 'ANSWER_ORGANIZATION' "
    "AND input_transcript_version_id IS NULL AND input_start_segment_id IS NULL "
    "AND input_end_segment_id IS NULL)"
)


def upgrade() -> None:
    op.drop_constraint("ai_jobs_answer_input_ck", "ai_jobs", type_="check")
    op.create_check_constraint("ai_jobs_answer_input_ck", "ai_jobs", _LIVE_SUMMARY_INPUT)


def downgrade() -> None:
    op.drop_constraint("ai_jobs_answer_input_ck", "ai_jobs", type_="check")
    op.create_check_constraint("ai_jobs_answer_input_ck", "ai_jobs", _ANSWER_ONLY_INPUT)
