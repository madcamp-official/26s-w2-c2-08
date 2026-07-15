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


def test_knowledge_embedding_schema_uses_embeddinggemma_dimension(
    migrated_database_url: str,
) -> None:
    """The database must not silently accept the obsolete eight-dimensional profile."""

    async def read_profile() -> tuple[str | None, str | None]:
        database = create_database(
            Settings(
                _env_file=None,
                app_env=AppEnvironment.TEST,
                database_url=migrated_database_url,
            )
        )
        try:
            async with database.engine.connect() as connection:
                dimension = await connection.scalar(
                    text(
                        "SELECT format_type(attribute.atttypid, attribute.atttypmod) "
                        "FROM pg_attribute AS attribute "
                        "JOIN pg_class AS relation ON relation.oid = attribute.attrelid "
                        "WHERE relation.relname = 'knowledge_chunks' "
                        "AND attribute.attname = 'embedding' "
                        "AND NOT attribute.attisdropped"
                    )
                )
                index = await connection.scalar(
                    text("SELECT pg_get_indexdef('knowledge_chunks_embedding_hnsw_idx'::regclass)")
                )
                return dimension, index
        finally:
            await database.dispose()

    dimension, index = asyncio.run(read_profile())

    assert dimension == "vector(768)"
    assert index is not None
    assert "USING hnsw" in index
    assert "vector_cosine_ops" in index


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
