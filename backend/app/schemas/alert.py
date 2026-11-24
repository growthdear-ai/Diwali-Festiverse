from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vote import VoteSummary


class AlertOut(BaseModel):
    id: int
    room_id: int
    watch_id: int
    title: str
    observed_value: str | None = None
    explanation: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    verification_status: str
    event_key: str
    created_at: datetime
    payload: dict[str, Any] | None = None
    votes: VoteSummary | None = None

    model_config = ConfigDict(from_attributes=True)


class CompleteRequest(BaseModel):
    action: Literal["booked"] = "booked"


class CompleteResponse(BaseModel):
    alert_id: int
    watch_id: int
    watch_status: str
    booked_by: str
    message: str


class ShareOut(BaseModel):
    alert_id: int
    summary: str
    share_url: str | None
    whatsapp_url: str
