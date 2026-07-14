"""Tests for application settings precedence."""

import pytest
from pydantic import ValidationError

from tbd.core.config import REPOSITORY_ROOT, AppEnvironment, Settings

pytestmark = pytest.mark.unit


def test_database_url_environment_variable_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process environment variable overrides defaults and dotenv files."""

    expected = "postgresql+psycopg://app:secret@db:5432/app"
    monkeypatch.setenv("DATABASE_URL", expected)

    settings = Settings(_env_file=None)

    assert settings.effective_database_url == expected


def test_relative_storage_root_is_resolved_from_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Storage paths must not depend on the process working directory."""

    monkeypatch.setenv("STORAGE_ROOT", "data/uploads")

    settings = Settings(_env_file=None)

    assert settings.storage_root == REPOSITORY_ROOT / "data" / "uploads"


def test_database_url_is_built_from_postgres_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compose and the backend should share one set of PostgreSQL values."""

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "database.local")
    monkeypatch.setenv("POSTGRES_HOST_PORT", "5544")
    monkeypatch.setenv("POSTGRES_DB", "lecture")
    monkeypatch.setenv("POSTGRES_USER", "app user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret/value")

    settings = Settings(_env_file=None)

    assert settings.effective_database_url == (
        "postgresql+psycopg://app%20user:secret%2Fvalue@database.local:5544/lecture"
    )


def test_production_requires_explicit_database_url() -> None:
    """Production cannot silently fall back to repository development settings."""

    with pytest.raises(ValidationError, match="DATABASE_URL must be set"):
        Settings(_env_file=None, app_env=AppEnvironment.PRODUCTION)


def test_production_rejects_repository_development_credentials() -> None:
    """An explicit URL must not embed the documented local password."""

    with pytest.raises(ValidationError, match="repository development credentials"):
        Settings(
            _env_file=None,
            app_env=AppEnvironment.PRODUCTION,
            database_url="postgresql+psycopg://tbd:tbd_dev@database:5432/tbd",
        )


def test_production_accepts_explicit_non_default_database_url() -> None:
    """Production can use an explicitly configured non-development database URL."""

    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.PRODUCTION,
        database_url="postgresql+psycopg://goal:strong-password@database:5432/goal",
    )

    assert settings.effective_database_url.endswith("@database:5432/goal")
