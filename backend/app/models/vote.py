from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.normalization import utcnow

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.user import User


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("alert_id", "user_id", name="uq_vote_alert_user"),
        CheckConstraint("choice IN ('yes', 'no', 'wait')", name="ck_vote_choice"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    choice: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    alert: Mapped[Alert] = relationship("Alert", back_populates="votes")
    user: Mapped[User] = relationship("User", back_populates="votes")
