"""Create user, course, membership, and lecture session tables.

Revision ID: 20260714_0003
Revises: 20260714_0002
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0003"
down_revision: str | None = "20260714_0002"
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
    """Create the ownership and class lifecycle foundation."""

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("primary_email", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("users_active_idx", "users", ["id"], postgresql_where=sa.text("deleted_at IS NULL"))
    _install_updated_at_trigger("users")

    op.create_table(
        "user_auth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_subject", sa.Text(), nullable=False),
        sa.Column("email_snapshot", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("provider IN ('GOOGLE')", name="user_auth_identities_provider_ck"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "provider_subject", name="user_auth_identities_provider_subject_uq"),
        sa.UniqueConstraint("user_id", "provider", name="user_auth_identities_user_provider_uq"),
    )
    op.create_index("user_auth_identities_user_idx", "user_auth_identities", ["user_id"])
    _install_updated_at_trigger("user_auth_identities")

    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("semester", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("join_code_lookup_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("join_code_lookup_key_version", sa.SmallInteger(), nullable=False),
        sa.Column("join_code_ciphertext", postgresql.BYTEA(), nullable=False),
        sa.Column("join_code_nonce", postgresql.BYTEA(), nullable=False),
        sa.Column("join_code_key_version", sa.SmallInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        *_timestamps(),
        sa.CheckConstraint("length(btrim(title)) > 0", name="courses_title_not_blank_ck"),
        sa.CheckConstraint("length(btrim(semester)) > 0", name="courses_semester_not_blank_ck"),
        sa.CheckConstraint("octet_length(join_code_lookup_hash) = 32", name="courses_join_code_lookup_hash_length_ck"),
        sa.CheckConstraint("octet_length(join_code_nonce) = 12", name="courses_join_code_nonce_length_ck"),
        sa.CheckConstraint("join_code_lookup_key_version > 0", name="courses_lookup_key_version_ck"),
        sa.CheckConstraint("join_code_key_version > 0", name="courses_key_version_ck"),
        sa.CheckConstraint("version > 0", name="courses_version_ck"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("join_code_lookup_hash", name="courses_join_code_lookup_hash_uq"),
    )
    _install_updated_at_trigger("courses")

    op.create_table(
        "course_members",
        sa.Column("course_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('PROFESSOR', 'STUDENT')", name="course_members_role_ck"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    )

    op.create_table(
        "lecture_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("lecture_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'READY'")),
        sa.Column("canonical_transcript_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("length(btrim(title)) > 0", name="lecture_sessions_title_not_blank_ck"),
        sa.CheckConstraint(
            "status IN ('READY', 'LIVE', 'PROCESSING', 'COMPLETED')",
            name="lecture_sessions_status_ck",
        ),
        sa.CheckConstraint("version > 0", name="lecture_sessions_version_ck"),
        sa.CheckConstraint(
            """
            (status = 'READY' AND started_at IS NULL AND ended_at IS NULL AND completed_at IS NULL)
            OR (status = 'LIVE' AND started_at IS NOT NULL AND ended_at IS NULL AND completed_at IS NULL)
            OR (status = 'PROCESSING' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NULL)
            OR (status = 'COMPLETED' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NOT NULL)
            """,
            name="lecture_sessions_lifecycle_timestamps_ck",
        ),
        sa.CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="lecture_sessions_ended_after_started_ck"),
        sa.CheckConstraint("completed_at IS NULL OR completed_at >= ended_at", name="lecture_sessions_completed_after_ended_ck"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "course_id", name="lecture_sessions_id_course_uq"),
    )
    _install_updated_at_trigger("lecture_sessions")


def downgrade() -> None:
    """Drop the foundation in dependency-safe order."""

    op.drop_table("lecture_sessions")
    op.drop_table("course_members")
    op.drop_table("courses")
    op.drop_table("user_auth_identities")
    op.drop_table("users")
