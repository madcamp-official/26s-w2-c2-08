"""Shared unit and isolated PostgreSQL integration fixtures."""

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from psycopg import sql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _sync_postgres_url(url: URL) -> URL:
    """Return a psycopg-compatible synchronous URL."""

    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("integration tests require a PostgreSQL DATABASE_URL")
    return url.set(drivername="postgresql")


def _render_url(url: URL) -> str:
    """Render a SQLAlchemy URL without hiding the test password."""

    return url.render_as_string(hide_password=False)


def _run_alembic(database_url: str, *arguments: str) -> None:
    """Run Alembic against one isolated test database."""

    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": AppEnvironment.TEST.value,
            "DATABASE_URL": database_url,
        }
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
    )


@dataclass
class FakeDatabase:
    """Small database resource fake that never opens a network connection."""

    failure: SQLAlchemyError | None = None
    dispose_calls: int = 0

    async def check_connection(self) -> None:
        """Succeed or raise the failure selected by an individual test."""

        if self.failure is not None:
            raise self.failure

    async def dispose(self) -> None:
        """Record application shutdown without owning a real engine."""

        self.dispose_calls += 1


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return isolated test settings without reading the repository dotenv file."""

    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        storage_root=tmp_path / "uploads",
    )


@pytest.fixture
def database() -> FakeDatabase:
    """Return a disposable fake database resource."""

    return FakeDatabase()


@pytest.fixture
def app(settings: Settings, database: FakeDatabase) -> FastAPI:
    """Create a factory-built app with isolated test resources."""

    return create_app(settings=settings, database=database)  # type: ignore[arg-type]


@pytest.fixture
def temporary_database_url() -> Iterator[str]:
    """Create and always drop a unique empty PostgreSQL database.

    A missing server or insufficient CREATE DATABASE permission is an explicit
    integration failure. It is never converted into a pytest skip.
    """

    source_url = make_url(Settings(_env_file=None).effective_database_url)
    database_name = f"goal_test_{uuid4().hex[:16]}"
    admin_url = _sync_postgres_url(source_url).set(database="postgres")
    test_url = source_url.set(database=database_name)
    admin_dsn = _render_url(admin_url)

    try:
        with psycopg.connect(admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(database_name)
                )
            )
    except psycopg.Error as exc:
        raise RuntimeError(
            "integration PostgreSQL is unavailable; run `make db-up` and verify "
            "the configured user can create test databases"
        ) from exc

    try:
        yield _render_url(test_url)
    finally:
        try:
            with psycopg.connect(admin_dsn, autocommit=True) as connection:
                connection.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s AND pid <> pg_backend_pid()
                    """,
                    (database_name,),
                )
                connection.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name))
                )
        except psycopg.Error as exc:
            raise RuntimeError(f"failed to remove isolated test database {database_name}") from exc


@pytest.fixture
def alembic_runner() -> Callable[..., None]:
    """Return the Alembic runner used by migration and fixture setup tests."""

    return _run_alembic


@pytest.fixture
def migrated_database_url(
    temporary_database_url: str,
    alembic_runner: Callable[..., None],
) -> str:
    """Upgrade an empty database to head and return its isolated URL."""

    alembic_runner(temporary_database_url, "upgrade", "head")
    return temporary_database_url
