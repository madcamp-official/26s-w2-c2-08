"""Shared API error response schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """Stable public error information without provider or database internals."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None


class ErrorResponse(BaseModel):
    """Top-level error envelope shared by HTTP endpoints."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
