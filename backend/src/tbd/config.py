"""Application configuration loaded from environment variables and dotenv files."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings.

    Process environment variables take precedence over the repository-level dotenv
    file so commands behave consistently regardless of their working directory.
    """

    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / ".env",),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ToBeDetermined API"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    postgres_host: str = "127.0.0.1"
    postgres_host_port: int = 5432
    postgres_db: str = "tbd"
    postgres_user: str = "tbd"
    postgres_password: str = "tbd_dev"
    database_url: str = ""
    storage_root: Path = REPOSITORY_ROOT / "data" / "uploads"
    max_upload_bytes: int = 50 * 1024 * 1024

    @model_validator(mode="after")
    def populate_database_url(self) -> "Settings":
        """Build the local database URL from the shared PostgreSQL settings."""

        if self.database_url:
            return self

        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        database = quote(self.postgres_db, safe="")
        self.database_url = (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_host_port}/{database}"
        )
        return self

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
