"""Tests for application settings precedence."""

import base64

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
        frontend_origin="https://goal.example",
        auth_allowed_origins="https://goal.example",
        auth_secret_key="a-production-auth-secret-with-at-least-32-bytes",
        google_oidc_client_id="client-id.apps.googleusercontent.com",
        google_oidc_client_secret="client-secret",
        google_oidc_redirect_uri="https://api.goal.example/api/v1/auth/google/callback",
        idempotency_response_encryption_key=base64.b64encode(b"x" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"y" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"z" * 32).decode(),
    )

    assert settings.effective_database_url.endswith("@database:5432/goal")


def test_idempotency_response_key_must_be_a_base64_aes_256_key() -> None:
    """A configured response cipher key cannot be malformed or the wrong size."""

    with pytest.raises(ValidationError, match="must decode to exactly 32 bytes"):
        Settings(_env_file=None, idempotency_response_encryption_key="dG9vLXNob3J0")


def test_production_requires_idempotency_response_encryption_key() -> None:
    """Production must not start an encrypted-response API without its key."""

    with pytest.raises(ValidationError, match="IDEMPOTENCY_RESPONSE_ENCRYPTION_KEY"):
        Settings(
            _env_file=None,
            app_env=AppEnvironment.PRODUCTION,
            database_url="postgresql+psycopg://goal:strong-password@database:5432/goal",
        )


def test_course_join_code_keys_are_independent_and_validated() -> None:
    """Course code encryption and HMAC lookup each require strong configured material."""

    with pytest.raises(ValidationError, match="COURSE_JOIN_CODE_ENCRYPTION_KEY"):
        Settings(_env_file=None, course_join_code_encryption_key="dG9vLXNob3J0")
    with pytest.raises(ValidationError, match="COURSE_JOIN_CODE_LOOKUP_KEY"):
        Settings(_env_file=None, course_join_code_lookup_key="dG9vLXNob3J0")


def test_production_rejects_http_auth_origin() -> None:
    """Production browser origins must use HTTPS."""

    with pytest.raises(ValidationError, match="FRONTEND_ORIGIN must use HTTPS"):
        Settings(
            _env_file=None,
            app_env=AppEnvironment.PRODUCTION,
            database_url="postgresql+psycopg://goal:strong-password@database:5432/goal",
            auth_secret_key="a-production-auth-secret-with-at-least-32-bytes",
            google_oidc_client_id="client-id.apps.googleusercontent.com",
            google_oidc_client_secret="client-secret",
            idempotency_response_encryption_key=base64.b64encode(b"x" * 32).decode(),
            course_join_code_encryption_key=base64.b64encode(b"y" * 32).decode(),
            course_join_code_lookup_key=base64.b64encode(b"z" * 32).decode(),
        )


def test_auth_origin_rejects_paths() -> None:
    """Origin allowlists are exact origins rather than arbitrary URL prefixes."""

    with pytest.raises(ValidationError, match="exact scheme"):
        Settings(_env_file=None, auth_allowed_origins="http://localhost:5173/path")
