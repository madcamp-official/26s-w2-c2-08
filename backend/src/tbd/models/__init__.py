"""SQLAlchemy model declarations and shared relational vocabulary."""

from tbd.models.auth import AuthSession, OAuthTransaction, RealtimeTicket
from tbd.models.base import Base
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin
from tbd.models.courses import Course, CourseMember
from tbd.models.materials import (
    LectureMaterial,
    RecordingUpload,
    SessionRecording,
    TranscriptGap,
    TranscriptSegment,
    TranscriptVersion,
)
from tbd.models.questions import AIJob, Question, QuestionClusteringState, QuestionReaction
from tbd.models.sessions import LectureSession
from tbd.models.users import User, UserAuthIdentity

__all__ = [
    "Base",
    "AuthSession",
    "AIJob",
    "Course",
    "CourseMember",
    "LectureMaterial",
    "LectureSession",
    "OAuthTransaction",
    "Question",
    "QuestionClusteringState",
    "QuestionReaction",
    "RealtimeTicket",
    "RecordingUpload",
    "SessionRecording",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserAuthIdentity",
    "VersionMixin",
    "TranscriptGap",
    "TranscriptSegment",
    "TranscriptVersion",
]
