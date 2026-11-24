"""The Nazar bot behaviour shared by the Nexconn webhook and the REST messages API."""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.nexconn_client import nexconn_client
from app.integrations.serpapi_client import ProviderError
from app.models.alert import Alert
from app.models.message import Message
from app.models.room import Room
from app.models.user import User
from app.models.watch import Watch
from app.services import room_service, search_service, voting_service, watch_service
from app.services.parser_service import parse_message
from app.utils.normalization import format_money, utcnow

logger = logging.getLogger(__name__)

MENTION_RE = re.compile(r"@nazar\b", re.IGNORECASE)
SEARCH_FOLLOW_UP_WINDOW = timedelta(minutes=15)
WATCH_INTENT_RE = re.compile(
    r"\b(?:watch|track|alert|notify|monitor|remind|check for|nazar rakho|nazar rakh|"
    r"keep an eye|keep me posted|let me know when|tell me when|jab|aaye|aayen)\b|"
    r"\b(?:gir|fall|drop)\s+(?:jaye|below|under)\b|\b(?:ho|hoga|hogi)\s+toh\b",
    re.IGNORECASE,
)
ACKNOWLEDGEMENTS = {"ok", "okay", "thanks", "thank you", "got it", "great", "cool"}


def include_search_context(
    db: Session,
    room_id: int,
    sender: User | None,
    text: str,
    *,
    before_id: int,
) -> str:
    """Join a short same-user reply to Nazar's recent search so it can narrow results."""

    if sender is None or len(text.split()) > 6 or text.strip().lower() in ACKNOWLEDGEMENTS:
        return text
    last_two = db.scalars(
        select(Message)
        .where(Message.room_id == room_id, Message.id < before_id)
        .order_by(Message.id.desc())
        .limit(2)
    ).all()
    if len(last_two) < 2:
        return text
    bot_msg, asked_by = last_two
    if (
        bot_msg.sender_id is not None
        or bot_msg.message_type != "bot"
        or asked_by.sender_id != sender.id
        or utcnow() - bot_msg.created_at > SEARCH_FOLLOW_UP_WINDOW
    ):
        return text
    try:
        data = json.loads(bot_msg.message_text)
    except ValueError:
        return text
    context = data.get("context")
    if data.get("action") != "search_results" or not isinstance(context, str):
        return text
    return f"@Nazar {MENTION_RE.sub(' ', context).strip()} {MENTION_RE.sub(' ', text).strip()}"


def send_to_room(room: Room, text: str) -> bool:
    if not room.nexconn_conversation_id or not nexconn_client.configured:
        return False
    try:
        nexconn_client.send_group_text(room.nexconn_conversation_id, text)
        return True
    except ProviderError as exc:
        logger.warning("Could not send bot message to room %s: %s", room.id, exc)
        return False


def send_search_card(room: Room, result: dict) -> bool:
    if not room.nexconn_conversation_id or not nexconn_client.configured:
        return False
    card = {
        key: result[key]
        for key in ("action", "summary", "follow_up_question", "results", "sources")
        if key in result
    }
    try:
        nexconn_client.send_search_card(room.nexconn_conversation_id, card)
        return True
    except ProviderError as exc:
        logger.warning("Could not send search card to room %s: %s", room.id, exc)
        return False


def _describe_watch(watch: Watch) -> str:
    rule = watch.rule_json
    if watch.watch_type == "flight":
        return (
            f"✈️ Flight {rule.get('origin')} → {rule.get('destination')} on "
            f"{rule.get('travel_date')}. I'll alert the group when the fare is "
            f"{rule.get('condition')} {format_money(rule.get('target_price'), rule.get('currency', 'INR'))}."
        )
    if watch.watch_type == "stock":
        if rule.get("condition") == "absolute_change_greater_than":
            threshold = f"{rule.get('threshold_percent')}% {rule.get('direction', 'either')} move"
        else:
            threshold = f"price {rule.get('condition', '').replace('_', ' ')} {rule.get('target_price')}"
        return f"📈 {rule.get('symbol')} — alert on a {threshold}, measured from the previous close."
    if watch.watch_type == "topic":
        if rule.get("mode") in {"price_below", "price_above"}:
            side = "below" if rule.get("mode") == "price_below" else "above"
            return (
                f"🛒 {rule.get('query')}: I'll alert the group when the lowest price on Google Shopping "
                f"goes {side} {format_money(rule.get('target_price'), rule.get('currency', 'INR'))}."
            )
        where = {"news": "Google News", "jobs": "Google Jobs", "web": "the web"}.get(rule.get("source"), "the web")
        return f"🔎 {rule.get('query')}: I'll post the latest from {where} now, then only new results."
    return (
        f"📢 Job notifications for {', '.join(rule.get('keywords', []))}. "
        "I'll only use official recruitment domains."
    )


