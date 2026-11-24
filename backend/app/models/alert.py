from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.normalization import utcnow

if TYPE_CHECKING:
    from app.models.room import Room
    from app.models.vote import Vote
    from app.models.watch import Watch


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("watch_id", "event_key", name="uq_alert_watch_event"),
        Index("ix_alerts_room_created", "room_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    watch_id: Mapped[int] = mapped_column(
        ForeignKey("watches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_value: Mapped[str | None] = mapped_column(String(120))
    explanation: Mapped[str | None] = mapped_column(Text)
    sources_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(32), default="not_applicable", nullable=False
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    room: Mapped[Room] = relationship("Room", back_populates="alerts")
    watch: Mapped[Watch] = relationship("Watch", back_populates="alerts")
    votes: Mapped[list[Vote]] = relationship(
        "Vote", back_populates="alert", cascade="all, delete-orphan"
    )
