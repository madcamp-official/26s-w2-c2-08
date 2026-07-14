"""Course aggregate and per-course membership models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class Course(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """A course with one immutable owner and an encrypted join code."""

    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="courses_title_not_blank_ck"),
        CheckConstraint("length(btrim(semester)) > 0", name="courses_semester_not_blank_ck"),
        CheckConstraint(
            "octet_length(join_code_lookup_hash) = 32",
            name="courses_join_code_lookup_hash_length_ck",
        ),
        CheckConstraint(
            "octet_length(join_code_nonce) = 12",
            name="courses_join_code_nonce_length_ck",
        ),
        CheckConstraint("join_code_lookup_key_version > 0", name="courses_lookup_key_version_ck"),
        CheckConstraint("join_code_key_version > 0", name="courses_key_version_ck"),
        CheckConstraint("version > 0", name="courses_version_ck"),
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    semester: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    join_code_lookup_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False, unique=True)
    join_code_lookup_key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    join_code_ciphertext: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    join_code_nonce: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    join_code_key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class CourseMember(Base):
    """A user's role scoped to one course."""

    __tablename__ = "course_members"
    __table_args__ = (
        CheckConstraint("role IN ('PROFESSOR', 'STUDENT')", name="course_members_role_ck"),
        Index(
            "course_members_one_professor_per_course_uq",
            "course_id",
            unique=True,
            postgresql_where="role = 'PROFESSOR'",
        ),
        Index("course_members_user_role_idx", "user_id", "role", "course_id"),
    )

    course_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
