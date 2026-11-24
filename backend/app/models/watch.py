from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.normalization import utcnow

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.room import Room
    from app.models.user import User
    from app.models.watch_history import WatchHistory

WATCH_TYPES = ("flight", "stock", "job_notification", "topic")
WATCH_STATUSES = ("active", "paused", "completed", "deleted")


class Watch(Base):
    __tablename__ = "watches"
    __table_args__ = (
        Index("ix_watches_status_next_check", "status", "next_check_at"),
        Index("ix_watches_room_status", "room_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    watch_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    rule_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    check_interval: Mapped[int] = mapped_column(default=30, nullable=False)  # minutes
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime)
    booked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    room: Mapped[Room] = relationship("Room", back_populates="watches")
    creator: Mapped[User] = relationship("User", back_populates="watches_created", foreign_keys=[created_by])
    booked_by: Mapped[User | None] = relationship("User", back_populates="booked_watches", foreign_keys=[booked_by_id])
    history: Mapped[list[WatchHistory]] = relationship(
        "WatchHistory", back_populates="watch", cascade="all, delete-orphan", order_by="WatchHistory.checked_at"
    )
    alerts: Mapped[list[Alert]] = relationship("Alert", back_populates="watch", cascade="all, delete-orphan")
