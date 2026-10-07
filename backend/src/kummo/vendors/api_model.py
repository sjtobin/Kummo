from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Vendor(BaseModel):
    """A vendor as the API exposes it. `auth_user_id` is internal and stays out."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    email: str
    website: str | None = None
    activity_type: list[str]
    picture: str | None = None
