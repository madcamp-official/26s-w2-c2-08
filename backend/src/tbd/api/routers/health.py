"""Unauthenticated process and database health routes."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tbd.db import engine

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a liveness result without calling external services."""

    return {"status": "ok"}


@router.get("/health/db")
async def database_health() -> dict[str, str]:
    """Return readiness only after a PostgreSQL round trip succeeds."""

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc

    return {"status": "ok", "database": "reachable"}
