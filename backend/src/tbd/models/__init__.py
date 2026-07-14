"""SQLAlchemy model declarations and shared relational vocabulary."""

from tbd.models.auth import AuthSession, OAuthTransaction, RealtimeTicket
from tbd.models.base import Base
from tbd.models.clustering import (
    AIRepresentativeQuestion,
    Answer,
    AnswerOrganization,
    AnswerTranscriptMapping,
    QuestionCluster,
    QuestionClusterMember,
)
from tbd.models.common import TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin
from tbd.models.consistency import IdempotencyRecord, OutboxEvent, StorageDeletionLedger
from tbd.models.courses import Course, CourseMember
from tbd.models.knowledge import (
    ChatMessage,
    ChatMessageEvidence,
    ChatSession,
    KnowledgeChunk,
    LectureSummary,
)
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
from tbd.models.users import User, UserAuthIdentity, UserPasswordCredential

__all__ = [
    "Base",
    "AuthSession",
    "AIJob",
    "AIRepresentativeQuestion",
    "Answer",
    "AnswerOrganization",
    "AnswerTranscriptMapping",
    "ChatMessage",
    "ChatMessageEvidence",
    "ChatSession",
    "Course",
    "CourseMember",
    "IdempotencyRecord",
    "LectureMaterial",
    "LectureSession",
    "LectureSummary",
    "KnowledgeChunk",
    "OAuthTransaction",
    "OutboxEvent",
    "Question",
    "QuestionCluster",
    "QuestionClusterMember",
    "QuestionClusteringState",
    "QuestionReaction",
    "RealtimeTicket",
    "RecordingUpload",
    "SessionRecording",
    "StorageDeletionLedger",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserAuthIdentity",
    "UserPasswordCredential",
    "VersionMixin",
    "TranscriptGap",
    "TranscriptSegment",
    "TranscriptVersion",
]
