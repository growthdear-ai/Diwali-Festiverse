from __future__ import annotations

import json
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.message import Message
from app.models.user import User
from app.schemas.room import MessageCreate, MessageOut, MessageWithBotOut
from app.services import bot_service, parser_service, room_service
from app.utils.normalization import utcnow

router = APIRouter(prefix="/rooms", tags=["messages"])

FOLLOW_UP_WINDOW = timedelta(minutes=15)
_MENTION = re.compile(r"@nazar\b", re.IGNORECASE)


def _strip_mention(text: str) -> str:
    return _MENTION.sub(" ", text).strip()


def _with_mention(text: str) -> str:
    return text if _MENTION.search(text) else f"@Nazar {text}"


def _pending_request(
    db: Session, room_id: int, user_id: int, *, before_id: int
) -> dict[str, str] | None:
    """If Nazar's last message here was a follow-up question to this user, return the request it refers to."""
    last_two = db.scalars(
        select(Message).where(Message.room_id == room_id, Message.id < before_id).order_by(Message.id.desc()).limit(2)
    ).all()
    if len(last_two) < 2:
        return None
    bot_msg, asked_by = last_two
    if bot_msg.sender_id is not None or bot_msg.message_type != "bot" or asked_by.sender_id != user_id:
        return None
    if utcnow() - bot_msg.created_at > FOLLOW_UP_WINDOW:
        return None
    try:
        data = json.loads(bot_msg.message_text)
    except ValueError:
        return None
    if data.get("action") != "follow_up":
        return None
    context = data.get("context")
    action = data.get("action")
    if not isinstance(context, str) or not isinstance(action, str):
        return None
    return {"context": context, "action": action}


@router.get("/{room_id}/messages", response_model=list[MessageOut])
def list_messages(
    room_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MessageOut]:
    room = room_service.get_room_for_user(db, room_id, user)
    messages = db.scalars(
        select(Message)
        .where(Message.room_id == room.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).all()
    return [MessageOut.model_validate(message) for message in reversed(messages)]


@router.post("/{room_id}/messages", response_model=MessageWithBotOut, status_code=201)
def post_message(
    room_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageWithBotOut:
    room = room_service.get_room_for_user(db, room_id, user)

    message = Message(
        room_id=room.id,
        sender_id=user.id,
        message_text=payload.message_text,
        message_type=payload.message_type,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    text_for_bot = bot_service.include_search_context(
        db, room.id, user, payload.message_text, before_id=message.id
    )
    pending = _pending_request(db, room.id, user.id, before_id=message.id)
    looks_like_answer = bool(_MENTION.search(text_for_bot)) or len(text_for_bot.split()) <= 6
    is_watch_answer = bool(
        pending
        and pending["action"] == "follow_up"
        and not parser_service.heuristic_parse(_with_mention(text_for_bot))["understood"]
    )
    if pending and looks_like_answer and is_watch_answer:
        # Nazar asked this user a follow-up question; treat this message as the answer.
        text_for_bot = (
            "@Nazar " + _strip_mention(pending["context"]) + " " + _strip_mention(text_for_bot)
        )

    bot_reply = bot_service.handle_incoming_text(db, room, user, text_for_bot)

    # Persist Nazar's reply in the room so it survives reloads and every member sees it
    # (Nexconn delivery, when configured, is separate and only reaches the Nexconn group).
    if bot_reply and bot_reply.get("action") != "ignored" and bot_reply.get("reply"):
        stored = {
            k: bot_reply[k]
            for k in (
                "action", "reply", "watch_id", "watch_type", "alert_id", "error",
                "sources", "search_query", "result_count", "summary",
                "follow_up_question", "results",
            )
            if k in bot_reply
        }
        if bot_reply.get("action") == "follow_up" and not bot_reply.get("unsupported"):
            stored["context"] = text_for_bot  # what the follow-up answer will be joined to
        elif bot_reply.get("action") == "search_results":
            stored["context"] = text_for_bot
        db.add(Message(room_id=room.id, sender_id=None, message_text=json.dumps(stored, ensure_ascii=False), message_type="bot"))
        db.commit()

    return MessageWithBotOut(
        message=MessageOut.model_validate(message),
        bot_reply=bot_reply,
    )
