"""Opt-in integration checks for PostgreSQL schema prerequisites."""

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


async def read_extension_version(name: str) -> str | None:
    """Return the installed extension version by its stable public name."""

    database = create_database(get_settings())
    try:
        async with database.engine.connect() as connection:
            return await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = :name"),
                {"name": name},
            )
    finally:
        await database.dispose()


def test_pgvector_migration_is_applied() -> None:
    """The migrated database must expose the vector extension."""

    version = asyncio.run(read_extension_version("vector"))

    assert version is not None


def test_pgcrypto_and_updated_at_trigger_function_are_applied() -> None:
    """The schema spine needs UUID generation and its shared timestamp trigger."""

    async def read_common_schema() -> tuple[str | None, str | None]:
        database = create_database(get_settings())
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
