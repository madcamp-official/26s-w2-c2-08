"""Unauthenticated process and database health routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from tbd.api.dependencies import get_database
from tbd.db import Database

router = APIRouter(prefix="/api", tags=["health"])
DatabaseDependency = Annotated[Database, Depends(get_database)]


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a liveness result without calling external services."""

    return {"status": "ok"}


@router.get("/health/db")
async def database_health(database: DatabaseDependency) -> dict[str, str]:
    """Return readiness only after a PostgreSQL round trip succeeds."""

    try:
        await database.check_connection()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc

    return {"status": "ok", "database": "reachable"}
