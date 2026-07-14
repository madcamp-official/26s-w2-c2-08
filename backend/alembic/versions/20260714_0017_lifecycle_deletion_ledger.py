"""Add irreversible Course and recording retention state.

Revision ID: 20260714_0017
Revises: 20260714_0016
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0017"
down_revision: str | None = "20260714_0016"
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
    """Make removed resources inaccessible before their storage cleanup succeeds."""

    op.add_column("courses", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "courses_active_idx",
        "courses",
        ["id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_course_owner_membership() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          checked_course_id uuid;
          owner_user_id uuid;
          is_deleted boolean;
          professor_count integer;
        BEGIN
          checked_course_id := COALESCE(
            (to_jsonb(NEW) ->> 'course_id')::uuid,
            (to_jsonb(OLD) ->> 'course_id')::uuid,
            (to_jsonb(NEW) ->> 'id')::uuid,
            (to_jsonb(OLD) ->> 'id')::uuid
          );

          SELECT created_by_user_id, deleted_at IS NOT NULL
          INTO owner_user_id, is_deleted
          FROM courses WHERE id = checked_course_id;
          IF NOT FOUND OR is_deleted THEN
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
    op.execute("DROP TRIGGER courses_owner_membership_guard ON courses")
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER courses_owner_membership_guard
        AFTER INSERT OR UPDATE OF created_by_user_id, deleted_at OR DELETE ON courses
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_course_owner_membership()
        """
    )

    op.add_column(
        "session_recordings", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "session_recordings",
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "session_recordings_retention_due_idx",
        "session_recordings",
        ["retention_expires_at", "id"],
        postgresql_where=sa.text(
            "deleted_at IS NULL AND retention_expires_at IS NOT NULL AND storage_key IS NOT NULL"
        ),
    )

    op.create_table(
        "storage_deletion_ledgers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "resource_type IN ('MATERIAL', 'RECORDING')",
            name="storage_deletion_ledgers_resource_type_ck",
        ),
        sa.CheckConstraint("byte_size > 0", name="storage_deletion_ledgers_byte_size_ck"),
        sa.CheckConstraint("attempt >= 0", name="storage_deletion_ledgers_attempt_ck"),
        sa.CheckConstraint(
            "state IN ('PENDING', 'RUNNING', 'SUCCEEDED')",
            name="storage_deletion_ledgers_state_ck",
        ),
        sa.CheckConstraint(
            "(state = 'SUCCEEDED') = (succeeded_at IS NOT NULL)",
            name="storage_deletion_ledgers_terminal_state_ck",
        ),
        sa.CheckConstraint(
            "lease_expires_at IS NULL OR state = 'RUNNING'",
            name="storage_deletion_ledgers_lease_state_ck",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("storage_key", name="storage_deletion_ledgers_storage_key_uq"),
    )
    _install_updated_at_trigger("storage_deletion_ledgers")
    op.create_index(
        "storage_deletion_ledgers_claim_idx",
        "storage_deletion_ledgers",
        ["state", "next_attempt_at", "id"],
        postgresql_where=sa.text("state IN ('PENDING', 'RUNNING')"),
    )
    op.create_index(
        "storage_deletion_ledgers_course_idx",
        "storage_deletion_ledgers",
        ["course_id", "state", "id"],
    )


def downgrade() -> None:
    """Remove lifecycle-only persistence in reverse dependency order."""

    op.drop_index("storage_deletion_ledgers_course_idx", table_name="storage_deletion_ledgers")
    op.drop_index("storage_deletion_ledgers_claim_idx", table_name="storage_deletion_ledgers")
    op.drop_table("storage_deletion_ledgers")
    op.drop_index("session_recordings_retention_due_idx", table_name="session_recordings")
    op.drop_column("session_recordings", "retention_expires_at")
    op.drop_column("session_recordings", "deleted_at")
    op.drop_index("courses_active_idx", table_name="courses")
    # The current constraint trigger explicitly watches deleted_at, so it
    # must be removed before dropping that column.
    op.execute("DROP TRIGGER courses_owner_membership_guard ON courses")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_course_owner_membership() RETURNS trigger
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
    op.drop_column("courses", "deleted_at")
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER courses_owner_membership_guard
        AFTER INSERT OR UPDATE OF created_by_user_id OR DELETE ON courses
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_course_owner_membership()
        """
    )
