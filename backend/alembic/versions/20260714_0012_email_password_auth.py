"""Add local email/password credentials.

Revision ID: 20260714_0012
Revises: 20260714_0011
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0012"
down_revision: str | None = "20260714_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve each active normalized email and store one local password verifier per user."""

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT lower(btrim(primary_email))
            FROM users
            WHERE primary_email IS NOT NULL AND deleted_at IS NULL
            GROUP BY lower(btrim(primary_email))
            HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION
              'cannot enable email/password auth while active users have duplicate emails';
          END IF;
        END $$;
        """
    )
    op.execute(
        "UPDATE users SET primary_email = lower(btrim(primary_email)) "
        "WHERE primary_email IS NOT NULL"
    )
    op.create_index(
        "users_active_primary_email_uq",
        "users",
        ["primary_email"],
        unique=True,
        postgresql_where=sa.text("primary_email IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_table(
        "user_password_credentials",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.execute(
        "CREATE TRIGGER user_password_credentials_set_updated_at "
        "BEFORE UPDATE ON user_password_credentials "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    """Remove local credentials before allowing duplicate active emails again."""

    op.drop_table("user_password_credentials")
    op.drop_index("users_active_primary_email_uq", table_name="users")
