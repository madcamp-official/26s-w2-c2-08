"""Enforce the approved completed Answer text boundary.

Revision ID: 20260714_0015
Revises: 20260714_0014
Create Date: 2026-07-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260714_0015"
down_revision: str | None = "20260714_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("answers_text_content_ck", "answers", type_="check")
    op.create_check_constraint(
        "answers_text_content_ck",
        "answers",
        "text_content IS NULL OR (text_content = btrim(text_content) "
        "AND text_content IS NFC NORMALIZED "
        "AND char_length(text_content) BETWEEN 1 AND 2000)",
    )


def downgrade() -> None:
    op.drop_constraint("answers_text_content_ck", "answers", type_="check")
    op.create_check_constraint(
        "answers_text_content_ck",
        "answers",
        "text_content IS NULL OR char_length(btrim(text_content)) > 0",
    )
