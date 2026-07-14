"""Add common PostgreSQL schema facilities.

Revision ID: 20260714_0002
Revises: 20260710_0001
Create Date: 2026-07-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260714_0002"
down_revision: str | None = "20260710_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Install UUID support and the reusable ``updated_at`` trigger function."""

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE FUNCTION set_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
        """
    )


def downgrade() -> None:
    """Remove facilities after dependent table revisions have been reverted."""

    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
