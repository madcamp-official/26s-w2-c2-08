"""SQLAlchemy model declarations and shared relational vocabulary."""

from tbd.models.auth import AuthSession, OAuthTransaction, RealtimeTicket
from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin
from tbd.models.courses import Course, CourseMember
from tbd.models.sessions import LectureSession
from tbd.models.users import User, UserAuthIdentity

__all__ = [
    "Base",
    "AuthSession",
    "Course",
    "CourseMember",
    "LectureSession",
    "OAuthTransaction",
    "RealtimeTicket",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserAuthIdentity",
    "VersionMixin",
]
