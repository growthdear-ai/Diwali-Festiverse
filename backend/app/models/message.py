from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.normalization import utcnow

if TYPE_CHECKING:
    from app.models.room import Room
    from app.models.user import User


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_room_created", "room_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    # Nexconn's message UID; unique when present, used to make webhooks idempotent.
    provider_message_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    room: Mapped[Room] = relationship("Room", back_populates="messages")
    sender: Mapped[User | None] = relationship("User", back_populates="messages")
