"""Persist the exact Transcript input selected for FINAL_SUMMARY Jobs."""

from alembic import op

revision = "20260715_0019"
down_revision = "20260715_0018"
branch_labels = None
depends_on = None

_FINAL_SUMMARY_INPUT = (
    "(job_type IN ('ANSWER_ORGANIZATION', 'LIVE_SUMMARY') "
    "AND input_transcript_version_id IS NOT NULL AND input_start_segment_id IS NOT NULL "
    "AND input_end_segment_id IS NOT NULL) OR (job_type = 'FINAL_SUMMARY' "
    "AND input_transcript_version_id IS NOT NULL AND input_start_segment_id IS NULL "
    "AND input_end_segment_id IS NULL) OR (job_type NOT IN "
    "('ANSWER_ORGANIZATION', 'LIVE_SUMMARY', 'FINAL_SUMMARY') "
    "AND input_transcript_version_id IS NULL AND input_start_segment_id IS NULL "
    "AND input_end_segment_id IS NULL)"
)

_LEGACY_INPUT = (
    "(job_type IN ('ANSWER_ORGANIZATION', 'LIVE_SUMMARY') "
    "AND input_transcript_version_id IS NOT NULL AND input_start_segment_id IS NOT NULL "
    "AND input_end_segment_id IS NOT NULL) OR (job_type NOT IN "
    "('ANSWER_ORGANIZATION', 'LIVE_SUMMARY') AND input_transcript_version_id IS NULL "
    "AND input_start_segment_id IS NULL AND input_end_segment_id IS NULL)"
)


def upgrade() -> None:
    op.execute(
        "UPDATE ai_jobs AS job "
        "SET input_transcript_version_id = COALESCE("
        "(SELECT summary.source_transcript_version_id FROM lecture_summaries AS summary "
        "WHERE summary.created_by_job_id = job.id LIMIT 1), "
        "session.canonical_transcript_version_id) "
        "FROM lecture_sessions AS session "
        "WHERE job.session_id = session.id AND job.job_type = 'FINAL_SUMMARY' "
        "AND job.input_transcript_version_id IS NULL"
    )
    op.drop_constraint("ai_jobs_answer_input_ck", "ai_jobs", type_="check")
    op.drop_constraint("ai_jobs_input_version_segment_ck", "ai_jobs", type_="check")
    op.create_check_constraint("ai_jobs_answer_input_ck", "ai_jobs", _FINAL_SUMMARY_INPUT)
    op.create_check_constraint(
        "ai_jobs_input_version_segment_ck",
        "ai_jobs",
        "input_start_segment_id IS NULL OR input_transcript_version_id IS NOT NULL",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_jobs SET input_transcript_version_id = NULL WHERE job_type = 'FINAL_SUMMARY'"
    )
    op.drop_constraint("ai_jobs_answer_input_ck", "ai_jobs", type_="check")
    op.drop_constraint("ai_jobs_input_version_segment_ck", "ai_jobs", type_="check")
    op.create_check_constraint("ai_jobs_answer_input_ck", "ai_jobs", _LEGACY_INPUT)
    op.create_check_constraint(
        "ai_jobs_input_version_segment_ck",
        "ai_jobs",
        "(input_transcript_version_id IS NULL) = (input_start_segment_id IS NULL)",
    )
