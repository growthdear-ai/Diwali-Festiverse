from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import rate_limit
from app.integrations.nexconn_client import nexconn_client
from app.models.message import Message
from app.models.room import Room
from app.models.user import User
from app.services import bot_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


def _text_from_content(content: Any) -> str | None:
    if isinstance(content, str):
        stripped = content.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except ValueError:
            return stripped
        if isinstance(parsed, dict):
            return _text_from_content(parsed)
        return stripped
    if isinstance(content, dict):
        value = content.get("content")
        if isinstance(value, str):
            return value.strip() or None
        return None
    return None


def _first(*values: Any) -> Any:
    for value in values:
        if value:
            return value
    return None


@router.post(
    "/webhooks/nexconn",
    dependencies=[Depends(rate_limit("nexconn-webhook", 600))],
)
async def nexconn_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw_body = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}

    if not nexconn_client.verify_webhook(raw_body, headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Unexpected webhook payload")

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    message = data.get("message") if isinstance(data.get("message"), dict) else data
    if not message and isinstance(data.get("messages"), list) and data["messages"]:
        first = data["messages"][0]
        message = first if isinstance(first, dict) else {}

    channel_id = _first(
        message.get("channelId"),
        message.get("toChannelId"),
        message.get("targetId"),
        message.get("conversationId"),
        message.get("groupId"),
        data.get("channelId"),
    )
    sender_external_id = _first(
        message.get("fromUserId"),
        message.get("senderId"),
        message.get("userId"),
        payload.get("fromUserId"),
    )
    provider_message_id = _first(
        message.get("messageId"),
        message.get("uid"),
        message.get("mid"),
        payload.get("messageId"),
    )
    text = _text_from_content(message.get("content"))

    if not channel_id or not text:
        return {"code": 0, "result": "ignored_not_a_text_message"}

    channel_id = str(channel_id)
    sender_external_id = str(sender_external_id) if sender_external_id else None
    provider_message_id = str(provider_message_id) if provider_message_id else None

    if sender_external_id and sender_external_id == settings.nexconn_bot_user_id:
        return {"code": 0, "result": "ignored_self"}

    room = db.scalar(select(Room).where(Room.nexconn_conversation_id == channel_id))
    if room is None:
        logger.info("Nexconn message for unmapped conversation %s", channel_id)
        return {"code": 0, "result": "conversation_not_mapped"}

    if provider_message_id and db.scalar(
        select(Message).where(Message.provider_message_id == provider_message_id)
    ):
        return {"code": 0, "result": "duplicate"}

    sender = (
        db.scalar(select(User).where(User.nexconn_user_id == sender_external_id))
        if sender_external_id
        else None
    )

    message_row = Message(
        room_id=room.id,
        sender_id=sender.id if sender else None,
        message_text=text,
        message_type="text",
        provider_message_id=provider_message_id,
    )
    db.add(message_row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"code": 0, "result": "duplicate"}

    text_for_bot = bot_service.include_search_context(
        db, room.id, sender, text, before_id=message_row.id
    )
    reply = bot_service.handle_incoming_text(db, room, sender, text_for_bot)
    if reply.get("action") != "ignored" and reply.get("reply"):
        stored = {
            key: reply[key]
            for key in (
                "action", "reply", "watch_id", "watch_type", "alert_id", "error",
                "sources", "search_query", "result_count", "summary",
                "follow_up_question", "results", "missing_fields", "unsupported",
                "choice",
            )
            if key in reply
        }
        if reply.get("action") == "search_results":
            stored["context"] = text_for_bot
        db.add(
            Message(
                room_id=room.id,
                sender_id=None,
                message_text=json.dumps(stored, ensure_ascii=False),
                message_type="bot",
            )
        )
        db.commit()
    return {"code": 0, "result": reply}
