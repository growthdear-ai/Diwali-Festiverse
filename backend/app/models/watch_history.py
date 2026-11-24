from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.normalization import utcnow

if TYPE_CHECKING:
    from app.models.watch import Watch


class WatchHistory(Base):
    __tablename__ = "watch_history"
    __table_args__ = (Index("ix_watch_history_watch_checked", "watch_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(
        ForeignKey("watches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    observed_value: Mapped[float | None] = mapped_column(Float)
    observed_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    watch: Mapped[Watch] = relationship("Watch", back_populates="history")
