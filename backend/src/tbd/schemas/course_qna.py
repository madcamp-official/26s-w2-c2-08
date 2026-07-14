"""Public, author-anonymous projections for the Course Q&A archive."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tbd.schemas.courses import LectureSessionSummary
from tbd.schemas.questions import QuestionResponse


class CourseArchiveAnswerOrganization(BaseModel):
    """Content-only organization projection without Job or provider provenance."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)


class CourseArchiveCompletedAnswer(BaseModel):
    """A terminal Answer projection containing only archive display fields."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {
                    "title": "Completed text Answer",
                    "properties": {
                        "answer_type": {"const": "TEXT"},
                        "text_content": {"type": "string", "minLength": 1},
                        "organization": {"type": "null"},
                    },
                },
                {
                    "title": "Completed voice Answer",
                    "properties": {"answer_type": {"const": "VOICE"}},
                },
            ]
        },
    )

    id: UUID
    answer_type: Literal["VOICE", "TEXT"]
    status: Literal["COMPLETED"]
    text_content: str | None = Field(min_length=1, max_length=2000)
    organization: CourseArchiveAnswerOrganization | None
    completed_at: datetime

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> "CourseArchiveCompletedAnswer":
        if self.answer_type == "TEXT" and (
            self.text_content is None or self.organization is not None
        ):
            raise ValueError("TEXT archive Answer requires text_content and no organization")
        return self


class CourseStudentQuestionArchiveItem(BaseModel):
    """One student Question without author-identifying fields."""

    model_config = ConfigDict(extra="forbid")

    target_type: Literal["STUDENT_QUESTION"]
    session: LectureSessionSummary
    question: QuestionResponse
    target_text_snapshot: str = Field(min_length=1, max_length=300)
    answer: CourseArchiveCompletedAnswer | None
    record_url: str = Field(pattern=r"^/sessions/[^/?#]+$")
    occurred_at: datetime


class CourseRepresentativeQuestionArchiveItem(BaseModel):
    """One AI representative target that has a completed public Answer."""

    model_config = ConfigDict(extra="forbid")

    target_type: Literal["AI_REPRESENTATIVE_QUESTION"]
    session: LectureSessionSummary
    representative_question_id: UUID
    target_text_snapshot: str = Field(min_length=1, max_length=300)
    answer: CourseArchiveCompletedAnswer
    record_url: str = Field(pattern=r"^/sessions/[^/?#]+$")
    occurred_at: datetime


CourseQnaArchiveItem = Annotated[
    CourseStudentQuestionArchiveItem | CourseRepresentativeQuestionArchiveItem,
    Field(discriminator="target_type"),
]


class CourseQnaArchiveResponse(BaseModel):
    """A stable flat page from every visible Q&A target in one Course."""

    model_config = ConfigDict(extra="forbid")

    items: list[CourseQnaArchiveItem]
    next_cursor: str | None
