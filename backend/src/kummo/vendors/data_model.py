from datetime import datetime
from uuid import UUID

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY, REAL
from sqlalchemy.orm import Mapped, mapped_column

from ..data_model import SCHEMA, Entity, auth_user_id, created_at, primary_key


class Vendor(Entity):
    """A business offering activities.

    A vendor is the business identity *and* the shop: there is no separate shops
    entity. `auth_user_id` is null for vendors that predate authentication.
    """

    __tablename__ = "vendors"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = primary_key()
    created_at: Mapped[datetime] = created_at()
    auth_user_id: Mapped[UUID | None] = auth_user_id()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(REAL, nullable=True)
    longitude: Mapped[float | None] = mapped_column(REAL, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity_type: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    picture: Mapped[str | None] = mapped_column(Text, nullable=True)
