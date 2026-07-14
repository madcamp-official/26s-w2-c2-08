"""Unauthenticated process and database health routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError

from tbd.api.dependencies import get_database
from tbd.core.errors import ApiError
from tbd.db import Database
from tbd.schemas.errors import ErrorResponse
from tbd.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter(prefix="/api", tags=["Health"])
DatabaseDependency = Annotated[Database, Depends(get_database)]
REQUEST_ID_RESPONSE_HEADER = {
    "X-Request-ID": {
        "description": "요청 추적용 식별자. 요청 값을 수용하거나 서버가 생성한다.",
        "schema": {"type": "string"},
    }
}


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={200: {"headers": REQUEST_ID_RESPONSE_HEADER}},
)
async def health() -> HealthResponse:
    """Return a liveness result without calling external services."""

    return HealthResponse(status="ok")


@router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    responses={
        200: {"headers": REQUEST_ID_RESPONSE_HEADER},
        503: {
            "model": ErrorResponse,
            "headers": REQUEST_ID_RESPONSE_HEADER,
        },
    },
)
async def database_health(database: DatabaseDependency) -> DatabaseHealthResponse:
    """Return readiness only after a PostgreSQL round trip succeeds."""

    try:
        await database.check_connection()
    except SQLAlchemyError as exc:
        raise ApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="데이터베이스에 연결할 수 없습니다.",
        ) from exc

    return DatabaseHealthResponse(status="ok", database="reachable")
