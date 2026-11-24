from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.normalization import utcnow

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.message import Message
    from app.models.room import Room
    from app.models.room_member import RoomMember
    from app.models.vote import Vote
    from app.models.watch import Watch


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Mapping between the internal user and the Nexconn user id (Platform Chat API).
    nexconn_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    rooms_created: Mapped[list[Room]] = relationship(
        "Room", back_populates="creator", foreign_keys="Room.created_by"
    )
    memberships: Mapped[list[RoomMember]] = relationship(
        "RoomMember", back_populates="user", cascade="all, delete-orphan"
    )
    watches_created: Mapped[list[Watch]] = relationship(
        "Watch", back_populates="creator", foreign_keys="Watch.created_by"
    )
    votes: Mapped[list[Vote]] = relationship("Vote", back_populates="user", cascade="all, delete-orphan")
    messages: Mapped[list[Message]] = relationship("Message", back_populates="sender")
    booked_watches: Mapped[list[Watch]] = relationship(
        "Watch", back_populates="booked_by", foreign_keys="Watch.booked_by_id"
    )
