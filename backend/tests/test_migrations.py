"""Fresh PostgreSQL migration round-trip checks."""

from collections.abc import Callable

import psycopg
import pytest
from sqlalchemy.engine import make_url

pytestmark = [pytest.mark.integration, pytest.mark.migration]


def _sync_dsn(database_url: str) -> str:
    """Convert the application URL into a synchronous psycopg DSN."""

    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


def _migration_state(database_url: str) -> tuple[str | None, str | None]:
    """Return the Alembic revision and pgvector version if present."""

    with psycopg.connect(_sync_dsn(database_url)) as connection:
        revision = connection.execute("SELECT to_regclass('public.alembic_version')").fetchone()
        current_revision = None
        if revision is not None and revision[0] is not None:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            current_revision = row[0] if row is not None else None

        row = connection.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        vector_version = row[0] if row is not None else None

    return current_revision, vector_version


def test_fresh_upgrade_downgrade_and_reupgrade(
    temporary_database_url: str,
    alembic_runner: Callable[..., None],
) -> None:
    """Every migration must work from empty DB, downgrade, and apply again."""

    alembic_runner(temporary_database_url, "upgrade", "head")
    revision, vector_version = _migration_state(temporary_database_url)
    assert revision is not None
    assert vector_version is not None
    upgraded_revision = revision

    alembic_runner(temporary_database_url, "downgrade", "base")
    revision, vector_version = _migration_state(temporary_database_url)
    assert revision is None
    assert vector_version is None

    alembic_runner(temporary_database_url, "upgrade", "head")
    revision, vector_version = _migration_state(temporary_database_url)
    assert revision == upgraded_revision
    assert vector_version is not None
