"""Integration checks for PostgreSQL schema prerequisites."""

import asyncio

import pytest
from sqlalchemy import text

from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database

pytestmark = pytest.mark.integration


def _create_test_database(database_url: str):
    """Create a database resource bound to the isolated migrated database."""

    return create_database(
        Settings(
            _env_file=None,
            app_env=AppEnvironment.TEST,
            database_url=database_url,
        )
    )


async def read_extension_version(database_url: str, name: str) -> str | None:
    """Return an installed extension version by its stable public name."""

    database = _create_test_database(database_url)
    try:
        async with database.engine.connect() as connection:
            return await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = :name"),
                {"name": name},
            )
    finally:
        await database.dispose()


def test_pgvector_migration_is_applied(migrated_database_url: str) -> None:
    """The migrated database must expose the vector extension."""

    version = asyncio.run(read_extension_version(migrated_database_url, "vector"))

    assert version is not None


def test_pgcrypto_and_updated_at_trigger_function_are_applied(
    migrated_database_url: str,
) -> None:
    """The schema spine needs UUID generation and its shared timestamp trigger."""

    async def read_common_schema() -> tuple[str | None, str | None]:
        database = _create_test_database(migrated_database_url)
        try:
            async with database.engine.connect() as connection:
                extension = await connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'pgcrypto'")
                )
                function = await connection.scalar(
                    text("SELECT to_regprocedure('set_updated_at()')")
                )
                return extension, function
        finally:
            await database.dispose()

    extension, function = asyncio.run(read_common_schema())

    assert extension is not None
    assert function == "set_updated_at()"
