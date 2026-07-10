"""Opt-in integration checks for PostgreSQL and pgvector."""

import asyncio
import os

import pytest
from sqlalchemy import text

from tbd.db import engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1",
    reason="set RUN_DATABASE_TESTS=1 with PostgreSQL running",
)


async def read_vector_version() -> str | None:
    """Return the installed pgvector extension version."""

    async with engine.connect() as connection:
        return await connection.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )


def test_pgvector_migration_is_applied() -> None:
    """The migrated database must expose the vector extension."""

    try:
        version = asyncio.run(read_vector_version())
    finally:
        asyncio.run(engine.dispose())

    assert version is not None
