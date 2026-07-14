"""Public user representations."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """Current user's authentication-method-neutral profile without global roles."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    display_name: str
    email: str | None
    avatar_url: str | None