def _confirmation(watch: Watch) -> str:
    return (
        f"✅ Watch #{watch.id} created.\n{_describe_watch(watch)}\n"
        f"I'll check every {watch.check_interval} minutes and post only on a new crossing. "
        "Reply YES / NO / WAIT when an alert appears."
    )


def latest_alert(db: Session, room_id: int, max_age_days: int = 7) -> Alert | None:
    cutoff = utcnow() - timedelta(days=max_age_days)
    return db.scalar(
        select(Alert)
        .where(Alert.room_id == room_id, Alert.created_at >= cutoff)
        .order_by(Alert.created_at.desc())
        .limit(1)
    )


def handle_incoming_text(
    db: Session,
    room: Room,
    sender: User | None,
    text: str,
    *,
    reply_via_nexconn: bool = True,
) -> dict:
    """Process a bot mention, a prepared search follow-up, or a vote."""

    cleaned = text.strip()
    if not cleaned:
        return {"action": "ignored", "reason": "empty"}

    vote_text = MENTION_RE.sub(" ", cleaned).strip()
    token = voting_service.parse_vote_token(vote_text)
    if token is not None:
        alert = latest_alert(db, room.id)
        if alert is None:
            return {"action": "ignored", "reason": "no_open_alert"}

        if sender is None or room_service.get_membership(db, room.id, sender.id) is None:
            return {"action": "ignored", "reason": "unlinked_voter"}

        if token == "booked":
            result = voting_service.complete_watch(db, alert, sender)
            return {"action": "watch_completed", "reply": result["message"], **result}

        vote = voting_service.cast_vote(db, alert, sender, token)
        summary = voting_service.summary(db, alert, sender)
        reply = f"{sender.name} voted {token.upper()} on alert #{alert.id}. {voting_service.vote_notification(summary)}"

        if reply_via_nexconn and alert.room.nexconn_conversation_id:
            send_to_room(room, reply)

        return {
            "action": "vote_cast",
            "alert_id": alert.id,
            "choice": vote.choice,
            "reply": reply,
            "summary": summary,
        }

    if MENTION_RE.search(cleaned):
        if sender is None or room_service.get_membership(db, room.id, sender.id) is None:
            reply = (
                "I can only search or create watches for room members. Join this room with the "
                "Nazar invite link first, then mention me again."
            )
            if reply_via_nexconn:
                send_to_room(room, reply)
            return {"action": "unlinked_sender", "reply": reply}

        parsed = parse_message(cleaned)
        if parsed.get("unsupported"):
            reply = parsed.get("follow_up_question") or "What would you like me to search for?"
            delivered = send_to_room(room, reply) if reply_via_nexconn else False
            return {
                "action": "follow_up",
                "reply": reply,
                "missing_fields": parsed.get("missing_fields", []),
                "unsupported": True,
                "delivered": delivered,
            }

        if not WATCH_INTENT_RE.search(cleaned):
            result = search_service.search(cleaned, parsed)
            delivery = result["reply"]
            if result.get("sources"):
                citations = "\n".join(
                    f"- {source['title']}: {source['url']}" for source in result["sources"][:5]
                )
                delivery = f"{delivery}\n\nSources:\n{citations}"
            delivered = send_search_card(room, result) if reply_via_nexconn else False
            if reply_via_nexconn and not delivered:
                delivered = send_to_room(room, delivery)
            result["delivered"] = delivered
            return result

        if parsed["understood"] and parsed.get("rule"):
            try:
                watch = watch_service.create_watch(
                    db,
                    room,
                    sender,
                    parsed["watch_type"],
                    parsed["rule"],
                )
            except HTTPException as exc:
                reply = f"I couldn't save that watch: {exc.detail}"
                if reply_via_nexconn:
                    send_to_room(room, reply)
                return {"action": "watch_rejected", "reply": reply, "error": exc.detail}

            reply = _confirmation(watch)
            delivered = send_to_room(room, reply) if reply_via_nexconn else False
            return {
                "action": "watch_created",
                "watch_id": watch.id,
                "watch_type": watch.watch_type,
                "reply": reply,
                "delivered": delivered,
            }

        reply = parsed.get("follow_up_question") or "I need a bit more detail to set that up."
        delivered = send_to_room(room, reply) if reply_via_nexconn else False
        return {
            "action": "follow_up",
            "reply": reply,
            "missing_fields": parsed.get("missing_fields", []),
            "unsupported": bool(parsed.get("unsupported")),
            "delivered": delivered,
        }

    return {"action": "ignored", "reason": "not_a_mention_or_vote"}
