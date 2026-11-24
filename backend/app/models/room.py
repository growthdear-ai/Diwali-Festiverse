from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.normalization import utcnow

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.message import Message
    from app.models.room_member import RoomMember
    from app.models.user import User
    from app.models.watch import Watch


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nexconn_conversation_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    creator: Mapped[User] = relationship("User", back_populates="rooms_created", foreign_keys=[created_by])
    members: Mapped[list[RoomMember]] = relationship(
        "RoomMember", back_populates="room", cascade="all, delete-orphan"
    )
    watches: Mapped[list[Watch]] = relationship("Watch", back_populates="room", cascade="all, delete-orphan")
    alerts: Mapped[list[Alert]] = relationship("Alert", back_populates="room", cascade="all, delete-orphan")
    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="room", cascade="all, delete-orphan"
    )
