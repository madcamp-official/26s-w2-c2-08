"""Validated public request and response payloads for lecture sessions."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from tbd.schemas.jobs import AIJobResponse


class LectureSessionCreateRequest(BaseModel):
    """Create one READY class on a Course."""

    model_config = ConfigDict(extra="forbid")

    lecture_date: date
    title: str | None = None

    @field_validator("title")
    @classmethod
    def trim_optional_title(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class LectureSessionUpdateRequest(BaseModel):
    """Replace a class title, with an empty value restoring the automatic title."""

    model_config = ConfigDict(extra="forbid")

    title: str

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        return value.strip()


class LectureSessionResponse(BaseModel):
    """The lifecycle projection visible to a Course member."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    title: str
    lecture_date: date
    status: Literal["READY", "LIVE", "PROCESSING", "COMPLETED"]
    version: int
    canonical_transcript_version_id: UUID | None
    started_at: datetime | None
    ended_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LectureSessionListResponse(BaseModel):
    """A stable page of one Course's classes."""

    model_config = ConfigDict(extra="forbid")

    items: list[LectureSessionResponse]
    next_cursor: str | None


class SessionEndAcceptedResponse(BaseModel):
    """The durable postprocessing coordinator created by a class end request."""

    model_config = ConfigDict(extra="forbid")

    session: LectureSessionResponse
    recording: None = None
    jobs: list[AIJobResponse]
