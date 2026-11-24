from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

VoteChoice = Literal["yes", "no", "wait"]


class VoteRequest(BaseModel):
    choice: VoteChoice


class VoteOut(BaseModel):
    id: int
    alert_id: int
    user_id: int
    choice: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VoteSummary(BaseModel):
    alert_id: int
    yes: int = 0
    no: int = 0
    wait: int = 0
    total_votes: int = 0
    total_members: int = 0
    my_vote: str | None = None
    user_votes: dict[str, str] = {}
