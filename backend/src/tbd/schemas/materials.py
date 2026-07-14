"""Public request and response payloads for attached PDF materials."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tbd.schemas.courses import LectureSessionSummary
from tbd.schemas.jobs import AIJobResponse


class LectureMaterialResponse(BaseModel):
    """Safe projection of one attached PDF without its private storage key."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    display_name: str
    mime_type: Literal["application/pdf"]
    byte_size: int = Field(ge=1, le=100_000_000)
    page_count: int | None = Field(default=None, ge=1)
    processing_status: Literal["UPLOADED", "PROCESSING", "READY", "FAILED"]
    created_at: datetime


class LectureMaterialListResponse(BaseModel):
    """One stable page of active materials in creation order."""

    model_config = ConfigDict(extra="forbid")

    items: list[LectureMaterialResponse]
    next_cursor: str | None


class CourseMaterialArchiveItem(BaseModel):
    """One attached Material paired with its public class summary and API-only URLs."""

    model_config = ConfigDict(extra="forbid")

    session: LectureSessionSummary
    material: LectureMaterialResponse
    content_url: str | None
    download_url: str | None


class CourseMaterialArchiveResponse(BaseModel):
    """A stable flat page from every visible class in one Course."""

    model_config = ConfigDict(extra="forbid")

    items: list[CourseMaterialArchiveItem]
    next_cursor: str | None


class MaterialUploadAcceptedResponse(BaseModel):
    """The stored PDF and its durable non-blocking processing Job."""

    model_config = ConfigDict(extra="forbid")

    material: LectureMaterialResponse
    job: AIJobResponse
