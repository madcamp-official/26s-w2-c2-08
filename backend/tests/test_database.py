"""Integration checks for PostgreSQL and pgvector."""

import asyncio

import pytest
from sqlalchemy import text

from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database

pytestmark = pytest.mark.integration


async def read_vector_version(database_url: str) -> str | None:
    """Return the installed pgvector extension version."""

    database = create_database(
        Settings(
            _env_file=None,
            app_env=AppEnvironment.TEST,
            database_url=database_url,
        )
    )
    try:
        async with database.engine.connect() as connection:
            return await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
    finally:
        await database.dispose()


def test_pgvector_migration_is_applied(migrated_database_url: str) -> None:
    """The migrated database must expose the vector extension."""

    version = asyncio.run(read_vector_version(migrated_database_url))

    assert version is not None
