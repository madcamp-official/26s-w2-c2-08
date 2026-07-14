"""Application configuration loaded from environment variables and dotenv files."""

import base64
import binascii
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tbd.core.crypto import AesGcmResponseCipher

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_POSTGRES_DB = "tbd"
DEFAULT_POSTGRES_HOST = "127.0.0.1"
DEFAULT_POSTGRES_PASSWORD = "tbd_dev"
DEFAULT_POSTGRES_USER = "tbd"


class AppEnvironment(StrEnum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Runtime settings with production-safe database validation."""

    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / ".env",),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ToBeDetermined API"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    postgres_host: str = DEFAULT_POSTGRES_HOST
    postgres_host_port: int = 5432
    postgres_db: str = DEFAULT_POSTGRES_DB
    postgres_user: str = DEFAULT_POSTGRES_USER
    postgres_password: str = DEFAULT_POSTGRES_PASSWORD
    database_url: str | None = None
    storage_root: Path = REPOSITORY_ROOT / "data" / "uploads"
    max_upload_bytes: int = 100_000_000
    idempotency_response_encryption_key: SecretStr | None = None
    idempotency_response_encryption_key_version: int = Field(default=1, ge=1)

    @property
    def effective_database_url(self) -> str:
        """Return the explicit URL or build one from local PostgreSQL settings."""

        if self.database_url:
            return self.database_url

        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        database = quote(self.postgres_db, safe="")
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_host_port}/{database}"
        )

    @property
    def idempotency_response_cipher(self) -> AesGcmResponseCipher | None:
        """Build the in-memory cipher for encrypted idempotency responses."""

        if self.idempotency_response_encryption_key is None:
            return None
        key = base64.b64decode(
            self.idempotency_response_encryption_key.get_secret_value(),
            validate=True,
        )
        return AesGcmResponseCipher(
            key,
            key_version=self.idempotency_response_encryption_key_version,
        )

    @model_validator(mode="after")
    def validate_production_database(self) -> "Settings":
        """Reject repository defaults when a process claims to be production."""

        if self.app_env is not AppEnvironment.PRODUCTION:
            return self

        if not self.database_url:
            raise ValueError("DATABASE_URL must be set when APP_ENV=production")

        parsed = urlsplit(self.database_url)
        if (
            unquote(parsed.username or "") == DEFAULT_POSTGRES_USER
            and unquote(parsed.password or "") == DEFAULT_POSTGRES_PASSWORD
        ):
            raise ValueError("DATABASE_URL must not use the repository development credentials")

        if self.idempotency_response_encryption_key is None:
            raise ValueError(
                "IDEMPOTENCY_RESPONSE_ENCRYPTION_KEY must be set when APP_ENV=production"
            )

        return self

    @field_validator("idempotency_response_encryption_key")
    @classmethod
    def validate_idempotency_response_encryption_key(
        cls,
        value: SecretStr | None,
    ) -> SecretStr | None:
        """Accept only a base64-encoded AES-256 key when the key is configured."""

        if value is None:
            return None
        encoded = value.get_secret_value().strip()
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("IDEMPOTENCY_RESPONSE_ENCRYPTION_KEY must be base64-encoded") from exc
        if len(decoded) != 32:
            raise ValueError("IDEMPOTENCY_RESPONSE_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return SecretStr(encoded)

    @field_validator("storage_root", mode="after")
    @classmethod
    def resolve_storage_root(cls, value: Path) -> Path:
        """Resolve relative storage paths from the repository root."""

        if value.is_absolute():
            return value
        return (REPOSITORY_ROOT / value).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return one settings instance per process."""

    return Settings()
