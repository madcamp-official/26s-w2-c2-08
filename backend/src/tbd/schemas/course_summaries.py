"""Public Course archive projections for shared FINAL Summaries."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from tbd.schemas.courses import LectureSessionSummary
from tbd.schemas.personal_ai import LectureSummaryResponse
from tbd.schemas.records import FinalSummaryState


class CourseSummarySession(LectureSessionSummary):
    """A class eligible for the FINAL Summary archive."""

    status: Literal["PROCESSING", "COMPLETED"]


class CourseFinalSummaryResponse(LectureSummaryResponse):
    """A shared FINAL result with requester-only variants excluded by type."""

    summary_type: Literal["FINAL"]
    visibility: Literal["COURSE_MEMBERS"]


class CourseSummaryArchiveItemResponse(BaseModel):
    """One class whose content is present only for an AVAILABLE state."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {
                    "title": "공용 FINAL Summary 사용 가능",
                    "properties": {
                        "state": {
                            "type": "object",
                            "properties": {"status": {"const": "AVAILABLE"}},
                            "required": ["status"],
                        },
                        "summary": {"$ref": "#/components/schemas/CourseFinalSummaryResponse"},
                        "summary_url": {
                            "type": "string",
                            "format": "uri-reference",
                            "pattern": "^/api/v1/summaries/[^/?#]+$",
                        },
                    },
                },
                {
                    "title": "공용 FINAL Summary 결과 없음",
                    "properties": {
                        "state": {
                            "type": "object",
                            "properties": {
                                "status": {
                                    "enum": [
                                        "PENDING",
                                        "NOT_APPLICABLE",
                                        "FAILED",
                                        "DATA_INTEGRITY_ERROR",
                                    ]
                                }
                            },
                            "required": ["status"],
                        },
                        "summary": {"type": "null"},
                        "summary_url": {"type": "null"},
                    },
                },
            ]
        },
    )

    session: CourseSummarySession
    state: FinalSummaryState
    summary: CourseFinalSummaryResponse | None
    summary_url: (
        Annotated[
            str,
            StringConstraints(pattern=r"^/api/v1/summaries/[^/?#]+$"),
        ]
        | None
    )

    @model_validator(mode="after")
    def validate_available_result(self) -> Self:
        available = self.state.status == "AVAILABLE"
        if available != (self.summary is not None and self.summary_url is not None):
            raise ValueError("AVAILABLE requires both summary and summary_url")
        if not available and (self.summary is not None or self.summary_url is not None):
            raise ValueError("non-AVAILABLE state cannot expose a summary result")
        return self


class CourseSummaryArchiveResponse(BaseModel):
    """One stable page across all PROCESSING and COMPLETED classes."""

    model_config = ConfigDict(extra="forbid")

    items: list[CourseSummaryArchiveItemResponse]
    next_cursor: str | None
