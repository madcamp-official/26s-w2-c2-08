"""Validated Course request and response payloads."""

import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

CourseRole = Literal["PROFESSOR", "STUDENT"]
CourseRoleFilter = Literal["ALL", "PROFESSOR", "STUDENT"]
NonBlankText = Annotated[str, StringConstraints(min_length=1)]


class CourseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankText
    semester: NonBlankText

    @field_validator("title", "semester")
    @classmethod
    def strip_and_require_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class CourseJoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    join_code: str

    @field_validator("join_code")
    @classmethod
    def normalize_join_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if re.fullmatch(r"[A-Z]{6}", normalized, re.ASCII) is None:
            raise ValueError("must contain exactly six ASCII letters")
        return normalized


class LectureSessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    lecture_date: date
    status: Literal["READY", "LIVE", "PROCESSING", "COMPLETED"]
    started_at: datetime | None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    semester: str
    role: CourseRole
    join_code: Annotated[str, Field(pattern=r"^[A-Z]{6}$")] | None = None
    current_session: LectureSessionSummary | None
    created_at: datetime


class CourseListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CourseResponse]
    next_cursor: str | None
