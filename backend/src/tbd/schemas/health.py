"""Health endpoint response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Liveness response independent from external dependencies."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


class DatabaseHealthResponse(HealthResponse):
    """Readiness response after PostgreSQL has accepted a query."""

    database: Literal["reachable"]
