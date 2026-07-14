"""Public user representations."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """Current user's provider-backed profile without account-wide roles."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    display_name: str
    email: str | None
    avatar_url: str | None
