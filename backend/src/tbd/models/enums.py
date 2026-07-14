"""Database text values mirrored as Python ``StrEnum`` classes."""

from enum import StrEnum


class CourseMemberRole(StrEnum):
    PROFESSOR = "PROFESSOR"
    STUDENT = "STUDENT"


class LectureSessionStatus(StrEnum):
    READY = "READY"
    LIVE = "LIVE"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"


class MaterialProcessingStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class RecordingStatus(StrEnum):
    CAPTURING = "CAPTURING"
    UPLOAD_PENDING = "UPLOAD_PENDING"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"


class RecordingUploadStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class TranscriptSource(StrEnum):
    LIVE = "LIVE"
    RECORDING = "RECORDING"


class TranscriptStatus(StrEnum):
    FINALIZING = "FINALIZING"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"
    EMPTY = "EMPTY"


class QuestionStatus(StrEnum):
    OPEN = "OPEN"
    SELECTED = "SELECTED"
    ANSWERED = "ANSWERED"


class RepresentativeQuestionLifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PRESERVED = "PRESERVED"
    DISCARDED = "DISCARDED"


class AnswerStatus(StrEnum):
    CAPTURING = "CAPTURING"
    COMPLETED = "COMPLETED"


class AnswerTranscriptMappingStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SummaryType(StrEnum):
    LIVE = "LIVE"
    FINAL = "FINAL"


class SummaryVisibility(StrEnum):
    REQUESTER_ONLY = "REQUESTER_ONLY"
    COURSE_MEMBERS = "COURSE_MEMBERS"


class ChatMode(StrEnum):
    LIVE = "LIVE"
    REVIEW = "REVIEW"


class ChatMessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class AIJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class AIJobVisibility(StrEnum):
    SHARED = "SHARED"
    REQUESTER_ONLY = "REQUESTER_ONLY"


class ClusteringMode(StrEnum):
    LIVE_INCREMENTAL = "LIVE_INCREMENTAL"
    FINAL = "FINAL"


class AIJobType(StrEnum):
    MATERIAL_PROCESSING = "MATERIAL_PROCESSING"
    QUESTION_CLUSTERING = "QUESTION_CLUSTERING"
    LIVE_SUMMARY = "LIVE_SUMMARY"
    FINAL_SUMMARY = "FINAL_SUMMARY"
    CHAT_RESPONSE = "CHAT_RESPONSE"
    SESSION_POSTPROCESSING = "SESSION_POSTPROCESSING"
    RECORDING_TRANSCRIPTION = "RECORDING_TRANSCRIPTION"
    ANSWER_ORGANIZATION = "ANSWER_ORGANIZATION"
    KNOWLEDGE_INDEXING = "KNOWLEDGE_INDEXING"


class RealtimeTicketScope(StrEnum):
    SESSION_EVENTS_READ = "SESSION_EVENTS_READ"
    SESSION_AUDIO_WRITE = "SESSION_AUDIO_WRITE"


class AuthenticationProvider(StrEnum):
    GOOGLE = "GOOGLE"
