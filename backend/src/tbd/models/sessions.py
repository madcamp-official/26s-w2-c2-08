"""Lecture session aggregate model."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class LectureSession(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """A class progressing through READY, LIVE, PROCESSING, and COMPLETED."""

    __tablename__ = "lecture_sessions"
    __table_args__ = (
        UniqueConstraint("id", "course_id", name="lecture_sessions_id_course_uq"),
        CheckConstraint("length(btrim(title)) > 0", name="lecture_sessions_title_not_blank_ck"),
        CheckConstraint(
            "status IN ('READY', 'LIVE', 'PROCESSING', 'COMPLETED')",
            name="lecture_sessions_status_ck",
        ),
        CheckConstraint("version > 0", name="lecture_sessions_version_ck"),
        CheckConstraint(
            """
            (status = 'READY' AND started_at IS NULL AND ended_at IS NULL AND completed_at IS NULL)
            OR (status = 'LIVE' AND started_at IS NOT NULL AND ended_at IS NULL AND completed_at IS NULL)
            OR (status = 'PROCESSING' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NULL)
            OR (status = 'COMPLETED' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NOT NULL)
            """,
            name="lecture_sessions_lifecycle_timestamps_ck",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="lecture_sessions_ended_after_started_ck",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= ended_at",
            name="lecture_sessions_completed_after_ended_ck",
        ),
        ForeignKeyConstraint(
            ["canonical_transcript_version_id", "id"],
            ["transcript_versions.id", "transcript_versions.session_id"],
            name="lecture_sessions_canonical_transcript_fk",
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index(
            "lecture_sessions_one_active_per_course_uq",
            "course_id",
            unique=True,
            postgresql_where="status IN ('READY', 'LIVE', 'PROCESSING')",
        ),
        Index(
            "lecture_sessions_course_history_idx",
            "course_id",
            text("lecture_date DESC"),
            text("started_at DESC"),
            text("id DESC"),
        ),
        Index("lecture_sessions_course_status_idx", "course_id", "status", text("updated_at DESC")),
    )

    course_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    lecture_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'READY'"))
    canonical_transcript_version_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
