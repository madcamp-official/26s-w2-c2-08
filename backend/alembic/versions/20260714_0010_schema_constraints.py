"""Add deferred relationships, concurrency indexes, and schema guards.

Revision ID: 20260714_0010
Revises: 20260714_0009
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0010"
down_revision: str | None = "20260714_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _deferred_fk(
    name: str,
    source_table: str,
    referent_table: str,
    local_columns: list[str],
    remote_columns: list[str],
    *,
    ondelete: str = "NO ACTION",
) -> None:
    op.create_foreign_key(
        name,
        source_table,
        referent_table,
        local_columns,
        remote_columns,
        ondelete=ondelete,
        deferrable=True,
        initially="DEFERRED",
    )


def _install_integrity_functions() -> None:
    op.execute(
        """
        CREATE FUNCTION enforce_course_owner_membership() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          checked_course_id uuid;
          owner_user_id uuid;
          professor_count integer;
        BEGIN
          checked_course_id := COALESCE(
            (to_jsonb(NEW) ->> 'course_id')::uuid,
            (to_jsonb(OLD) ->> 'course_id')::uuid,
            (to_jsonb(NEW) ->> 'id')::uuid,
            (to_jsonb(OLD) ->> 'id')::uuid
          );

          SELECT created_by_user_id INTO owner_user_id
          FROM courses WHERE id = checked_course_id;
          IF NOT FOUND THEN
            RETURN NULL;
          END IF;

          SELECT count(*) INTO professor_count
          FROM course_members
          WHERE course_id = checked_course_id AND role = 'PROFESSOR';
          IF professor_count <> 1 OR NOT EXISTS (
            SELECT 1 FROM course_members
            WHERE course_id = checked_course_id
              AND user_id = owner_user_id
              AND role = 'PROFESSOR'
          ) THEN
            RAISE EXCEPTION 'course % must retain its creator as sole professor', checked_course_id
              USING ERRCODE = '23514';
          END IF;
          RETURN NULL;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER courses_owner_membership_guard
        AFTER INSERT OR UPDATE OF created_by_user_id OR DELETE ON courses
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_course_owner_membership();
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER course_members_owner_membership_guard
        AFTER INSERT OR UPDATE OR DELETE ON course_members
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_course_owner_membership();
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_active_material_limit() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE active_count integer;
        BEGIN
          IF TG_OP = 'UPDATE' AND NEW.detached_at IS NOT NULL THEN
            RETURN NEW;
          END IF;
          IF TG_OP = 'UPDATE' AND NEW.detached_at IS NULL
             AND OLD.session_id = NEW.session_id AND OLD.detached_at IS NULL THEN
            RETURN NEW;
          END IF;

          PERFORM 1 FROM lecture_sessions WHERE id = NEW.session_id FOR UPDATE;
          SELECT count(*) INTO active_count
          FROM lecture_materials
          WHERE session_id = NEW.session_id
            AND detached_at IS NULL
            AND id <> NEW.id;
          IF active_count >= 10 THEN
            RAISE EXCEPTION 'session % has reached the active material limit', NEW.session_id
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER lecture_materials_active_count_guard
        BEFORE INSERT OR UPDATE OF session_id, detached_at ON lecture_materials
        FOR EACH ROW EXECUTE FUNCTION enforce_active_material_limit();
        """
    )


def _create_indexes() -> None:
    op.create_index(
        "course_members_one_professor_per_course_uq",
        "course_members",
        ["course_id"],
        unique=True,
        postgresql_where=sa.text("role = 'PROFESSOR'"),
    )
    op.create_index(
        "course_members_user_role_idx", "course_members", ["user_id", "role", "course_id"]
    )
    op.create_index(
        "lecture_sessions_one_active_per_course_uq",
        "lecture_sessions",
        ["course_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('READY', 'LIVE', 'PROCESSING')"),
    )
    op.create_index(
        "lecture_sessions_course_history_idx",
        "lecture_sessions",
        ["course_id", sa.text("lecture_date DESC"), sa.text("started_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "lecture_sessions_course_status_idx",
        "lecture_sessions",
        ["course_id", "status", sa.text("updated_at DESC")],
    )

    op.create_index(
        "lecture_materials_active_display_name_uq",
        "lecture_materials",
        ["session_id", "display_name"],
        unique=True,
        postgresql_where=sa.text("detached_at IS NULL"),
    )
    op.create_index(
        "lecture_materials_processed_by_job_uq",
        "lecture_materials",
        ["processed_by_job_id"],
        unique=True,
        postgresql_where=sa.text("processed_by_job_id IS NOT NULL"),
    )
    op.create_index(
        "lecture_materials_session_idx",
        "lecture_materials",
        ["session_id", "created_at", "id"],
        postgresql_where=sa.text("detached_at IS NULL"),
    )
    op.create_index(
        "lecture_materials_processing_idx",
        "lecture_materials",
        ["processing_status", "updated_at"],
        postgresql_where=sa.text(
            "detached_at IS NULL AND processing_status IN ('UPLOADED', 'PROCESSING', 'FAILED')"
        ),
    )
    op.create_index(
        "session_recordings_status_idx", "session_recordings", ["status", "updated_at", "id"]
    )
    op.create_index(
        "session_recordings_publisher_idx",
        "session_recordings",
        ["publisher_user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("publisher_user_id IS NOT NULL"),
    )
    op.create_index(
        "recording_uploads_one_active_uq",
        "recording_uploads",
        ["recording_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "recording_uploads_expiry_idx",
        "recording_uploads",
        ["expires_at", "id"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "recording_uploads_recording_idx",
        "recording_uploads",
        ["recording_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "transcript_versions_created_by_job_attempt_uq",
        "transcript_versions",
        ["created_by_job_id", "created_by_job_attempt"],
        unique=True,
        postgresql_where=sa.text("created_by_job_id IS NOT NULL"),
    )
    op.create_index(
        "transcript_versions_one_finalizing_per_source_uq",
        "transcript_versions",
        ["session_id", "source"],
        unique=True,
        postgresql_where=sa.text("status = 'FINALIZING'"),
    )
    op.create_index(
        "transcript_versions_session_idx",
        "transcript_versions",
        ["session_id", sa.text("version DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "transcript_versions_status_idx", "transcript_versions", ["status", "updated_at", "id"]
    )
    op.create_index(
        "transcript_segments_version_utterance_uq",
        "transcript_segments",
        ["transcript_version_id", "utterance_id"],
        unique=True,
        postgresql_where=sa.text("utterance_id IS NOT NULL"),
    )
    op.create_index(
        "transcript_segments_time_idx",
        "transcript_segments",
        ["transcript_version_id", "start_ms", "id"],
    )
    op.create_index(
        "transcript_gaps_version_time_idx",
        "transcript_gaps",
        ["transcript_version_id", "start_ms", "id"],
    )

    op.create_index(
        "questions_session_recent_idx",
        "questions",
        ["session_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "questions_session_popular_idx",
        "questions",
        [
            "session_id",
            sa.text("reaction_count DESC"),
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
    )
    op.create_index(
        "questions_recent_idx",
        "questions",
        ["session_id", "status", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "questions_popular_idx",
        "questions",
        [
            "session_id",
            "status",
            sa.text("reaction_count DESC"),
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
    )
    op.create_index(
        "questions_clustering_input_idx", "questions", ["session_id", "clustering_sequence", "id"]
    )
    op.create_index(
        "ai_jobs_dedupe_uq",
        "ai_jobs",
        ["session_id", "job_type", "dedupe_key_hash"],
        unique=True,
        postgresql_where=sa.text("dedupe_key_hash IS NOT NULL"),
    )
    op.create_index(
        "ai_jobs_one_active_chat_response_uq",
        "ai_jobs",
        ["target_chat_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'CHAT_RESPONSE' AND status IN ('PENDING', 'RUNNING')"),
    )
    op.create_index(
        "ai_jobs_one_chat_response_per_user_message_uq",
        "ai_jobs",
        ["target_user_message_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'CHAT_RESPONSE'"),
    )
    op.create_index(
        "ai_jobs_one_active_material_processing_uq",
        "ai_jobs",
        ["target_material_id"],
        unique=True,
        postgresql_where=sa.text(
            "job_type = 'MATERIAL_PROCESSING' AND status IN ('PENDING', 'RUNNING')"
        ),
    )
    op.create_index(
        "ai_jobs_one_active_question_clustering_uq",
        "ai_jobs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text(
            "job_type = 'QUESTION_CLUSTERING' AND status IN ('PENDING', 'RUNNING')"
        ),
    )
    op.create_index(
        "ai_jobs_one_final_question_clustering_uq",
        "ai_jobs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'QUESTION_CLUSTERING' AND clustering_mode = 'FINAL'"),
    )
    op.create_index(
        "ai_jobs_one_recording_transcription_uq",
        "ai_jobs",
        ["target_recording_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'RECORDING_TRANSCRIPTION'"),
    )
    op.create_index(
        "ai_jobs_one_answer_organization_uq",
        "ai_jobs",
        ["target_answer_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'ANSWER_ORGANIZATION'"),
    )
    op.create_index(
        "ai_jobs_one_session_postprocessing_uq",
        "ai_jobs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'SESSION_POSTPROCESSING'"),
    )
    op.create_index(
        "ai_jobs_one_final_summary_uq",
        "ai_jobs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'FINAL_SUMMARY'"),
    )
    op.create_index(
        "ai_jobs_session_shared_idx",
        "ai_jobs",
        ["session_id", "status", "job_type", sa.text("created_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("visibility = 'SHARED'"),
    )
    op.create_index(
        "ai_jobs_session_shared_created_idx",
        "ai_jobs",
        ["session_id", sa.text("created_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("visibility = 'SHARED'"),
    )
    op.create_index(
        "ai_jobs_requester_idx",
        "ai_jobs",
        ["requester_user_id", "status", sa.text("created_at DESC")],
        postgresql_where=sa.text("requester_user_id IS NOT NULL"),
    )
    op.create_index(
        "ai_jobs_claim_idx",
        "ai_jobs",
        ["available_at", "created_at", "id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ai_jobs_lease_idx",
        "ai_jobs",
        ["lease_expires_at"],
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.create_index(
        "ai_representative_questions_session_idx",
        "ai_representative_questions",
        ["session_id", "lifecycle_status", "status", "created_at", "id"],
    )
    op.create_index(
        "ai_representative_questions_discarded_cleanup_idx",
        "ai_representative_questions",
        ["discarded_at", "id"],
        postgresql_where=sa.text("lifecycle_status = 'DISCARDED'"),
    )
    op.create_index(
        "ai_representative_questions_job_idx",
        "ai_representative_questions",
        ["created_by_job_id", "created_by_job_attempt"],
    )
    op.create_index(
        "question_clusters_session_idx",
        "question_clusters",
        [
            "session_id",
            sa.text("is_final DESC"),
            sa.text("generation DESC"),
            "ordinal",
            "logical_cluster_id",
        ],
    )
    op.create_index(
        "question_clusters_job_idx",
        "question_clusters",
        ["created_by_job_id", "created_by_job_attempt"],
    )
    op.create_index(
        "question_cluster_members_question_uq",
        "question_cluster_members",
        ["session_id", "generation", "question_id"],
        unique=True,
        postgresql_where=sa.text("question_id IS NOT NULL"),
    )
    op.create_index(
        "question_cluster_members_representative_uq",
        "question_cluster_members",
        ["session_id", "generation", "representative_question_id"],
        unique=True,
        postgresql_where=sa.text("representative_question_id IS NOT NULL"),
    )
    op.create_index(
        "question_cluster_members_cluster_idx",
        "question_cluster_members",
        ["cluster_id", "position"],
    )
    op.create_index(
        "answers_one_per_question_uq",
        "answers",
        ["target_question_id"],
        unique=True,
        postgresql_where=sa.text("target_question_id IS NOT NULL"),
    )
    op.create_index(
        "answers_one_per_representative_question_uq",
        "answers",
        ["target_representative_question_id"],
        unique=True,
        postgresql_where=sa.text("target_representative_question_id IS NOT NULL"),
    )
    op.create_index(
        "answers_one_capturing_per_session_uq",
        "answers",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status = 'CAPTURING'"),
    )
    op.create_index("answers_session_started_idx", "answers", ["session_id", "started_at", "id"])
    op.create_index(
        "answer_transcript_mappings_target_idx",
        "answer_transcript_mappings",
        ["target_transcript_version_id", "status", "answer_id"],
    )
    op.create_index(
        "answer_organizations_session_created_idx",
        "answer_organizations",
        ["session_id", "created_at", "id"],
    )
    op.create_index(
        "answer_organizations_source_idx",
        "answer_organizations",
        ["source_transcript_version_id", "source_start_segment_id", "source_end_segment_id"],
    )

    op.create_index(
        "knowledge_chunks_material_ordinal_uq",
        "knowledge_chunks",
        ["material_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("material_id IS NOT NULL"),
    )
    op.create_index(
        "knowledge_chunks_transcript_ordinal_uq",
        "knowledge_chunks",
        [
            "source_transcript_version_id",
            "transcript_start_segment_id",
            "transcript_end_segment_id",
            "chunk_index",
        ],
        unique=True,
        postgresql_where=sa.text("source_transcript_version_id IS NOT NULL"),
    )
    op.create_index(
        "knowledge_chunks_question_ordinal_uq",
        "knowledge_chunks",
        ["question_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("question_id IS NOT NULL"),
    )
    op.create_index(
        "knowledge_chunks_representative_question_ordinal_uq",
        "knowledge_chunks",
        ["representative_question_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("representative_question_id IS NOT NULL"),
    )
    op.create_index(
        "knowledge_chunks_answer_ordinal_uq",
        "knowledge_chunks",
        ["answer_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("answer_id IS NOT NULL"),
    )
    op.create_index("knowledge_chunks_scope_idx", "knowledge_chunks", ["course_id", "session_id"])
    op.create_index(
        "knowledge_chunks_job_idx",
        "knowledge_chunks",
        ["created_by_job_id", "created_by_job_attempt"],
    )
    op.create_index(
        "lecture_summaries_session_type_idx",
        "lecture_summaries",
        ["session_id", "summary_type", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "lecture_summaries_requester_idx",
        "lecture_summaries",
        ["requester_user_id", "session_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("requester_user_id IS NOT NULL"),
    )
    op.create_index(
        "chat_sessions_owner_idx",
        "chat_sessions",
        ["owner_user_id", "session_id", sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index("chat_sessions_session_mode_idx", "chat_sessions", ["session_id", "mode", "id"])
    op.create_index(
        "chat_messages_created_by_job_uq",
        "chat_messages",
        ["created_by_job_id"],
        unique=True,
        postgresql_where=sa.text("created_by_job_id IS NOT NULL"),
    )
    op.create_index("chat_messages_chat_sequence_idx", "chat_messages", ["chat_id", "sequence"])
    op.create_index(
        "chat_message_evidence_chunk_idx",
        "chat_message_evidence",
        ["knowledge_chunk_id", "session_id"],
    )
    op.create_index(
        "idempotency_records_expiry_idx",
        "idempotency_records",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_index(
        "idempotency_records_session_purge_idx",
        "idempotency_records",
        ["session_id", "id"],
        postgresql_where=sa.text("purge_on_session_end"),
    )
    op.create_index(
        "outbox_events_unpublished_idx",
        "outbox_events",
        ["available_at", "created_at", "id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "outbox_events_session_replay_idx",
        "outbox_events",
        ["session_id", "created_at", "id"],
        postgresql_where=sa.text("session_id IS NOT NULL"),
    )


def _create_deferred_foreign_keys() -> None:
    _deferred_fk(
        "lecture_sessions_canonical_transcript_fk",
        "lecture_sessions",
        "transcript_versions",
        ["canonical_transcript_version_id", "id"],
        ["id", "session_id"],
        ondelete="SET NULL",
    )
    _deferred_fk(
        "lecture_materials_processed_job_fk",
        "lecture_materials",
        "ai_jobs",
        ["processed_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "transcript_versions_recording_fk",
        "transcript_versions",
        "session_recordings",
        ["recording_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "transcript_versions_created_job_fk",
        "transcript_versions",
        "ai_jobs",
        ["created_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "transcript_segments_created_job_fk",
        "transcript_segments",
        "ai_jobs",
        ["created_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "clustering_state_last_job_fk",
        "question_clustering_states",
        "ai_jobs",
        ["last_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "clustering_state_retry_job_fk",
        "question_clustering_states",
        "ai_jobs",
        ["retry_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "representative_questions_job_fk",
        "ai_representative_questions",
        "ai_jobs",
        ["created_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "question_clusters_representative_fk",
        "question_clusters",
        "ai_representative_questions",
        ["representative_question_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "question_clusters_job_fk",
        "question_clusters",
        "ai_jobs",
        ["created_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "cluster_members_cluster_fk",
        "question_cluster_members",
        "question_clusters",
        ["cluster_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "cluster_members_question_fk",
        "question_cluster_members",
        "questions",
        ["question_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "cluster_members_representative_fk",
        "question_cluster_members",
        "ai_representative_questions",
        ["representative_question_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "answers_question_fk",
        "answers",
        "questions",
        ["target_question_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "answers_representative_fk",
        "answers",
        "ai_representative_questions",
        ["target_representative_question_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "answers_transcript_version_fk",
        "answers",
        "transcript_versions",
        ["source_transcript_version_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "answers_start_segment_fk",
        "answers",
        "transcript_segments",
        ["start_segment_id", "source_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "answers_end_segment_fk",
        "answers",
        "transcript_segments",
        ["end_segment_id", "source_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "answer_mappings_answer_fk",
        "answer_transcript_mappings",
        "answers",
        ["answer_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "answer_mappings_version_fk",
        "answer_transcript_mappings",
        "transcript_versions",
        ["target_transcript_version_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "answer_mappings_start_fk",
        "answer_transcript_mappings",
        "transcript_segments",
        ["mapped_start_segment_id", "target_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "answer_mappings_end_fk",
        "answer_transcript_mappings",
        "transcript_segments",
        ["mapped_end_segment_id", "target_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "answer_mappings_job_fk",
        "answer_transcript_mappings",
        "ai_jobs",
        ["processed_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "answer_org_answer_fk",
        "answer_organizations",
        "answers",
        ["answer_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "answer_org_version_fk",
        "answer_organizations",
        "transcript_versions",
        ["source_transcript_version_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "answer_org_start_fk",
        "answer_organizations",
        "transcript_segments",
        ["source_start_segment_id", "source_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "answer_org_end_fk",
        "answer_organizations",
        "transcript_segments",
        ["source_end_segment_id", "source_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "answer_org_job_fk",
        "answer_organizations",
        "ai_jobs",
        ["created_by_job_id", "session_id"],
        ["id", "session_id"],
    )

    _deferred_fk(
        "knowledge_chunks_session_course_fk",
        "knowledge_chunks",
        "lecture_sessions",
        ["session_id", "course_id"],
        ["id", "course_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "knowledge_chunks_material_fk",
        "knowledge_chunks",
        "lecture_materials",
        ["material_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "knowledge_chunks_version_fk",
        "knowledge_chunks",
        "transcript_versions",
        ["source_transcript_version_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "knowledge_chunks_start_fk",
        "knowledge_chunks",
        "transcript_segments",
        ["transcript_start_segment_id", "source_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "knowledge_chunks_end_fk",
        "knowledge_chunks",
        "transcript_segments",
        ["transcript_end_segment_id", "source_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "knowledge_chunks_question_fk",
        "knowledge_chunks",
        "questions",
        ["question_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "knowledge_chunks_representative_fk",
        "knowledge_chunks",
        "ai_representative_questions",
        ["representative_question_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "knowledge_chunks_answer_fk",
        "knowledge_chunks",
        "answers",
        ["answer_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "knowledge_chunks_job_fk",
        "knowledge_chunks",
        "ai_jobs",
        ["created_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "summaries_job_fk",
        "lecture_summaries",
        "ai_jobs",
        ["created_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "summaries_version_fk",
        "lecture_summaries",
        "transcript_versions",
        ["source_transcript_version_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "summaries_start_fk",
        "lecture_summaries",
        "transcript_segments",
        ["source_start_segment_id", "source_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "summaries_end_fk",
        "lecture_summaries",
        "transcript_segments",
        ["source_end_segment_id", "source_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "chat_messages_chat_fk",
        "chat_messages",
        "chat_sessions",
        ["chat_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "chat_messages_job_fk",
        "chat_messages",
        "ai_jobs",
        ["created_by_job_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "chat_evidence_message_fk",
        "chat_message_evidence",
        "chat_messages",
        ["chat_message_id", "session_id"],
        ["id", "session_id"],
        ondelete="CASCADE",
    )
    _deferred_fk(
        "chat_evidence_chunk_fk",
        "chat_message_evidence",
        "knowledge_chunks",
        ["knowledge_chunk_id", "session_id"],
        ["id", "session_id"],
    )

    _deferred_fk(
        "ai_jobs_material_fk",
        "ai_jobs",
        "lecture_materials",
        ["target_material_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "ai_jobs_recording_fk",
        "ai_jobs",
        "session_recordings",
        ["target_recording_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "ai_jobs_chat_fk",
        "ai_jobs",
        "chat_sessions",
        ["target_chat_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "ai_jobs_message_fk",
        "ai_jobs",
        "chat_messages",
        ["target_user_message_id", "target_chat_id", "session_id"],
        ["id", "chat_id", "session_id"],
    )
    _deferred_fk(
        "ai_jobs_answer_fk",
        "ai_jobs",
        "answers",
        ["target_answer_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "ai_jobs_input_version_fk",
        "ai_jobs",
        "transcript_versions",
        ["input_transcript_version_id", "session_id"],
        ["id", "session_id"],
    )
    _deferred_fk(
        "ai_jobs_input_start_fk",
        "ai_jobs",
        "transcript_segments",
        ["input_start_segment_id", "input_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )
    _deferred_fk(
        "ai_jobs_input_end_fk",
        "ai_jobs",
        "transcript_segments",
        ["input_end_segment_id", "input_transcript_version_id", "session_id"],
        ["id", "transcript_version_id", "session_id"],
    )


def upgrade() -> None:
    """Install cross-table validation after all 31 tables exist."""

    _create_indexes()
    _create_deferred_foreign_keys()
    _install_integrity_functions()


def downgrade() -> None:
    """Drop final schema spine guards in reverse dependency order."""

    op.execute("DROP TRIGGER lecture_materials_active_count_guard ON lecture_materials")
    op.execute("DROP FUNCTION enforce_active_material_limit()")
    op.execute("DROP TRIGGER course_members_owner_membership_guard ON course_members")
    op.execute("DROP TRIGGER courses_owner_membership_guard ON courses")
    op.execute("DROP FUNCTION enforce_course_owner_membership()")

    foreign_keys = [
        ("ai_jobs", "ai_jobs_input_end_fk"),
        ("ai_jobs", "ai_jobs_input_start_fk"),
        ("ai_jobs", "ai_jobs_input_version_fk"),
        ("ai_jobs", "ai_jobs_answer_fk"),
        ("ai_jobs", "ai_jobs_message_fk"),
        ("ai_jobs", "ai_jobs_chat_fk"),
        ("ai_jobs", "ai_jobs_recording_fk"),
        ("ai_jobs", "ai_jobs_material_fk"),
        ("chat_message_evidence", "chat_evidence_chunk_fk"),
        ("chat_message_evidence", "chat_evidence_message_fk"),
        ("chat_messages", "chat_messages_job_fk"),
        ("chat_messages", "chat_messages_chat_fk"),
        ("lecture_summaries", "summaries_end_fk"),
        ("lecture_summaries", "summaries_start_fk"),
        ("lecture_summaries", "summaries_version_fk"),
        ("lecture_summaries", "summaries_job_fk"),
        ("knowledge_chunks", "knowledge_chunks_job_fk"),
        ("knowledge_chunks", "knowledge_chunks_answer_fk"),
        ("knowledge_chunks", "knowledge_chunks_representative_fk"),
        ("knowledge_chunks", "knowledge_chunks_question_fk"),
        ("knowledge_chunks", "knowledge_chunks_end_fk"),
        ("knowledge_chunks", "knowledge_chunks_start_fk"),
        ("knowledge_chunks", "knowledge_chunks_version_fk"),
        ("knowledge_chunks", "knowledge_chunks_material_fk"),
        ("knowledge_chunks", "knowledge_chunks_session_course_fk"),
        ("answer_organizations", "answer_org_job_fk"),
        ("answer_organizations", "answer_org_end_fk"),
        ("answer_organizations", "answer_org_start_fk"),
        ("answer_organizations", "answer_org_version_fk"),
        ("answer_organizations", "answer_org_answer_fk"),
        ("answer_transcript_mappings", "answer_mappings_job_fk"),
        ("answer_transcript_mappings", "answer_mappings_end_fk"),
        ("answer_transcript_mappings", "answer_mappings_start_fk"),
        ("answer_transcript_mappings", "answer_mappings_version_fk"),
        ("answer_transcript_mappings", "answer_mappings_answer_fk"),
        ("answers", "answers_end_segment_fk"),
        ("answers", "answers_start_segment_fk"),
        ("answers", "answers_transcript_version_fk"),
        ("answers", "answers_representative_fk"),
        ("answers", "answers_question_fk"),
        ("question_cluster_members", "cluster_members_representative_fk"),
        ("question_cluster_members", "cluster_members_question_fk"),
        ("question_cluster_members", "cluster_members_cluster_fk"),
        ("question_clusters", "question_clusters_job_fk"),
        ("question_clusters", "question_clusters_representative_fk"),
        ("ai_representative_questions", "representative_questions_job_fk"),
        ("question_clustering_states", "clustering_state_retry_job_fk"),
        ("question_clustering_states", "clustering_state_last_job_fk"),
        ("transcript_segments", "transcript_segments_created_job_fk"),
        ("transcript_versions", "transcript_versions_created_job_fk"),
        ("transcript_versions", "transcript_versions_recording_fk"),
        ("lecture_materials", "lecture_materials_processed_job_fk"),
        ("lecture_sessions", "lecture_sessions_canonical_transcript_fk"),
    ]
    for table_name, foreign_key in foreign_keys:
        op.drop_constraint(foreign_key, table_name, type_="foreignkey")

    indexes = [
        "outbox_events_session_replay_idx",
        "outbox_events_unpublished_idx",
        "idempotency_records_session_purge_idx",
        "idempotency_records_expiry_idx",
        "chat_message_evidence_chunk_idx",
        "chat_messages_chat_sequence_idx",
        "chat_messages_created_by_job_uq",
        "chat_sessions_session_mode_idx",
        "chat_sessions_owner_idx",
        "lecture_summaries_requester_idx",
        "lecture_summaries_session_type_idx",
        "knowledge_chunks_job_idx",
        "knowledge_chunks_scope_idx",
        "knowledge_chunks_answer_ordinal_uq",
        "knowledge_chunks_representative_question_ordinal_uq",
        "knowledge_chunks_question_ordinal_uq",
        "knowledge_chunks_transcript_ordinal_uq",
        "knowledge_chunks_material_ordinal_uq",
        "answer_organizations_source_idx",
        "answer_organizations_session_created_idx",
        "answer_transcript_mappings_target_idx",
        "answers_session_started_idx",
        "answers_one_capturing_per_session_uq",
        "answers_one_per_representative_question_uq",
        "answers_one_per_question_uq",
        "question_cluster_members_cluster_idx",
        "question_cluster_members_representative_uq",
        "question_cluster_members_question_uq",
        "question_clusters_job_idx",
        "question_clusters_session_idx",
        "ai_representative_questions_job_idx",
        "ai_representative_questions_discarded_cleanup_idx",
        "ai_representative_questions_session_idx",
        "ai_jobs_lease_idx",
        "ai_jobs_claim_idx",
        "ai_jobs_requester_idx",
        "ai_jobs_session_shared_created_idx",
        "ai_jobs_session_shared_idx",
        "ai_jobs_one_final_summary_uq",
        "ai_jobs_one_session_postprocessing_uq",
        "ai_jobs_one_answer_organization_uq",
        "ai_jobs_one_recording_transcription_uq",
        "ai_jobs_one_final_question_clustering_uq",
        "ai_jobs_one_active_question_clustering_uq",
        "ai_jobs_one_active_material_processing_uq",
        "ai_jobs_one_chat_response_per_user_message_uq",
        "ai_jobs_one_active_chat_response_uq",
        "ai_jobs_dedupe_uq",
        "questions_clustering_input_idx",
        "questions_popular_idx",
        "questions_recent_idx",
        "questions_session_popular_idx",
        "questions_session_recent_idx",
        "transcript_gaps_version_time_idx",
        "transcript_segments_time_idx",
        "transcript_segments_version_utterance_uq",
        "transcript_versions_status_idx",
        "transcript_versions_session_idx",
        "transcript_versions_one_finalizing_per_source_uq",
        "transcript_versions_created_by_job_attempt_uq",
        "recording_uploads_recording_idx",
        "recording_uploads_expiry_idx",
        "recording_uploads_one_active_uq",
        "session_recordings_publisher_idx",
        "session_recordings_status_idx",
        "lecture_materials_processing_idx",
        "lecture_materials_session_idx",
        "lecture_materials_processed_by_job_uq",
        "lecture_materials_active_display_name_uq",
        "lecture_sessions_course_status_idx",
        "lecture_sessions_course_history_idx",
        "lecture_sessions_one_active_per_course_uq",
        "course_members_user_role_idx",
        "course_members_one_professor_per_course_uq",
    ]
    for index in indexes:
        op.drop_index(index)
