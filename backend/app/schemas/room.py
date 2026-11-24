from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RoomCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=300)
    nexconn_conversation_id: str | None = Field(default=None, max_length=128)


class MemberOut(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    role: str
    joined_at: datetime


class RoomOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    invite_code: str
    created_by: int
    nexconn_conversation_id: str | None = None
    created_at: datetime
    member_count: int = 0
    my_role: str | None = None
    members: list[MemberOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class InviteOut(BaseModel):
    room_id: int
    invite_code: str
    invite_url: str
    whatsapp_url: str
    message: str


class MessageCreate(BaseModel):
    message_text: str = Field(min_length=1, max_length=4000)
    message_type: str = Field(default="text", max_length=32)


class MessageOut(BaseModel):
    id: int
    room_id: int
    sender_id: int | None
    message_text: str
    message_type: str
    provider_message_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageWithBotOut(BaseModel):
    message: MessageOut
    bot_reply: dict[str, Any] | None = None
