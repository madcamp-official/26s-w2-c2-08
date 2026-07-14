"""Email and password authentication request and response schemas."""

import unicodedata

from pydantic import BaseModel, ConfigDict, field_validator

from tbd.auth.passwords import InvalidEmailError, normalize_email
from tbd.schemas.users import UserResponse


class EmailPasswordRegisterRequest(BaseModel):
    """Create a new local account and immediately establish a browser session."""

    model_config = ConfigDict(extra="forbid")

    display_name: str
    email: str
    password: str

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).strip()
        if not 1 <= len(normalized) <= 100:
            raise ValueError("display_name must contain 1 to 100 characters")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        try:
            return normalize_email(value)
        except InvalidEmailError as exc:
            raise ValueError("email must be a valid email address") from exc

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not 12 <= len(value) <= 128:
            raise ValueError("password must contain 12 to 128 characters")
        return value


class EmailPasswordLoginRequest(BaseModel):
    """Authenticate one existing local account without exposing account existence."""

    model_config = ConfigDict(extra="forbid")

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        try:
            return normalize_email(value)
        except InvalidEmailError as exc:
            raise ValueError("email must be a valid email address") from exc

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not 1 <= len(value) <= 128:
            raise ValueError("password must contain 1 to 128 characters")
        return value


class AuthenticatedUserResponse(BaseModel):
    """The public user returned after a local credential establishes a session."""

    user: UserResponse
