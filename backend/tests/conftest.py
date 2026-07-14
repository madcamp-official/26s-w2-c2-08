"""Shared unit-test app and runtime-resource fixtures."""

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings


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
