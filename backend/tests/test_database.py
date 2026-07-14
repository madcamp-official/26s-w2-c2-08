"""Opt-in integration checks for PostgreSQL and pgvector."""

import asyncio
import os

import pytest
from sqlalchemy import text

from tbd.core.config import get_settings
from tbd.db import create_database

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1",
    reason="set RUN_DATABASE_TESTS=1 with PostgreSQL running",
)


async def read_vector_version() -> str | None:
    """Return the installed pgvector extension version."""

    database = create_database(get_settings())
    try:
        async with database.engine.connect() as connection:
            return await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
    finally:
        await database.dispose()


def test_pgvector_migration_is_applied() -> None:
    """The migrated database must expose the vector extension."""

    version = asyncio.run(read_vector_version())

    assert version is not None
